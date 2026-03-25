from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.models import CaseDetail, ManagerActor, PresenceStatus, QueueItem


class ActorRepository(Protocol):
    async def by_telegram_user_id(self, telegram_user_id: int) -> ManagerActor | None: ...


class PresenceRepository(Protocol):
    async def get_status(self, actor_id: UUID) -> PresenceStatus: ...

    async def set_status(self, actor_id: UUID, status: PresenceStatus) -> None: ...


class QueueRepository(Protocol):
    async def summary_counts(self, actor_id: UUID) -> dict[str, int]: ...

    async def list_queue(self, queue_key: str, actor_id: UUID, offset: int, limit: int) -> list[QueueItem]: ...


class CaseRepository(Protocol):
    async def get_detail(self, case_id: UUID, actor_id: UUID) -> CaseDetail | None: ...

    async def claim_case(self, case_id: UUID, actor_id: UUID) -> bool: ...
