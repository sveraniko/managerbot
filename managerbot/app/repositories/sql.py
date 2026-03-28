from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from app.models import (
    CaseDetail,
    CustomerCard,
    DeliverySnapshot,
    HotTaskBucket,
    HotTaskBucketKey,
    HotTaskItem,
    InternalNote,
    ManagerActor,
    ManagerItemDetail,
    NotificationEvent,
    PresenceStatus,
    QueueFilters,
    QueueItem,
    SearchResultItem,
    SystemRole,
    ThreadEntry,
)
from app.services.escalation import (
    ESCALATION_OWNER_ATTENTION,
    escalation_rank,
    is_escalated,
    normalize_escalation_level,
)
from app.services.priority import is_high_or_higher_priority, is_top_tier_priority, priority_rank


BUSINESS_RELEVANCE_SQL = """
(
    s.last_customer_message_at is not null
    or exists (
        select 1
        from ops.quote_case_thread_entries te
        where te.quote_case_id = s.quote_case_id
          and te.direction = 'inbound'
    )
    or qc.customer_actor_id is not null
    or qc.customer_telegram_chat_id is not null
    or nullif(trim(coalesce(qc.customer_label, '')), '') is not null
)
"""


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
                    insert into ops.manager_presence_states(id,actor_id,presence_status,updated_at,created_at)
                    values (gen_random_uuid(),:actor_id,:status,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
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
        keys = [
            "new",
            "new_incoming",
            "mine",
            "waiting_me",
            "waiting_customer",
            "urgent",
            "escalated",
            "sla_near",
            "sla_overdue",
            "sla_risk",
            "urgent_escalated",
            "failed_delivery",
        ]
        result = {k: 0 for k in keys}
        now = datetime.now(timezone.utc)
        near_cutoff = now.timestamp() + 1800
        async with self._sf() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        select
                            s.status,
                            s.waiting_state,
                            s.priority,
                            s.escalation_level,
                            s.assigned_manager_actor_id,
                            s.sla_due_at,
                            s.last_failed_delivery_at,
                            s.is_business_relevant
                        from (
                            select
                                s.status,
                                s.waiting_state,
                                s.priority,
                                s.escalation_level,
                                s.assigned_manager_actor_id,
                                s.sla_due_at,
                                (
                                    select max(a.attempted_at)
                                    from ops.reply_delivery_attempts a
                                    where a.quote_case_id = s.quote_case_id and a.status = 'failed'
                                ) as last_failed_delivery_at,
                                case when """
                        + BUSINESS_RELEVANCE_SQL
                        + """
                                then 1 else 0 end as is_business_relevant
                            from ops.quote_case_ops_states s
                            join core.quote_cases qc on qc.id = s.quote_case_id
                        ) s
                        """
                    )
                )
            ).all()
        for row in rows:
            escalation_level = normalize_escalation_level(row.escalation_level)
            if row.status == "new":
                result["new"] += 1
                if row.is_business_relevant:
                    result["new_incoming"] += 1
            if row.assigned_manager_actor_id == actor_id and row.status in ("new", "active"):
                result["mine"] += 1
                if row.waiting_state in ("none", "waiting_manager", "waiting_owner"):
                    result["waiting_me"] += 1
            if row.status == "active" and row.waiting_state == "waiting_customer":
                result["waiting_customer"] += 1
            if is_top_tier_priority(row.priority) and row.status not in ("resolved", "closed"):
                result["urgent"] += 1
            if is_escalated(escalation_level) and row.status not in ("resolved", "closed"):
                result["escalated"] += 1
            if row.status not in ("resolved", "closed"):
                if is_high_or_higher_priority(row.priority) or is_escalated(escalation_level):
                    result["urgent_escalated"] += 1
                if row.last_failed_delivery_at:
                    result["failed_delivery"] += 1
            if row.sla_due_at:
                due = row.sla_due_at
                due_ts = due.timestamp() if hasattr(due, "timestamp") else datetime.fromisoformat(str(due)).timestamp()
                if due_ts <= now.timestamp():
                    result["sla_overdue"] += 1
                    result["sla_risk"] += 1
                elif due_ts <= near_cutoff:
                    result["sla_near"] += 1
                    result["sla_risk"] += 1
        return result

    async def list_queue(self, queue_key, actor_id, offset, limit, filters: QueueFilters | None = None):
        query = text(
            """
            select
                qc.id as case_id,
                qc.display_number as case_display_number,
                qc.customer_label as customer_label,
                qc.customer_actor_id,
                qc.customer_telegram_chat_id,
                s.status as operational_status,
                s.waiting_state,
                s.assigned_manager_actor_id,
                s.priority,
                s.escalation_level,
                s.last_customer_message_at,
                s.sla_due_at,
                s.updated_at as ops_updated_at,
                exists (
                    select 1
                    from ops.quote_case_thread_entries te
                    where te.quote_case_id = s.quote_case_id and te.direction = 'inbound'
                ) as has_inbound_thread,
                (
                    select max(a.attempted_at)
                    from ops.reply_delivery_attempts a
                    where a.quote_case_id = s.quote_case_id and a.status = 'failed'
                ) as last_failed_delivery_at
            from ops.quote_case_ops_states s
            join core.quote_cases qc on qc.id = s.quote_case_id
            """
        )
        async with self._sf() as session:
            rows = (await session.execute(query, {"actor_id": actor_id})).all()
        entries = []
        for row in rows:
            data = dict(row._mapping)
            data["escalation_level"] = normalize_escalation_level(data.get("escalation_level"))
            data["sla_due_at"] = _as_dt(data.get("sla_due_at"))
            data["last_customer_message_at"] = _as_dt(data.get("last_customer_message_at"))
            data["ops_updated_at"] = _as_dt(data.get("ops_updated_at"))
            data["last_failed_delivery_at"] = _as_dt(data.get("last_failed_delivery_at"))
            entries.append(data)

        now_ts = datetime.now(timezone.utc).timestamp()
        filters = filters or QueueFilters()

        def sla_due_rank(sla_due_at) -> int:
            if not sla_due_at:
                return 2
            due_ts = sla_due_at.timestamp() if hasattr(sla_due_at, "timestamp") else datetime.fromisoformat(str(sla_due_at)).timestamp()
            if due_ts <= now_ts:
                return 0
            if due_ts <= now_ts + 1800:
                return 1
            return 2

        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        if queue_key == "archive":
            filtered = [i for i in entries if i["operational_status"] in ("resolved", "closed")]
            filtered.sort(
                key=lambda i: (
                    priority_rank(i["priority"]),
                    -escalation_rank(i["escalation_level"]),
                    -(i["ops_updated_at"] or epoch).timestamp(),
                    int(i["case_display_number"]),
                )
            )
        elif queue_key == "new":
            filtered = [i for i in entries if i["operational_status"] == "new"]
            filtered.sort(key=lambda i: (priority_rank(i["priority"]), -escalation_rank(i["escalation_level"]), -(i["ops_updated_at"] or epoch).timestamp(), int(i["case_display_number"])))
        elif queue_key == "new_incoming":
            filtered = [
                i
                for i in entries
                if i["operational_status"] == "new"
                and (
                    i["last_customer_message_at"] is not None
                    or bool(i["customer_actor_id"])
                    or i["customer_telegram_chat_id"] is not None
                    or bool((i.get("customer_label") or "").strip())
                    or i.get("has_inbound_thread", False)
                )
            ]
            filtered.sort(
                key=lambda i: (
                    priority_rank(i["priority"]),
                    -escalation_rank(i["escalation_level"]),
                    -(i["last_customer_message_at"] or i["ops_updated_at"] or epoch).timestamp(),
                    int(i["case_display_number"]),
                )
            )
        elif queue_key == "mine":
            filtered = [i for i in entries if i["assigned_manager_actor_id"] == actor_id]
            filtered.sort(key=lambda i: (priority_rank(i["priority"]), sla_due_rank(i["sla_due_at"]), -escalation_rank(i["escalation_level"]), (i["sla_due_at"] or i["last_customer_message_at"] or epoch).timestamp(), int(i["case_display_number"])))
        elif queue_key == "waiting_me":
            filtered = [i for i in entries if i["assigned_manager_actor_id"] == actor_id and i["waiting_state"] in ("none", "waiting_manager", "waiting_owner")]
            filtered.sort(key=lambda i: (priority_rank(i["priority"]), sla_due_rank(i["sla_due_at"]), -escalation_rank(i["escalation_level"]), (i["sla_due_at"] or i["last_customer_message_at"] or epoch).timestamp(), int(i["case_display_number"])))
        elif queue_key == "waiting_customer":
            filtered = [i for i in entries if i["operational_status"] == "active" and i["waiting_state"] == "waiting_customer"]
            filtered.sort(key=lambda i: (priority_rank(i["priority"]), -escalation_rank(i["escalation_level"]), -(i["last_customer_message_at"] or epoch).timestamp(), int(i["case_display_number"])))
        elif queue_key == "urgent":
            filtered = [i for i in entries if is_top_tier_priority(i["priority"])]
            filtered.sort(key=lambda i: (-escalation_rank(i["escalation_level"]), sla_due_rank(i["sla_due_at"]), -(i["last_customer_message_at"] or epoch).timestamp(), int(i["case_display_number"])))
        elif queue_key == "escalated":
            filtered = [i for i in entries if is_escalated(i["escalation_level"])]
            filtered.sort(key=lambda i: (priority_rank(i["priority"]), sla_due_rank(i["sla_due_at"]), -(i["last_customer_message_at"] or epoch).timestamp(), int(i["case_display_number"])))
        elif queue_key == "sla_risk":
            filtered = [i for i in entries if sla_due_rank(i["sla_due_at"]) in (0, 1)]
            filtered.sort(key=lambda i: (sla_due_rank(i["sla_due_at"]), priority_rank(i["priority"]), -escalation_rank(i["escalation_level"]), (i["sla_due_at"] or epoch).timestamp(), int(i["case_display_number"])))
        elif queue_key == "urgent_escalated":
            filtered = [i for i in entries if is_high_or_higher_priority(i["priority"]) or is_escalated(i["escalation_level"])]
            filtered.sort(key=lambda i: (priority_rank(i["priority"]), -escalation_rank(i["escalation_level"]), sla_due_rank(i["sla_due_at"]), -(i["last_customer_message_at"] or epoch).timestamp(), int(i["case_display_number"])))
        elif queue_key == "failed_delivery":
            filtered = [i for i in entries if i["last_failed_delivery_at"] is not None]
            filtered.sort(key=lambda i: (-(i["last_failed_delivery_at"] or epoch).timestamp(), priority_rank(i["priority"]), -escalation_rank(i["escalation_level"]), int(i["case_display_number"])))
        else:
            filtered = []

        filtered = self._apply_filters(filtered, actor_id, filters)

        items = [
            QueueItem(
                case_id=item["case_id"],
                case_display_number=item["case_display_number"],
                customer_label=item["customer_label"],
                operational_status=item["operational_status"],
                waiting_state=item["waiting_state"],
                assigned_manager_actor_id=item["assigned_manager_actor_id"],
                priority=item["priority"],
                escalation_level=item["escalation_level"],
                last_customer_message_at=item["last_customer_message_at"],
                sla_due_at=item["sla_due_at"],
                is_archived=item["operational_status"] in ("resolved", "closed"),
            )
            for item in filtered
        ]
        return items[offset : offset + limit]

    def _apply_filters(self, items: list[dict], actor_id, filters: QueueFilters) -> list[dict]:
        now_ts = datetime.now(timezone.utc).timestamp()

        def sla_due_rank(sla_due_at) -> int:
            if not sla_due_at:
                return 2
            due_ts = sla_due_at.timestamp() if hasattr(sla_due_at, "timestamp") else datetime.fromisoformat(str(sla_due_at)).timestamp()
            if due_ts <= now_ts:
                return 0
            if due_ts <= now_ts + 1800:
                return 1
            return 2

        filtered = list(items)
        if filters.assignment_scope == "mine":
            filtered = [i for i in filtered if i["assigned_manager_actor_id"] == actor_id]
        elif filters.assignment_scope == "unassigned":
            filtered = [i for i in filtered if i["assigned_manager_actor_id"] is None]
        if filters.waiting_scope == "waiting_manager":
            filtered = [i for i in filtered if i["waiting_state"] in ("none", "waiting_manager", "waiting_owner")]
        elif filters.waiting_scope == "waiting_customer":
            filtered = [i for i in filtered if i["waiting_state"] == "waiting_customer"]
        if filters.priority_scope == "high_or_urgent":
            filtered = [i for i in filtered if is_high_or_higher_priority(i["priority"])]
        elif filters.priority_scope == "urgent_or_vip":
            filtered = [i for i in filtered if is_top_tier_priority(i["priority"])]
        elif filters.priority_scope == "vip":
            filtered = [i for i in filtered if i["priority"] == "vip"]
        if filters.sla_scope == "at_risk":
            filtered = [i for i in filtered if i["sla_due_at"] and sla_due_rank(i["sla_due_at"]) in (0, 1)]
        if filters.escalation_scope == "escalated":
            filtered = [i for i in filtered if is_escalated(i["escalation_level"])]
        if filters.lifecycle_scope == "active":
            filtered = [i for i in filtered if i["operational_status"] in ("new", "active")]
        elif filters.lifecycle_scope == "archive":
            filtered = [i for i in filtered if i["operational_status"] in ("resolved", "closed")]
        return filtered

    async def search_cases(self, actor_id, query: str, limit: int, filters: QueueFilters | None = None) -> list[SearchResultItem]:
        filters = filters or QueueFilters(lifecycle_scope="all")
        needle = query.strip().lower()
        if not needle:
            return []
        search_query = text(
            """
            select
                qc.id as case_id,
                qc.display_number as case_display_number,
                qc.customer_label,
                qc.customer_actor_id,
                qc.customer_telegram_chat_id,
                o.display_number as linked_order_display_number,
                s.status as operational_status,
                s.waiting_state,
                s.priority,
                s.escalation_level,
                s.assigned_manager_actor_id,
                s.sla_due_at
            from core.quote_cases qc
            join ops.quote_case_ops_states s on s.quote_case_id = qc.id
            left join core.orders o on o.source_quote_case_id = qc.id
            """
        )
        async with self._sf() as session:
            rows = (await session.execute(search_query)).all()
        raw_items = [dict(r._mapping) for r in rows]
        for item in raw_items:
            item["escalation_level"] = normalize_escalation_level(item.get("escalation_level"))
            item["sla_due_at"] = _as_dt(item.get("sla_due_at"))
        raw_items = self._apply_filters(raw_items, actor_id, filters)

        def match_rank(item: dict) -> int | None:
            case_num = str(item["case_display_number"])
            order_num = str(item["linked_order_display_number"] or "")
            customer = (item.get("customer_label") or "").lower()
            customer_actor_id = str(item.get("customer_actor_id") or "").lower()
            chat_id = str(item.get("customer_telegram_chat_id") or "")
            if needle in {f"q-{case_num}", f"quote {case_num}", case_num}:
                return 0
            if order_num and needle in {f"o-{order_num}", f"order {order_num}", order_num}:
                return 1
            if customer.startswith(needle):
                return 2
            if needle.startswith("@") and needle[1:] and needle[1:] in customer:
                return 2
            if needle in customer or needle in customer_actor_id or (chat_id and needle in chat_id):
                return 3
            return None

        matched: list[tuple[int, dict]] = []
        for item in raw_items:
            rank = match_rank(item)
            if rank is not None:
                matched.append((rank, item))
        matched.sort(
            key=lambda pair: (
                pair[0],
                0 if pair[1]["operational_status"] in ("new", "active") else 1,
                priority_rank(pair[1]["priority"]),
                -escalation_rank(pair[1]["escalation_level"]),
                int(pair[1]["case_display_number"]),
            )
        )
        return [
            SearchResultItem(
                case_id=item["case_id"],
                case_display_number=int(item["case_display_number"]),
                linked_order_display_number=item["linked_order_display_number"],
                customer_label=item.get("customer_label"),
                operational_status=item["operational_status"],
                waiting_state=item["waiting_state"],
                priority=item["priority"],
                escalation_level=normalize_escalation_level(item["escalation_level"]),
                is_archived=item["operational_status"] in ("resolved", "closed"),
                customer_actor_id=item.get("customer_actor_id"),
                customer_telegram_chat_id=item.get("customer_telegram_chat_id"),
            )
            for _, item in matched[:limit]
        ]

    async def hot_task_buckets(self, actor_id, item_limit: int) -> list[HotTaskBucket]:
        # V1 workdesk buckets are operational and deterministic by contract:
        # needs reply, new business, SLA risk, urgent/escalated, and failed delivery.
        async with self._sf() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        select
                            qc.id as case_id,
                            qc.display_number as case_display_number,
                            qc.customer_label as customer_label,
                            qc.customer_actor_id as customer_actor_id,
                            qc.customer_telegram_chat_id as customer_telegram_chat_id,
                            s.status as operational_status,
                            s.waiting_state,
                            s.priority,
                            s.escalation_level,
                            s.assigned_manager_actor_id,
                            s.last_customer_message_at,
                            s.sla_due_at,
                            s.updated_at as ops_updated_at,
                            o.display_number as linked_order_display_number,
                            exists (
                                select 1
                                from ops.quote_case_thread_entries te
                                where te.quote_case_id = s.quote_case_id and te.direction = 'inbound'
                            ) as has_inbound_thread,
                            (
                                select max(a.attempted_at)
                                from ops.reply_delivery_attempts a
                                where a.quote_case_id = s.quote_case_id and a.status = 'failed'
                            ) as last_failed_delivery_at
                        from ops.quote_case_ops_states s
                        join core.quote_cases qc on qc.id = s.quote_case_id
                        left join core.orders o on o.source_quote_case_id = qc.id
                        where s.status in ('new', 'active')
                        """
                    )
                )
            ).all()

        now_ts = datetime.now(timezone.utc).timestamp()
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        raw: list[dict] = []
        for row in rows:
            item = dict(row._mapping)
            item["escalation_level"] = normalize_escalation_level(item.get("escalation_level"))
            item["sla_due_at"] = _as_dt(item.get("sla_due_at"))
            item["last_customer_message_at"] = _as_dt(item.get("last_customer_message_at"))
            item["ops_updated_at"] = _as_dt(item.get("ops_updated_at"))
            item["last_failed_delivery_at"] = _as_dt(item.get("last_failed_delivery_at"))
            raw.append(item)

        def sla_rank(sla_due_at: datetime | None) -> int:
            if not sla_due_at:
                return 2
            due_ts = sla_due_at.timestamp()
            if due_ts <= now_ts:
                return 0
            if due_ts <= now_ts + 1800:
                return 1
            return 2

        def to_item(item: dict, reason: str, *, last_event_at: datetime | None) -> HotTaskItem:
            return HotTaskItem(
                case_id=item["case_id"],
                case_display_number=int(item["case_display_number"]),
                customer_label=item.get("customer_label"),
                reason=reason,
                priority=item["priority"],
                escalation_level=item["escalation_level"],
                waiting_state=item["waiting_state"],
                sla_due_at=item.get("sla_due_at"),
                last_customer_message_at=item.get("last_customer_message_at"),
                last_event_at=last_event_at,
                linked_order_display_number=item.get("linked_order_display_number"),
            )

        # Needs reply now: manager-side waiting with customer activity.
        needs_reply_raw = [
            i
            for i in raw
            if i["assigned_manager_actor_id"] == actor_id and i["waiting_state"] in ("none", "waiting_manager", "waiting_owner")
        ]
        needs_reply_raw.sort(
            key=lambda i: (
                priority_rank(i["priority"]),
                sla_rank(i["sla_due_at"]),
                -escalation_rank(i["escalation_level"]),
                -(i["last_customer_message_at"] or epoch).timestamp(),
                i["case_display_number"],
            )
        )
        needs_reply = [to_item(i, "Customer waiting for manager response.", last_event_at=i["last_customer_message_at"]) for i in needs_reply_raw[:item_limit]]

        # New incoming: real business-relevant new cases only.
        new_business_raw = [
            i
            for i in raw
            if i["operational_status"] == "new"
            and (
                i["last_customer_message_at"] is not None
                or bool(i["customer_actor_id"])
                or i["customer_telegram_chat_id"] is not None
                or bool((i.get("customer_label") or "").strip())
                or i.get("has_inbound_thread", False)
            )
        ]
        new_business_raw.sort(
            key=lambda i: (
                priority_rank(i["priority"]),
                -escalation_rank(i["escalation_level"]),
                -(i["last_customer_message_at"] or i["ops_updated_at"] or epoch).timestamp(),
                i["case_display_number"],
            )
        )
        new_business = [to_item(i, "New incoming case needs triage.", last_event_at=i["last_customer_message_at"] or i["ops_updated_at"]) for i in new_business_raw[:item_limit]]

        # SLA risk: overdue before near-breach.
        sla_risk_raw = [i for i in raw if sla_rank(i["sla_due_at"]) in (0, 1)]
        sla_risk_raw.sort(
            key=lambda i: (
                sla_rank(i["sla_due_at"]),
                priority_rank(i["priority"]),
                -escalation_rank(i["escalation_level"]),
                (i["sla_due_at"] or epoch).timestamp(),
                i["case_display_number"],
            )
        )
        sla_risk = [
            to_item(
                i,
                "SLA overdue." if sla_rank(i["sla_due_at"]) == 0 else "SLA near breach.",
                last_event_at=i["sla_due_at"],
            )
            for i in sla_risk_raw[:item_limit]
        ]

        # Urgent/VIP/escalated: explicit priority then escalation pressure.
        urgent_raw = [i for i in raw if is_high_or_higher_priority(i["priority"]) or is_escalated(i["escalation_level"])]
        urgent_raw.sort(
            key=lambda i: (
                priority_rank(i["priority"]),
                -escalation_rank(i["escalation_level"]),
                sla_rank(i["sla_due_at"]),
                -(i["last_customer_message_at"] or epoch).timestamp(),
                i["case_display_number"],
            )
        )
        urgent = [to_item(i, "Urgent/VIP/escalated handling lane.", last_event_at=i["last_customer_message_at"] or i["ops_updated_at"]) for i in urgent_raw[:item_limit]]

        # Failed delivery: most recent failures first.
        failed_raw = [i for i in raw if i["last_failed_delivery_at"]]
        failed_raw.sort(
            key=lambda i: (
                -(i["last_failed_delivery_at"] or epoch).timestamp(),
                priority_rank(i["priority"]),
                -escalation_rank(i["escalation_level"]),
                i["case_display_number"],
            )
        )
        failed = [
            to_item(i, "Outbound delivery failed; manual recovery required.", last_event_at=i["last_failed_delivery_at"])
            for i in failed_raw[:item_limit]
        ]

        return [
            HotTaskBucket(HotTaskBucketKey.NEEDS_REPLY_NOW, "Needs reply now", "waiting_me", needs_reply),
            HotTaskBucket(HotTaskBucketKey.NEW_BUSINESS, "New incoming", "new_incoming", new_business),
            HotTaskBucket(HotTaskBucketKey.SLA_AT_RISK, "SLA at risk", "sla_risk", sla_risk),
            HotTaskBucket(HotTaskBucketKey.URGENT_ESCALATED, "Urgent / VIP / escalated", "urgent_escalated", urgent),
            HotTaskBucket(HotTaskBucketKey.FAILED_DELIVERY, "Failed delivery", "failed_delivery", failed),
        ]


