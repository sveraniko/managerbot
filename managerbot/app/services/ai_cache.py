from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class AICacheEntry:
    expires_at: datetime
    payload: dict[str, Any]


class InMemoryAICache:
    """Small process-local TTL cache for AI reader/recommender outputs."""

    def __init__(self, ttl_seconds: int, max_entries: int = 256) -> None:
        self._ttl_seconds = max(0, ttl_seconds)
        self._max_entries = max_entries
        self._store: dict[str, AICacheEntry] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        if self._ttl_seconds <= 0:
            return None
        entry = self._store.get(key)
        if not entry:
            return None
        now = datetime.now(timezone.utc)
        if entry.expires_at <= now:
            self._store.pop(key, None)
            return None
        logger.info("ai_cache_hit", cache_key=key)
        return entry.payload

    def set(self, key: str, payload: dict[str, Any]) -> None:
        if self._ttl_seconds <= 0:
            return
        if len(self._store) >= self._max_entries:
            oldest_key = min(self._store.items(), key=lambda kv: kv[1].expires_at)[0]
            self._store.pop(oldest_key, None)
        self._store[key] = AICacheEntry(
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self._ttl_seconds),
            payload=payload,
        )

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
