from __future__ import annotations

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
            row = (await session.execute(text("select status from ops.manager_presence_states where actor_id=:actor_id"), {"actor_id": actor_id})).first()
        return PresenceStatus(row.status) if row else PresenceStatus.ONLINE

    async def set_status(self, actor_id, status: PresenceStatus) -> None:
        async with self._sf() as session:
            await session.execute(
                text(
                    """
                    insert into ops.manager_presence_states(actor_id,status,updated_at,created_at)
                    values (:actor_id,:status,now(),now())
                    on conflict (actor_id) do update set status=:status, updated_at=now()
                    """
                ),
                {"actor_id": actor_id, "status": status.value},
            )
            await session.commit()


class SqlQueueRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def summary_counts(self, actor_id):
        # thin and explicit; assumes MB3 read-model semantics in DB.
        keys = ["new", "mine", "waiting_me", "waiting_customer", "urgent", "escalated"]
        result = {k: 0 for k in keys}
        async with self._sf() as session:
            rows = (await session.execute(text("select queue_key, count(*) as c from read.manager_case_queue_view where actor_id=:actor_id group by queue_key"), {"actor_id": actor_id})).all()
        for row in rows:
            if row.queue_key in result:
                result[row.queue_key] = row.c
        return result

    async def list_queue(self, queue_key, actor_id, offset, limit):
        query = text(
            """
            select case_id, case_display_number, customer_label, operational_status, waiting_state,
                   assigned_manager_actor_id, priority, escalation_level, last_customer_message_at
            from read.manager_case_queue_view
            where queue_key=:queue_key and actor_id=:actor_id
            order by sort_ts desc, case_display_number asc
            offset :offset limit :limit
            """
        )
        async with self._sf() as session:
            rows = (await session.execute(query, {"queue_key": queue_key, "actor_id": actor_id, "offset": offset, "limit": limit})).all()
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
                               ops.operational_status, ops.waiting_state, ops.priority, ops.escalation_level,
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
                    text("select direction, body, created_at from ops.quote_case_thread_entries where quote_case_id=:case_id order by created_at desc limit 10"),
                    {"case_id": case_id},
                )
            ).all()
        detail = CaseDetail(**head._mapping, linked_quote_display_number=head.case_display_number)
        detail.thread_entries = [ThreadEntry(**r._mapping) for r in reversed(thread_rows)]
        return detail

    async def claim_case(self, case_id, actor_id):
        async with self._sf() as session:
            result = await session.execute(
                text(
                    """
                    update ops.quote_case_ops_states
                    set assigned_manager_actor_id=:actor_id, operational_status='active', waiting_state='manager', updated_at=now()
                    where quote_case_id=:case_id
                    """
                ),
                {"case_id": case_id, "actor_id": actor_id},
            )
            await session.execute(
                text(
                    "insert into ops.quote_case_assignment_events(id, quote_case_id, assigned_to_actor_id, assigned_by_actor_id, created_at, updated_at) values (gen_random_uuid(),:case_id,:actor_id,:actor_id,now(),now())"
                ),
                {"case_id": case_id, "actor_id": actor_id},
            )
            await session.commit()
        return result.rowcount > 0
