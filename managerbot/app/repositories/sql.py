from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import CaseDetail, ManagerActor, PresenceStatus, QueueItem, SystemRole, ThreadEntry


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
        role = SystemRole(row.role)
        return ManagerActor(actor_id=row.id, telegram_user_id=row.telegram_user_id, display_name=row.display_name, role=role)


class SqlPresenceRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def get_status(self, actor_id):
        async with self._sf() as session:
            row = (
                await session.execute(
                    text(
                        "select presence_status from ops.manager_presence_states where actor_id=:actor_id"
                    ),
                    {"actor_id": actor_id},
                )
            ).first()
        return PresenceStatus(row.presence_status) if row else PresenceStatus.ONLINE

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
        keys = ["new", "mine", "waiting_me", "waiting_customer", "urgent", "escalated"]
        result = {k: 0 for k in keys}
        async with self._sf() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        select
                            case
                                when s.status = 'new' then 'new'
                                when s.assigned_manager_actor_id = :actor_id and s.status in ('new', 'active') and s.waiting_state in ('none', 'waiting_manager', 'waiting_owner') then 'waiting_me'
                                when s.assigned_manager_actor_id = :actor_id and s.status in ('new', 'active') then 'mine'
                                when s.status = 'active' and s.waiting_state = 'waiting_customer' then 'waiting_customer'
                                when s.priority = 'urgent' and s.status not in ('resolved', 'closed') then 'urgent'
                                when s.escalation_level > 0 and s.status not in ('resolved', 'closed') then 'escalated'
                                else null
                            end as queue_key,
                            count(*) as c
                        from ops.quote_case_ops_states s
                        group by queue_key
                        """
                    ),
                    {"actor_id": actor_id},
                )
            ).all()
        for row in rows:
            if row.queue_key in result:
                result[row.queue_key] = row.c
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
                s.last_customer_message_at
            from ops.quote_case_ops_states s
            join core.quote_cases qc on qc.id = s.quote_case_id
            where {condition}
            order by
                case s.priority when 'urgent' then 0 when 'high' then 1 else 2 end,
                s.escalation_level desc,
                coalesce(s.last_customer_message_at, s.updated_at) desc,
                qc.display_number asc
            limit :limit offset :offset
            """
        )
        async with self._sf() as session:
            rows = (
                await session.execute(
                    query,
                    {
                        "actor_id": actor_id,
                        "offset": offset,
                        "limit": limit,
                    },
                )
            ).all()
        return [QueueItem(**row._mapping) for row in rows]


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
                               ops.status as operational_status, ops.waiting_state, ops.priority, ops.escalation_level,
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
                        select direction, body_text as body, created_at
                        from ops.quote_case_thread_entries
                        where quote_case_id=:case_id
                        order by created_at desc
                        limit 10
                        """
                    ),
                    {"case_id": case_id},
                )
            ).all()
        detail = CaseDetail(**head._mapping, linked_quote_display_number=head.case_display_number)
        detail.thread_entries = [ThreadEntry(**r._mapping) for r in reversed(thread_rows)]
        return detail

    async def claim_case(self, case_id, actor_id):
        async with self._sf() as session:
            current = (
                await session.execute(
                    text(
                        "select assigned_manager_actor_id from ops.quote_case_ops_states where quote_case_id=:case_id"
                    ),
                    {"case_id": case_id},
                )
            ).first()
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
            next_seq = (
                await session.execute(
                    text(
                        "select coalesce(max(event_seq), 0) + 1 as next_seq from ops.quote_case_assignment_events where quote_case_id=:case_id"
                    ),
                    {"case_id": case_id},
                )
            ).scalar_one()
            await session.execute(
                text(
                    """
                    insert into ops.quote_case_assignment_events(
                        id,
                        quote_case_id,
                        event_seq,
                        event_kind,
                        from_manager_actor_id,
                        to_manager_actor_id,
                        triggered_by_actor_id,
                        created_at,
                        updated_at
                    ) values (
                         :event_id,
                        :case_id,
                        :event_seq,
                        :event_kind,
                        :from_actor_id,
                        :to_actor_id,
                        :triggered_by_actor_id,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
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