def _as_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


_MANAGER_ITEM_SOURCE_COLUMNS = {
    "title",
    "display_title",
    "item_title",
    "product_title",
    "name",
    "brand",
    "sku_code",
    "sku",
    "code",
    "selling_unit",
    "unit",
    "min_order",
    "minimum_order_qty",
    "moq",
    "increment",
    "order_increment",
    "step",
    "packaging_context",
    "in_box",
    "units_per_box",
    "box_quantity",
    "shelf_life",
    "country_of_origin",
    "origin",
    "weight",
    "piece_weight",
    "description",
    "is_active",
    "active",
    "in_draft",
    "is_draft",
}


def _first_non_empty(payload: dict, candidates: tuple[str, ...]) -> str | None:
    for key in candidates:
        value = payload.get(key)
        if value is None:
            continue
        text_value = str(value).strip()
        if text_value:
            return text_value
    return None


def _first_bool(payload: dict, candidates: tuple[str, ...]) -> bool | None:
    for key in candidates:
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized in {"true", "t", "1", "yes", "y"}:
            return True
        if normalized in {"false", "f", "0", "no", "n"}:
            return False
    return None


def _build_manager_item_detail(payload: dict) -> ManagerItemDetail | None:
    packaging_context = _first_non_empty(payload, ("packaging_context",))
    in_box = _first_non_empty(payload, ("in_box", "units_per_box", "box_quantity"))
    if not packaging_context and in_box:
        packaging_context = in_box
    detail = ManagerItemDetail(
        title=_first_non_empty(payload, ("display_title", "title", "item_title", "product_title", "name")),
        brand=_first_non_empty(payload, ("brand",)),
        sku_code=_first_non_empty(payload, ("sku_code", "sku", "code")),
        selling_unit=_first_non_empty(payload, ("selling_unit", "unit")),
        min_order=_first_non_empty(payload, ("min_order", "minimum_order_qty", "moq")),
        increment=_first_non_empty(payload, ("increment", "order_increment", "step")),
        packaging_context=packaging_context,
        shelf_life=_first_non_empty(payload, ("shelf_life",)),
        origin=_first_non_empty(payload, ("country_of_origin", "origin")),
        weight=_first_non_empty(payload, ("weight",)),
        piece_weight=_first_non_empty(payload, ("piece_weight",)),
        description=_first_non_empty(payload, ("description",)),
        is_active=_first_bool(payload, ("is_active", "active")),
        in_draft=_first_bool(payload, ("in_draft", "is_draft")),
    )
    if not any(
        (
            detail.title,
            detail.brand,
            detail.sku_code,
            detail.selling_unit,
            detail.min_order,
            detail.increment,
            detail.packaging_context,
            detail.shelf_life,
            detail.origin,
            detail.weight,
            detail.piece_weight,
            detail.description,
            detail.is_active is not None,
            detail.in_draft is not None,
        )
    ):
        return None
    return detail


class SqlCaseRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def _append_assignment_event(
        self,
        session,
        *,
        case_id,
        event_kind: str,
        from_actor_id,
        to_actor_id,
        triggered_by_actor_id,
    ) -> None:
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
                    id, quote_case_id, event_seq, event_kind, from_manager_actor_id, to_manager_actor_id, triggered_by_actor_id, created_at, updated_at
                ) values (
                        :event_id, :case_id, :event_seq, :event_kind, :from_actor_id, :to_actor_id, :triggered_by_actor_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "event_id": str(uuid4()),
                "case_id": case_id,
                "event_seq": next_seq,
                "event_kind": event_kind,
                "from_actor_id": from_actor_id,
                "to_actor_id": to_actor_id,
                "triggered_by_actor_id": triggered_by_actor_id,
            },
        )

    async def get_detail(self, case_id, actor_id):
        async with self._sf() as session:
            head = (
                await session.execute(
                    text(
                        """
                        select qc.id as case_id, qc.display_number as case_display_number, qc.status as commercial_status,
                               ops.status as operational_status, ops.waiting_state, ops.priority, ops.escalation_level, ops.sla_due_at,
                               qc.customer_label as customer_label, qc.customer_actor_id, qc.customer_telegram_chat_id,
                               b.telegram_user_id as customer_telegram_user_id,
                               coalesce(am.display_name, 'Unassigned') as assignment_label,
                               o.display_number as linked_order_display_number,
                               null as linked_order_status,
                               null as linked_order_summary,
                               null as linked_order_pdf_url,
                               null as linked_order_document_label
                        from core.quote_cases qc
                        join ops.quote_case_ops_states ops on ops.quote_case_id=qc.id
                        left join core.actors am on am.id=ops.assigned_manager_actor_id
                        left join core.actor_telegram_bindings b on b.actor_id = qc.customer_actor_id
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
                        select
                            direction,
                            body_text as body,
                            created_at,
                            coalesce(delivery_status, 'not_applicable') as delivery_status,
                            author_role
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
            item_detail = await self._load_item_detail(session, case_id)
        detail = CaseDetail(
            case_id=head.case_id,
            case_display_number=head.case_display_number,
            commercial_status=head.commercial_status,
            operational_status=head.operational_status,
            waiting_state=head.waiting_state,
            priority=head.priority,
            escalation_level=normalize_escalation_level(head.escalation_level),
            assignment_label=head.assignment_label,
            sla_due_at=_as_dt(head.sla_due_at),
            linked_order_display_number=head.linked_order_display_number,
            linked_order_status=head.linked_order_status,
            linked_order_summary=head.linked_order_summary,
            linked_order_pdf_url=head.linked_order_pdf_url,
            linked_order_document_label=head.linked_order_document_label,
            linked_quote_display_number=head.case_display_number,
            customer_label=head.customer_label,
            customer_card=CustomerCard(
                label=head.customer_label,
                actor_id=str(head.customer_actor_id) if head.customer_actor_id is not None else None,
                telegram_chat_id=int(head.customer_telegram_chat_id) if head.customer_telegram_chat_id is not None else None,
                telegram_user_id=int(head.customer_telegram_user_id) if head.customer_telegram_user_id is not None else None,
            ),
            item_detail=item_detail,
        )
        detail.thread_entries = [
            ThreadEntry(
                direction=r.direction,
                body=r.body,
                created_at=_as_dt(r.created_at),
                delivery_status=r.delivery_status,
                author_side=r.author_role,
            )
            for r in reversed(thread_rows)
        ]
        detail.internal_notes = [InternalNote(**r._mapping) for r in reversed(note_rows)]
        if delivery_row:
            detail.last_delivery = DeliverySnapshot(**delivery_row._mapping)
        return detail

    async def _load_item_detail(self, session, case_id) -> ManagerItemDetail | None:
        from_items = await self._load_item_detail_from_table(session, "core", "quote_case_items", "quote_case_id", case_id)
        if from_items:
            return from_items
        return await self._load_item_detail_from_table(session, "core", "quote_cases", "id", case_id)

    async def _load_item_detail_from_table(self, session, schema: str, table: str, key_column: str, key_value) -> ManagerItemDetail | None:
        columns = await self._table_columns(session, schema, table)
        if not columns:
            return None
        if key_column not in columns:
            return None
        projection = sorted(columns.intersection(_MANAGER_ITEM_SOURCE_COLUMNS))
        if not projection:
            return None
        select_sql = ", ".join(projection)
        try:
            row = (
                await session.execute(
                    text(f"select {select_sql} from {schema}.{table} where {key_column}=:key_value limit 1"),
                    {"key_value": key_value},
                )
            ).first()
        except SQLAlchemyError:
            return None
        if not row:
            return None
        payload = dict(row._mapping)
        return _build_manager_item_detail(payload)

    async def _table_columns(self, session, schema: str, table: str) -> set[str]:
        try:
            rows = (await session.execute(text(f"PRAGMA {schema}.table_info('{table}')"))).all()
            if rows:
                return {str(r.name) for r in rows}
        except SQLAlchemyError:
            pass
        try:
            rows = (
                await session.execute(
                    text(
                        """
                        select column_name
                        from information_schema.columns
                        where table_schema = :schema and table_name = :table
                        """
                    ),
                    {"schema": schema, "table": table},
                )
            ).all()
            return {str(r.column_name) for r in rows}
        except SQLAlchemyError:
            return set()

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
            await self._append_assignment_event(
                session,
                case_id=case_id,
                event_kind="claimed",
                from_actor_id=current.assigned_manager_actor_id,
                to_actor_id=actor_id,
                triggered_by_actor_id=actor_id,
            )
            await session.commit()
        return result.rowcount > 0

    async def assign_case(self, case_id, actor_id, target_manager_actor_id) -> bool:
        async with self._sf() as session:
            current = (
                await session.execute(
                    text("select assigned_manager_actor_id from ops.quote_case_ops_states where quote_case_id=:case_id"),
                    {"case_id": case_id},
                )
            ).first()
            if not current:
                return False
            is_reassign = current.assigned_manager_actor_id is not None and current.assigned_manager_actor_id != target_manager_actor_id
            result = await session.execute(
                text(
                    """
                    update ops.quote_case_ops_states
                    set assigned_manager_actor_id=:target_actor_id,
                        assigned_by_actor_id=:actor_id,
                        assigned_at=CURRENT_TIMESTAMP,
                        status='active',
                        waiting_state='waiting_manager',
                        updated_at=CURRENT_TIMESTAMP
                    where quote_case_id=:case_id
                    """
                ),
                {"case_id": case_id, "target_actor_id": target_manager_actor_id, "actor_id": actor_id},
            )
            await self._append_assignment_event(
                session,
                case_id=case_id,
                event_kind="reassigned" if is_reassign else "assigned",
                from_actor_id=current.assigned_manager_actor_id,
                to_actor_id=target_manager_actor_id,
                triggered_by_actor_id=actor_id,
            )
            await session.commit()
        return result.rowcount > 0

    async def unassign_case(self, case_id, actor_id) -> bool:
        async with self._sf() as session:
            current = (
                await session.execute(
                    text("select assigned_manager_actor_id from ops.quote_case_ops_states where quote_case_id=:case_id"),
                    {"case_id": case_id},
                )
            ).first()
            if not current:
                return False
            result = await session.execute(
                text(
                    """
                    update ops.quote_case_ops_states
                    set assigned_manager_actor_id=null,
                        assigned_by_actor_id=:actor_id,
                        assigned_at=CURRENT_TIMESTAMP,
                        status='new',
                        waiting_state='none',
                        updated_at=CURRENT_TIMESTAMP
                    where quote_case_id=:case_id
                    """
                ),
                {"case_id": case_id, "actor_id": actor_id},
            )
            await self._append_assignment_event(
                session,
                case_id=case_id,
                event_kind="unassigned",
                from_actor_id=current.assigned_manager_actor_id,
                to_actor_id=None,
                triggered_by_actor_id=actor_id,
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
                    set escalation_level = :escalation_level,
                        priority = case when priority in ('urgent', 'vip') then priority else 'high' end,
                        assigned_manager_actor_id = :owner_actor_id,
                        assigned_by_actor_id = :actor_id,
                        assigned_at = CURRENT_TIMESTAMP,
                        waiting_state = 'waiting_owner',
                        status = 'active',
                        updated_at = CURRENT_TIMESTAMP
                    where quote_case_id = :case_id
                    """
                ),
                {
                    "case_id": case_id,
                    "owner_actor_id": owner_row.actor_id,
                    "actor_id": actor_id,
                    "escalation_level": ESCALATION_OWNER_ATTENTION,
                },
            )
            await self._append_assignment_event(
                session,
                case_id=case_id,
                event_kind="escalated_to_owner",
                from_actor_id=current.assigned_manager_actor_id,
                to_actor_id=owner_row.actor_id,
                triggered_by_actor_id=actor_id,
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

    async def update_priority(self, case_id, actor_id, priority: str) -> bool:
        _ = actor_id
        if priority not in {"normal", "high", "urgent", "vip"}:
            return False
        async with self._sf() as session:
            result = await session.execute(
                text(
                    """
                    update ops.quote_case_ops_states
                    set priority=:priority,
                        updated_at=CURRENT_TIMESTAMP
                    where quote_case_id=:case_id
                    """
                ),
                {"case_id": case_id, "priority": priority},
            )
            await session.commit()
        return result.rowcount > 0


class SqlNotificationRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    async def poll_events(self) -> list[NotificationEvent]:
        async with self._sf() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        with visible_business as (
                            select
                                s.quote_case_id,
                                qc.display_number as case_display_number,
                                s.updated_at
                            from ops.quote_case_ops_states s
                            join core.quote_cases qc on qc.id = s.quote_case_id
                            where s.status = 'new'
                              and """
                        + BUSINESS_RELEVANCE_SQL
                        + """
                        ),
                        first_visible_case as (
                            select
                                vb.quote_case_id,
                                vb.case_display_number
                            from visible_business vb
                            order by vb.updated_at asc, vb.quote_case_id asc
                            limit 1
                        ),
                        case_visible_batch as (
                            select
                                case
                                    when count(*) = 0 then null
                                    else
                                        'case_visible_batch:' ||
                                        coalesce(cast(max(updated_at) as text), '') || ':' ||
                                        cast(count(*) as text) || ':' ||
                                        coalesce(cast((select quote_case_id from first_visible_case) as text), '')
                                end as event_key,
                                'case_visible_batch' as kind,
                                (select quote_case_id from first_visible_case) as case_id,
                                (select case_display_number from first_visible_case) as case_display_number,
                                cast(null as uuid) as assigned_manager_actor_id,
                                case
                                    when count(*) = 1 then
                                        '1 new incoming case: #' || cast((select case_display_number from first_visible_case) as text)
                                    when count(*) > 1 then
                                        cast(count(*) as text) || ' new incoming cases. Earliest: #' || cast((select case_display_number from first_visible_case) as text)
                                    else null
                                end as summary
                            from visible_business
                        )
                        select event_key, kind, case_id, case_display_number, assigned_manager_actor_id, summary
                        from case_visible_batch
                        where event_key is not null
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
