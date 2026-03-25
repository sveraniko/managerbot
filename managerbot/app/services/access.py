from app.models import SystemRole
from app.repositories.contracts import ActorRepository


class AccessService:
    def __init__(self, actors: ActorRepository) -> None:
        self._actors = actors

    async def resolve_authorized_actor(self, telegram_user_id: int):
        actor = await self._actors.by_telegram_user_id(telegram_user_id)
        if not actor:
            return None
        if actor.role not in {SystemRole.OWNER, SystemRole.MANAGER}:
            return None
        return actor
