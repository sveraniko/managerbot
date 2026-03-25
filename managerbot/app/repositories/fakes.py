from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

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
        detail.waiting_state = "manager"
        detail.thread_entries.append(ThreadEntry(direction="system", body="Case claimed", created_at=datetime.now(timezone.utc)))
        return True
