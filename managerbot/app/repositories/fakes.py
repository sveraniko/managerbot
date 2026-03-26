from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
from uuid import uuid4

from app.models import CaseDetail, ManagerActor, PresenceStatus, QueueItem, ThreadEntry


class FakeActorRepository:
    def __init__(self, actors: dict[int, ManagerActor]) -> None:
        self.actors = actors

    async def by_telegram_user_id(self, telegram_user_id: int):
        return self.actors.get(telegram_user_id)


class FakePresenceRepository:
    def __init__(self) -> None:
        self._states: dict[UUID, PresenceStatus] = {}

    async def get_status(self, actor_id: UUID):
        return self._states.get(actor_id, PresenceStatus.ONLINE)

    async def set_status(self, actor_id: UUID, status: PresenceStatus) -> None:
        self._states[actor_id] = status


class FakeQueueRepository:
    def __init__(self, queues: dict[str, list[QueueItem]]) -> None:
        self.queues = queues

    async def summary_counts(self, actor_id: UUID):
        return {k: len(v) for k, v in self.queues.items()}

    async def list_queue(self, queue_key: str, actor_id: UUID, offset: int, limit: int):
        return self.queues.get(queue_key, [])[offset : offset + limit]


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
