import asyncio
from uuid import uuid4

from app.models import ManagerActor, PresenceStatus, SystemRole
from app.repositories.fakes import FakeCaseRepository, FakePresenceRepository, FakeQueueRepository
from app.services.manager_surface import ManagerSurfaceService


def test_presence_toggle_updates_backend_state() -> None:
    actor = ManagerActor(uuid4(), 1, "Manager", SystemRole.MANAGER)
    presence = FakePresenceRepository()
    service = ManagerSurfaceService(FakeQueueRepository({}), FakeCaseRepository({}), presence)

    new_status = asyncio.run(service.toggle_presence(actor))
    assert new_status == PresenceStatus.AWAY
    assert asyncio.run(presence.get_status(actor.actor_id)) == PresenceStatus.AWAY

    second = asyncio.run(service.toggle_presence(actor))
    assert second == PresenceStatus.ONLINE
