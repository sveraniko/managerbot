from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
from uuid import uuid4

from app.models import CaseDetail, HotTaskBucket, HotTaskBucketKey, HotTaskItem, ManagerActor, NotificationEvent, PresenceStatus, QueueFilters, QueueItem, SearchResultItem, ThreadEntry
from app.services.priority import is_high_or_higher_priority, is_top_tier_priority, priority_rank


class FakeActorRepository:
    def __init__(self, actors: dict[int, ManagerActor]) -> None:
        self.actors = actors

    async def by_telegram_user_id(self, telegram_user_id: int):
        return self.actors.get(telegram_user_id)

    async def list_internal_recipients(self) -> list[tuple[str, int, str, str]]:
        return [
            (str(actor.actor_id), actor.telegram_user_id, actor.role.value, PresenceStatus.ONLINE.value)
            for actor in self.actors.values()
        ]


class FakePresenceRepository:
    def __init__(self) -> None:
        self._states: dict[UUID, PresenceStatus] = {}

    async def get_status(self, actor_id: UUID):
        return self._states.get(actor_id, PresenceStatus.OFFLINE)

    async def set_status(self, actor_id: UUID, status: PresenceStatus) -> None:
        self._states[actor_id] = status


class FakeQueueRepository:
    def __init__(self, queues: dict[str, list[QueueItem]]) -> None:
        self.queues = queues

    async def summary_counts(self, actor_id: UUID):
        return {k: len(v) for k, v in self.queues.items()}

    async def list_queue(self, queue_key: str, actor_id: UUID, offset: int, limit: int, filters: QueueFilters | None = None):
        _ = actor_id
        items = list(self.queues.get(queue_key, []))
        if filters:
            items = _apply_filters(items, actor_id, filters)
        return items[offset : offset + limit]

    async def hot_task_buckets(self, actor_id: UUID, item_limit: int) -> list[HotTaskBucket]:
        _ = actor_id
        buckets: list[HotTaskBucket] = []
        mappings = [
            (HotTaskBucketKey.NEEDS_REPLY_NOW, "Needs reply now", "waiting_me"),
            (HotTaskBucketKey.NEW_BUSINESS, "New business", "new"),
            (HotTaskBucketKey.SLA_AT_RISK, "SLA at risk", "sla_risk"),
            (HotTaskBucketKey.URGENT_ESCALATED, "Urgent / VIP / escalated", "urgent_escalated"),
            (HotTaskBucketKey.FAILED_DELIVERY, "Failed delivery", "failed_delivery"),
        ]
        for key, title, queue_key in mappings:
            items = [
                HotTaskItem(
                    case_id=item.case_id,
                    case_display_number=item.case_display_number,
                    customer_label=item.customer_label,
                    reason=f"{title.lower()} signal",
                    priority=item.priority,
                    escalation_level=item.escalation_level,
                    waiting_state=item.waiting_state,
                    sla_due_at=item.sla_due_at,
                    last_customer_message_at=item.last_customer_message_at,
                    last_event_at=item.last_customer_message_at,
                )
                for item in self.queues.get(queue_key, [])[:item_limit]
            ]
            buckets.append(HotTaskBucket(key=key, title=title, queue_key=queue_key, items=items))
        return buckets

    async def search_cases(self, actor_id: UUID, query: str, limit: int, filters: QueueFilters | None = None) -> list[SearchResultItem]:
        needle = query.strip().lower()
        matches: list[SearchResultItem] = []
        for queue_items in self.queues.values():
            for item in queue_items:
                if needle and needle not in str(item.case_display_number) and needle not in (item.customer_label or "").lower():
                    continue
                if filters and item not in _apply_filters([item], actor_id, filters):
                    continue
                matches.append(
                    SearchResultItem(
                        case_id=item.case_id,
                        case_display_number=item.case_display_number,
                        linked_order_display_number=None,
                        customer_label=item.customer_label,
                        operational_status=item.operational_status,
                        waiting_state=item.waiting_state,
                        priority=item.priority,
                        escalation_level=item.escalation_level,
                        is_archived=item.is_archived,
                    )
                )
        deduped: dict[UUID, SearchResultItem] = {m.case_id: m for m in matches}
        return sorted(
            deduped.values(),
            key=lambda i: (
                0 if not i.is_archived else 1,
                priority_rank(i.priority),
                -int(i.escalation_level),
                i.case_display_number,
                i.case_id.hex,
            ),
        )[:limit]


