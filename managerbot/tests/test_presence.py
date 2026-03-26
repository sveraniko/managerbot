import asyncio
from uuid import uuid4

from app.models import ManagerActor, PresenceStatus, SystemRole
from app.repositories.fakes import FakeCaseRepository, FakePresenceRepository, FakeQueueRepository
from app.services.delivery import DeliveryResult
from app.services.manager_surface import ManagerSurfaceService


class FakeDeliveryGateway:
    async def send_text(self, chat_id: int, text: str) -> DeliveryResult:
        _ = (chat_id, text)
        return DeliveryResult(ok=True, telegram_message_id=1)


def test_presence_toggle_updates_backend_state() -> None:
    actor = ManagerActor(uuid4(), 1, "Manager", SystemRole.MANAGER)
    presence = FakePresenceRepository()
    service = ManagerSurfaceService(
        FakeQueueRepository({}),
        FakeCaseRepository({}),
        presence,
        delivery_gateway=FakeDeliveryGateway(),
    )

    status_before = asyncio.run(presence.get_status(actor.actor_id))
    assert status_before == PresenceStatus.OFFLINE

    first = asyncio.run(service.toggle_presence(actor))
    assert first == PresenceStatus.ONLINE
    assert asyncio.run(presence.get_status(actor.actor_id)) == PresenceStatus.ONLINE

    second = asyncio.run(service.toggle_presence(actor))
    assert second == PresenceStatus.AWAY
    assert asyncio.run(presence.get_status(actor.actor_id)) == PresenceStatus.AWAY


def test_hub_view_uses_offline_default_presence() -> None:
    actor = ManagerActor(uuid4(), 1, "Manager", SystemRole.MANAGER)
    presence = FakePresenceRepository()
    service = ManagerSurfaceService(
        FakeQueueRepository({}),
        FakeCaseRepository({}),
        presence,
        delivery_gateway=FakeDeliveryGateway(),
    )

    status, counts = asyncio.run(service.hub_view(actor))
    assert status == PresenceStatus.OFFLINE
    assert counts == {}
