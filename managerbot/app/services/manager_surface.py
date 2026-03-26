from __future__ import annotations

from app.models import CaseDetail, ManagerActor, PresenceStatus, QueueItem
from app.repositories.contracts import CaseRepository, PresenceRepository, QueueRepository
from app.services.ai_reader import AIReaderResult, AIReaderService
from app.services.ai_recommender import AIRecommendationResult, AIRecommenderService
from app.services.delivery import CustomerDeliveryGateway
from app.services.sla import SlaService
from app.state.manager_session import ManagerSessionState


class ManagerSurfaceService:
    def __init__(
        self,
        queue_repo: QueueRepository,
        case_repo: CaseRepository,
        presence_repo: PresenceRepository,
        delivery_gateway: CustomerDeliveryGateway,
        ai_reader: AIReaderService | None = None,
        ai_recommender: AIRecommenderService | None = None,
        page_size: int = 5,
        sla_service: SlaService | None = None,
        low_confidence_threshold: float = 0.65,
    ) -> None:
        self._queue_repo = queue_repo
        self._case_repo = case_repo
        self._presence_repo = presence_repo
        self._delivery_gateway = delivery_gateway
        self._ai_reader = ai_reader
        self._ai_recommender = ai_recommender
        self._page_size = page_size
        self._sla_service = sla_service or SlaService()
        self._low_confidence_threshold = low_confidence_threshold

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

    async def escalate_to_owner(self, actor: ManagerActor, case_id) -> bool:
        return await self._case_repo.escalate_to_owner(case_id, actor.actor_id)

    def case_sla_state(self, detail: CaseDetail) -> str:
        return self._sla_service.classify(detail.sla_due_at)

    async def save_internal_note(self, actor: ManagerActor, case_id, body_text: str) -> bool:
        return await self._case_repo.add_internal_note(case_id, actor.actor_id, body_text)

    async def send_reply(self, actor: ManagerActor, case_id, body_text: str) -> str:
        created = await self._case_repo.create_outbound_reply(case_id, actor.actor_id, body_text)
        if not created:
            return "Reply could not be sent: missing customer delivery target."
        thread_entry_id, attempt_id, chat_id = created
        result = await self._delivery_gateway.send_text(chat_id, body_text)
        if result.ok:
            await self._case_repo.mark_reply_delivery(
                thread_entry_id,
                attempt_id,
                "sent",
                telegram_message_id=result.telegram_message_id,
                error_message=None,
            )
            return "Reply sent to customer."
        await self._case_repo.mark_reply_delivery(
            thread_entry_id,
            attempt_id,
            "failed",
            telegram_message_id=None,
            error_message=result.error_message,
        )
        return "Reply saved, but delivery failed."

    @property
    def low_confidence_threshold(self) -> float:
        return self._low_confidence_threshold

    async def analyze_case_reader(self, detail: CaseDetail, *, force_refresh: bool = False) -> AIReaderResult:
        if not self._ai_reader:
            return AIReaderResult(ok=False, error_message="AI reader is disabled.")
        return await self._ai_reader.analyze_case(detail, sla_state=self.case_sla_state(detail), force_refresh=force_refresh)

    async def recommend_case(self, detail: CaseDetail, *, force_refresh: bool = False) -> AIRecommendationResult:
        if not self._ai_reader or not self._ai_recommender:
            return AIRecommendationResult(ok=False, error_message="AI recommender is disabled.")
        packet = self._ai_reader.build_packet(detail, sla_state=self.case_sla_state(detail))
        return await self._ai_recommender.recommend(packet, force_refresh=force_refresh)