class FakeCaseRepository:
    def __init__(self, details: dict[UUID, CaseDetail]) -> None:
        self.details = details

    async def get_detail(self, case_id: UUID, actor_id: UUID):
        return self.details.get(case_id)

    async def claim_case(self, case_id: UUID, actor_id: UUID):
        detail = self.details.get(case_id)
        if not detail:
            return False
        detail.assignment_label = "Assigned to me"
        detail.operational_status = "active"
        detail.waiting_state = "waiting_manager"
        detail.thread_entries.append(ThreadEntry(direction="system", body="Case claimed", created_at=datetime.now(timezone.utc)))
        return True

    async def assign_case(self, case_id: UUID, actor_id: UUID, target_manager_actor_id: UUID):
        _ = (actor_id, target_manager_actor_id)
        detail = self.details.get(case_id)
        if not detail:
            return False
        detail.assignment_label = "Assigned"
        detail.operational_status = "active"
        detail.waiting_state = "waiting_manager"
        return True

    async def unassign_case(self, case_id: UUID, actor_id: UUID):
        _ = actor_id
        detail = self.details.get(case_id)
        if not detail:
            return False
        detail.assignment_label = "Unassigned"
        detail.operational_status = "new"
        detail.waiting_state = "none"
        return True

    async def escalate_to_owner(self, case_id: UUID, actor_id: UUID):
        detail = self.details.get(case_id)
        if not detail:
            return False
        detail.escalation_level = 1
        if detail.priority not in ("urgent", "vip"):
            detail.priority = "high"
        detail.waiting_state = "waiting_owner"
        detail.assignment_label = "Owner"
        return True

    async def add_internal_note(self, case_id: UUID, actor_id: UUID, body_text: str):
        detail = self.details.get(case_id)
        if not detail:
            return False
        from app.models import InternalNote

        detail.internal_notes.append(InternalNote(body=body_text, author_label="Assigned to me", created_at=datetime.now(timezone.utc)))
        return True

    async def create_outbound_reply(self, case_id: UUID, actor_id: UUID, body_text: str):
        detail = self.details.get(case_id)
        if not detail:
            return None
        entry_id = str(uuid4())
        attempt_id = str(uuid4())
        detail.thread_entries.append(
            ThreadEntry(direction="outbound", body=body_text, created_at=datetime.now(timezone.utc), delivery_status="pending")
        )
        return entry_id, attempt_id, 555001

    async def mark_reply_delivery(
        self,
        thread_entry_id: str,
        attempt_id: str,
        status: str,
        *,
        telegram_message_id: int | None,
        error_message: str | None,
    ) -> None:
        _ = (thread_entry_id, attempt_id, telegram_message_id, error_message)
        for detail in self.details.values():
            if detail.thread_entries:
                detail.thread_entries[-1].delivery_status = status

    async def update_priority(self, case_id: UUID, actor_id: UUID, priority: str) -> bool:
        _ = actor_id
        detail = self.details.get(case_id)
        if not detail:
            return False
        detail.priority = priority
        return True


def _apply_filters(items: list[QueueItem], actor_id: UUID, filters: QueueFilters) -> list[QueueItem]:
    filtered = items
    if filters.assignment_scope == "mine":
        filtered = [i for i in filtered if i.assigned_manager_actor_id == actor_id]
    elif filters.assignment_scope == "unassigned":
        filtered = [i for i in filtered if i.assigned_manager_actor_id is None]
    if filters.waiting_scope == "waiting_manager":
        filtered = [i for i in filtered if i.waiting_state in ("none", "waiting_manager", "waiting_owner")]
    elif filters.waiting_scope == "waiting_customer":
        filtered = [i for i in filtered if i.waiting_state == "waiting_customer"]
    if filters.priority_scope == "high_or_urgent":
        filtered = [i for i in filtered if is_high_or_higher_priority(i.priority)]
    elif filters.priority_scope == "urgent_or_vip":
        filtered = [i for i in filtered if is_top_tier_priority(i.priority)]
    elif filters.priority_scope == "vip":
        filtered = [i for i in filtered if i.priority == "vip"]
    if filters.escalation_scope == "escalated":
        filtered = [i for i in filtered if i.escalation_level > 0]
    if filters.lifecycle_scope == "active":
        filtered = [i for i in filtered if not i.is_archived]
    elif filters.lifecycle_scope == "archive":
        filtered = [i for i in filtered if i.is_archived]
    return filtered


class FakeNotificationRepository:
    def __init__(self, events: list[NotificationEvent]) -> None:
        self.events = events

    async def poll_events(self) -> list[NotificationEvent]:
        return list(self.events)
