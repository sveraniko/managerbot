from __future__ import annotations

from app.models import CaseDetail, ManagerActor, PresenceStatus, QueueItem
from app.repositories.contracts import CaseRepository, PresenceRepository, QueueRepository
from app.state.manager_session import ManagerSessionState


class ManagerSurfaceService:
    def __init__(self, queue_repo: QueueRepository, case_repo: CaseRepository, presence_repo: PresenceRepository, page_size: int = 5) -> None:
        self._queue_repo = queue_repo
        self._case_repo = case_repo
        self._presence_repo = presence_repo
        self._page_size = page_size

    async def hub_view(self, actor: ManagerActor) -> tuple[PresenceStatus, dict[str, int]]:
        presence = await self._presence_repo.get_status(actor.actor_id)
        counts = await self._queue_repo.summary_counts(actor.actor_id)
        return presence, counts

    async def queue_page(self, actor: ManagerActor, state: ManagerSessionState) -> list[QueueItem]:
        if not state.queue_key:
            return []
        return await self._queue_repo.list_queue(state.queue_key, actor.actor_id, state.queue_offset, self._page_size)

    async def case_detail(self, actor: ManagerActor, case_id) -> CaseDetail | None:
        return await self._case_repo.get_detail(case_id, actor.actor_id)

    async def toggle_presence(self, actor: ManagerActor) -> PresenceStatus:
        current = await self._presence_repo.get_status(actor.actor_id)
        nxt = PresenceStatus.AWAY if current == PresenceStatus.ONLINE else PresenceStatus.ONLINE
        await self._presence_repo.set_status(actor.actor_id, nxt)
        return nxt

    async def claim_case(self, actor: ManagerActor, case_id) -> bool:
        return await self._case_repo.claim_case(case_id, actor.actor_id)
