from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Protocol
from uuid import UUID

from typing import Any

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - optional for test env
    Redis = Any


@dataclass(slots=True)
class ManagerSessionState:
    panel_key: str = "hub:home"
    back_panel_key: str | None = None
    queue_key: str | None = None
    selected_case_id: UUID | None = None
    queue_offset: int = 0
    compose_mode: str | None = None
    compose_case_id: UUID | None = None
    compose_draft_text: str | None = None


class ManagerSessionStore(Protocol):
    async def get(self, telegram_user_id: int) -> ManagerSessionState: ...

    async def set(self, telegram_user_id: int, state: ManagerSessionState) -> None: ...


class RedisManagerSessionStore:
    def __init__(self, redis: Redis, prefix: str = "managerbot:session") -> None:
        self._redis = redis
        self._prefix = prefix

    def _key(self, telegram_user_id: int) -> str:
        return f"{self._prefix}:{telegram_user_id}"

    async def get(self, telegram_user_id: int) -> ManagerSessionState:
        raw = await self._redis.get(self._key(telegram_user_id))
        if not raw:
            return ManagerSessionState()
        payload = json.loads(raw)
        if payload.get("selected_case_id"):
            payload["selected_case_id"] = UUID(payload["selected_case_id"])
        if payload.get("compose_case_id"):
            payload["compose_case_id"] = UUID(payload["compose_case_id"])
        return ManagerSessionState(**payload)

    async def set(self, telegram_user_id: int, state: ManagerSessionState) -> None:
        payload = asdict(state)
        if payload["selected_case_id"]:
            payload["selected_case_id"] = str(payload["selected_case_id"])
        if payload["compose_case_id"]:
            payload["compose_case_id"] = str(payload["compose_case_id"])
        await self._redis.set(self._key(telegram_user_id), json.dumps(payload))


class InMemoryManagerSessionStore:
    def __init__(self) -> None:
        self._state: dict[int, ManagerSessionState] = {}

    async def get(self, telegram_user_id: int) -> ManagerSessionState:
        return self._state.get(telegram_user_id, ManagerSessionState())

    async def set(self, telegram_user_id: int, state: ManagerSessionState) -> None:
        self._state[telegram_user_id] = state
