from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import CaseDetail, DeliverySnapshot, InternalNote, ManagerActor, NotificationEvent, PresenceStatus, QueueItem, SystemRole, ThreadEntry


class SqlActorRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def by_telegram_user_id(self, telegram_user_id: int) -> ManagerActor | None:
        query = text(
            """
            select a.id, a.display_name, b.telegram_user_id, ar.role
            from core.actors a
            join core.actor_telegram_bindings b on b.actor_id = a.id
            join core.actor_roles ar on ar.actor_id = a.id
            where b.telegram_user_id = :telegram_user_id
            """
        )
        async with self._sf() as session:
            row = (await session.execute(query, {"telegram_user_id": telegram_user_id})).first()
        if not row:
            return None
        return ManagerActor(actor_id=row.id, telegram_user_id=row.telegram_user_id, display_name=row.display_name, role=SystemRole(row.role))

    async def list_internal_recipients(self) -> list[tuple[str, int, str, str]]:
        query = text(
            """
            select
                a.id as actor_id,
                b.telegram_user_id,
                ar.role,
                coalesce(mps.presence_status, 'offline') as presence_status
            from core.actors a
            join core.actor_telegram_bindings b on b.actor_id = a.id
            join core.actor_roles ar on ar.actor_id = a.id
            left join ops.manager_presence_states mps on mps.actor_id = a.id
            where ar.role in ('OWNER', 'MANAGER')
            """
        )
        async with self._sf() as session:
            rows = (await session.execute(query)).all()
        return [(str(r.actor_id), int(r.telegram_user_id), str(r.role), str(r.presence_status)) for r in rows]


class SqlPresenceRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def get_status(self, actor_id):
        async with self._sf() as session:
            row = (await session.execute(text("select presence_status from ops.manager_presence_states where actor_id=:actor_id"), {"actor_id": actor_id})).first()
        return PresenceStatus(row.presence_status) if row else PresenceStatus.OFFLINE

    async def set_status(self, actor_id, status: PresenceStatus) -> None:
        async with self._sf() as session:
            await session.execute(
                text(
                    """
                    insert into ops.manager_presence_states(actor_id,presence_status,updated_at,created_at)
                    values (:actor_id,:status,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
                    on conflict (actor_id) do update set presence_status=:status, updated_at=CURRENT_TIMESTAMP
                    """
                ),
                {"actor_id": actor_id, "status": status.value},
            )
            await session.commit()


class SqlQueueRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def summary_counts(self, actor_id):
        keys = ["new", "mine", "waiting_me", "waiting_customer", "urgent", "escalated", "sla_near", "sla_overdue"]
        result = {k: 0 for k in keys}
        now = datetime.now(timezone.utc)
        near_cutoff = now.timestamp() + 1800
        async with self._sf() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        select status, waiting_state, priority, escalation_level, assigned_manager_actor_id, sla_due_at
                        from ops.quote_case_ops_states
                        """
                    )
                )
            ).all()
        for row in rows:
            if row.status == "new":
                result["new"] += 1
            if row.assigned_manager_actor_id == actor_id and row.status in ("new", "active"):
                result["mine"] += 1
                if row.waiting_state in ("none", "waiting_manager", "waiting_owner"):
                    result["waiting_me"] += 1
            if row.status == "active" and row.waiting_state == "waiting_customer":
                result["waiting_customer"] += 1
            if row.priority == "urgent" and row.status not in ("resolved", "closed"):
                result["urgent"] += 1
            if row.escalation_level > 0 and row.status not in ("resolved", "closed"):
                result["escalated"] += 1
            if row.sla_due_at:
                due = row.sla_due_at
                due_ts = due.timestamp() if hasattr(due, "timestamp") else datetime.fromisoformat(str(due)).timestamp()
                if due_ts <= now.timestamp():
                    result["sla_overdue"] += 1
                elif due_ts <= near_cutoff:
                    result["sla_near"] += 1
        return result

    async def list_queue(self, queue_key, actor_id, offset, limit):
        filters = {
            "new": "s.status = 'new'",
            "mine": "s.assigned_manager_actor_id = :actor_id and s.status in ('new', 'active')",
            "waiting_me": "s.assigned_manager_actor_id = :actor_id and s.status in ('new', 'active') and s.waiting_state in ('none', 'waiting_manager', 'waiting_owner')",
            "waiting_customer": "s.status = 'active' and s.waiting_state = 'waiting_customer'",
            "urgent": "s.priority = 'urgent' and s.status not in ('resolved', 'closed')",
            "escalated": "s.escalation_level > 0 and s.status not in ('resolved', 'closed')",
        }
        condition = filters.get(queue_key, "1=0")
        query = text(
            f"""
            select
                qc.id as case_id,
                qc.display_number as case_display_number,
                qc.customer_label as customer_label,
                s.status as operational_status,
                s.waiting_state,
                s.assigned_manager_actor_id,
                s.priority,
                s.escalation_level,
                s.last_customer_message_at,
                s.sla_due_at
            from ops.quote_case_ops_states s
            join core.quote_cases qc on qc.id = s.quote_case_id
            where {condition}
            """
        )
        async with self._sf() as session:
            rows = (await session.execute(query, {"actor_id": actor_id})).all()
        items = [QueueItem(**row._mapping) for row in rows]
        now_ts = datetime.now(timezone.utc).timestamp()

        def sla_rank(item: QueueItem) -> int:
            if not item.sla_due_at:
                return 2
            due_ts = item.sla_due_at.timestamp() if hasattr(item.sla_due_at, "timestamp") else datetime.fromisoformat(str(item.sla_due_at)).timestamp()
            if due_ts <= now_ts:
                return 0
            if due_ts <= now_ts + 1800:
                return 1
            return 2

        def prio_rank(item: QueueItem) -> int:
            return {"urgent": 0, "high": 1}.get(item.priority, 2)

        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        items.sort(
            key=lambda i: (
                prio_rank(i),
                sla_rank(i),
                -i.escalation_level,
                i.sla_due_at or i.last_customer_message_at or epoch,
                i.case_display_number,
            )
        )
        return items[offset : offset + limit]


class SqlCaseRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def get_detail(self, case_id, actor_id):
        async with self._sf() as session:
            head = (
                await session.execute(
                    text(
                        """
                        select qc.id as case_id, qc.display_number as case_display_number, qc.status as commercial_status,
                               ops.status as operational_status, ops.waiting_state, ops.priority, ops.escalation_level, ops.sla_due_at,
                               coalesce(am.display_name, 'Unassigned') as assignment_label,
                               o.display_number as linked_order_display_number
                        from core.quote_cases qc
                        join ops.quote_case_ops_states ops on ops.quote_case_id=qc.id
                        left join core.actors am on am.id=ops.assigned_manager_actor_id
                        left join core.orders o on o.source_quote_case_id=qc.id
                        where qc.id=:case_id
                        """
                    ),
                    {"case_id": case_id},
                )
            ).first()
            if not head:
                return None
            thread_rows = (
                await session.execute(
                    text(
                        """
                        select direction, body_text as body, created_at, coalesce(delivery_status, 'not_applicable') as delivery_status
                        from ops.quote_case_thread_entries
                        where quote_case_id=:case_id
                        order by created_at desc
                        limit 10
                        """
                    ),
                    {"case_id": case_id},
                )
            ).all()
            note_rows = (
                await session.execute(
                    text(
                        """
                        select n.body_text as body, coalesce(a.display_name, 'Manager') as author_label, n.created_at
                        from ops.quote_case_internal_notes n
                        left join core.actors a on a.id = n.author_actor_id
                        where n.quote_case_id=:case_id
                        order by n.created_at desc
                        limit 5
                        """
                    ),
                    {"case_id": case_id},
                )
            ).all()
            delivery_row = (
                await session.execute(
                    text(
                        """
                        select status, attempted_at, error_message
                        from ops.reply_delivery_attempts
                        where quote_case_id=:case_id
                        order by attempted_at desc
                        limit 1
                        """
                    ),
                    {"case_id": case_id},
                )
            ).first()
        detail = CaseDetail(**head._mapping, linked_quote_display_number=head.case_display_number)
        detail.thread_entries = [ThreadEntry(**r._mapping) for r in reversed(thread_rows)]
        detail.internal_notes = [InternalNote(**r._mapping) for r in reversed(note_rows)]
        if delivery_row:
            detail.last_delivery = DeliverySnapshot(**delivery_row._mapping)
        return detail

    async def claim_case(self, case_id, actor_id):
        async with self._sf() as session:
            current = (await session.execute(text("select assigned_manager_actor_id from ops.quote_case_ops_states where quote_case_id=:case_id"), {"case_id": case_id})).first()
            if not current:
                return False
            result = await session.execute(
                text(
                    """
                    update ops.quote_case_ops_states
                    set assigned_manager_actor_id=:actor_id,
                        assigned_by_actor_id=:actor_id,
                        assigned_at=CURRENT_TIMESTAMP,
                        status='active',
                        waiting_state='waiting_manager',
                        updated_at=CURRENT_TIMESTAMP
                    where quote_case_id=:case_id
                    """
                ),
                {"case_id": case_id, "actor_id": actor_id},
            )
            next_seq = (await session.execute(text("select coalesce(max(event_seq), 0) + 1 as next_seq from ops.quote_case_assignment_events where quote_case_id=:case_id"), {"case_id": case_id})).scalar_one()
            await session.execute(
                text(
                    """
                    insert into ops.quote_case_assignment_events(
                        id, quote_case_id, event_seq, event_kind, from_manager_actor_id, to_manager_actor_id, triggered_by_actor_id, created_at, updated_at
                    ) values (
                         :event_id, :case_id, :event_seq, :event_kind, :from_actor_id, :to_actor_id, :triggered_by_actor_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "case_id": case_id,
                    "event_seq": next_seq,
                    "event_kind": "claimed",
                    "from_actor_id": current.assigned_manager_actor_id,
                    "to_actor_id": actor_id,
                    "triggered_by_actor_id": actor_id,
                    "event_id": str(uuid4()),
                },
            )
            await session.commit()
        return result.rowcount > 0

    async def escalate_to_owner(self, case_id, actor_id):
        async with self._sf() as session:
            owner_row = (await session.execute(text("select actor_id from core.actor_roles where role='OWNER' order by actor_id asc limit 1"))).first()
            current = (await session.execute(text("select assigned_manager_actor_id from ops.quote_case_ops_states where quote_case_id=:case_id"), {"case_id": case_id})).first()
            if not owner_row or not current:
                return False
            result = await session.execute(
                text(
                    """
                    update ops.quote_case_ops_states
                    set escalation_level = 1,
                        priority = case when priority='urgent' then 'urgent' else 'high' end,
                        assigned_manager_actor_id = :owner_actor_id,
                        assigned_by_actor_id = :actor_id,
                        assigned_at = CURRENT_TIMESTAMP,
                        waiting_state = 'waiting_owner',
                        status = 'active',
                        updated_at = CURRENT_TIMESTAMP
                    where quote_case_id = :case_id
                    """
                ),
                {"case_id": case_id, "owner_actor_id": owner_row.actor_id, "actor_id": actor_id},
            )
            next_seq = (await session.execute(text("select coalesce(max(event_seq), 0) + 1 as next_seq from ops.quote_case_assignment_events where quote_case_id=:case_id"), {"case_id": case_id})).scalar_one()
            await session.execute(
                text(
                    """
                    insert into ops.quote_case_assignment_events(
                        id, quote_case_id, event_seq, event_kind, from_manager_actor_id, to_manager_actor_id, triggered_by_actor_id, created_at, updated_at
                    ) values (
                        :id, :case_id, :event_seq, 'escalated_to_owner', :from_actor_id, :to_actor_id, :triggered_by_actor_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": str(uuid4()),
                    "case_id": case_id,
                    "event_seq": next_seq,
                    "from_actor_id": current.assigned_manager_actor_id,
                    "to_actor_id": owner_row.actor_id,
                    "triggered_by_actor_id": actor_id,
                },
            )
            await session.commit()
        return result.rowcount > 0

    async def add_internal_note(self, case_id, actor_id, body_text):
        async with self._sf() as session:
            exists = (await session.execute(text("select 1 from ops.quote_case_ops_states where quote_case_id=:case_id"), {"case_id": case_id})).first()
            if not exists:
                return False
            await session.execute(
                text(
                    """
                    insert into ops.quote_case_internal_notes(
                        id, quote_case_id, author_actor_id, author_role, body_text, body_format, visibility_scope, created_at, updated_at
                    ) values (
                        :id, :case_id, :actor_id, 'manager', :body_text, 'plain_text', 'internal_only', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"id": str(uuid4()), "case_id": case_id, "actor_id": actor_id, "body_text": body_text},
            )
            await session.commit()
        return True

    async def create_outbound_reply(self, case_id, actor_id, body_text):
        async with self._sf() as session:
            case_row = (
                await session.execute(
                    text(
                        """
                        select qc.id,
                               coalesce(qc.customer_telegram_chat_id, b.telegram_user_id) as customer_chat_id
                        from core.quote_cases qc
                        left join core.actor_telegram_bindings b on b.actor_id = qc.customer_actor_id
                        where qc.id=:case_id
                        """
                    ),
                    {"case_id": case_id},
                )
            ).first()
            if not case_row or case_row.customer_chat_id is None:
                return None
            thread_entry_id = str(uuid4())
            attempt_id = str(uuid4())
            await session.execute(
                text(
                    """
                    insert into ops.quote_case_thread_entries(
                        id, quote_case_id, direction, body_text, delivery_status, author_role, author_actor_id, created_at, updated_at
                    ) values (
                        :thread_entry_id, :case_id, 'outbound', :body_text, 'pending', 'manager', :actor_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"thread_entry_id": thread_entry_id, "case_id": case_id, "body_text": body_text, "actor_id": actor_id},
            )
            await session.execute(
                text(
                    """
                    insert into ops.reply_delivery_attempts(
                        id, thread_entry_id, quote_case_id, target_telegram_chat_id, attempt_number, transport, status, attempted_at, completed_at, created_at, updated_at
                    ) values (
                        :attempt_id, :thread_entry_id, :case_id, :target_chat_id, 1, 'telegram_bot_api', 'pending', CURRENT_TIMESTAMP, null, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"attempt_id": attempt_id, "thread_entry_id": thread_entry_id, "case_id": case_id, "target_chat_id": case_row.customer_chat_id},
            )
            await session.commit()
        return thread_entry_id, attempt_id, int(case_row.customer_chat_id)

    async def mark_reply_delivery(self, thread_entry_id, attempt_id, status, *, telegram_message_id, error_message):
        async with self._sf() as session:
            if status == "sent":
                await session.execute(
                    text(
                        """
                        update ops.reply_delivery_attempts
                        set status='sent', completed_at=CURRENT_TIMESTAMP, telegram_message_id=:telegram_message_id, error_message=null, updated_at=CURRENT_TIMESTAMP
                        where id=:attempt_id
                        """
                    ),
                    {"attempt_id": attempt_id, "telegram_message_id": telegram_message_id},
                )
                await session.execute(
                    text(
                        """
                        update ops.quote_case_thread_entries
                        set delivery_status='sent', telegram_message_id=:telegram_message_id, delivered_at=CURRENT_TIMESTAMP, failed_at=null, updated_at=CURRENT_TIMESTAMP
                        where id=:thread_entry_id
                        """
                    ),
                    {"thread_entry_id": thread_entry_id, "telegram_message_id": telegram_message_id},
                )
                await session.execute(
                    text(
                        """
                        update ops.quote_case_ops_states
                        set last_manager_message_at=CURRENT_TIMESTAMP, waiting_state='waiting_customer', status='active', updated_at=CURRENT_TIMESTAMP
                        where quote_case_id=(select quote_case_id from ops.quote_case_thread_entries where id=:thread_entry_id)
                        """
                    ),
                    {"thread_entry_id": thread_entry_id},
                )
            else:
                await session.execute(
                    text(
                        """
                        update ops.reply_delivery_attempts
                        set status='failed', completed_at=CURRENT_TIMESTAMP, error_message=:error_message, updated_at=CURRENT_TIMESTAMP
                        where id=:attempt_id
                        """
                    ),
                    {"attempt_id": attempt_id, "error_message": error_message},
                )
                await session.execute(
                    text(
                        """
                        update ops.quote_case_thread_entries
                        set delivery_status='failed', failed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                        where id=:thread_entry_id
                        """
                    ),
                    {"thread_entry_id": thread_entry_id},
                )
            await session.commit()


class SqlNotificationRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def poll_events(self) -> list[NotificationEvent]:
        async with self._sf() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        select
                            'case_visible:' || s.quote_case_id || ':' || coalesce(s.updated_at::text, '') as event_key,
                            'case_visible' as kind,
                            s.quote_case_id as case_id,
                            qc.display_number as case_display_number,
                            s.assigned_manager_actor_id,
                            null as summary
                        from ops.quote_case_ops_states s
                        join core.quote_cases qc on qc.id = s.quote_case_id
                        where s.status = 'new'
                        union all
                        select
                            'new_inbound:' || t.id as event_key,
                            'new_inbound' as kind,
                            t.quote_case_id as case_id,
                            qc.display_number as case_display_number,
                            s.assigned_manager_actor_id,
                            substr(t.body_text, 1, 120) as summary
                        from ops.quote_case_thread_entries t
                        join ops.quote_case_ops_states s on s.quote_case_id = t.quote_case_id
                        join core.quote_cases qc on qc.id = t.quote_case_id
                        where t.direction = 'inbound'
                        union all
                        select
                            'assigned_to_me:' || e.id as event_key,
                            'assigned_to_me' as kind,
                            e.quote_case_id as case_id,
                            qc.display_number as case_display_number,
                            e.to_manager_actor_id as assigned_manager_actor_id,
                            null as summary
                        from ops.quote_case_assignment_events e
                        join core.quote_cases qc on qc.id = e.quote_case_id
                        where e.event_kind in ('claimed', 'assigned', 'reassigned', 'escalated_to_owner')
                        union all
                        select
                            'delivery_failed:' || a.id as event_key,
                            'delivery_failed' as kind,
                            a.quote_case_id as case_id,
                            qc.display_number as case_display_number,
                            s.assigned_manager_actor_id,
                            coalesce(a.error_message, 'delivery_failed') as summary
                        from ops.reply_delivery_attempts a
                        join ops.quote_case_ops_states s on s.quote_case_id = a.quote_case_id
                        join core.quote_cases qc on qc.id = a.quote_case_id
                        where a.status = 'failed'
                        """
                    )
                )
            ).all()
        return [
            NotificationEvent(
                event_key=str(r.event_key),
                kind=str(r.kind),
                case_id=r.case_id,
                case_display_number=int(r.case_display_number),
                assigned_manager_actor_id=r.assigned_manager_actor_id,
                summary=r.summary,
            )
            for r in rows
        ]
