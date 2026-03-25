import asyncio
from uuid import uuid4

from app.models import ManagerActor, SystemRole
from app.repositories.fakes import FakeActorRepository
from app.services.access import AccessService


def test_unauthorized_denied() -> None:
    service = AccessService(FakeActorRepository({}))
    actor = asyncio.run(service.resolve_authorized_actor(100))
    assert actor is None


def test_owner_or_manager_allowed() -> None:
    manager = ManagerActor(uuid4(), 10, "M", SystemRole.MANAGER)
    owner = ManagerActor(uuid4(), 11, "O", SystemRole.OWNER)
    service = AccessService(FakeActorRepository({10: manager, 11: owner}))
    assert asyncio.run(service.resolve_authorized_actor(10)) == manager
    assert asyncio.run(service.resolve_authorized_actor(11)) == owner
