from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

import structlog

from app.models import NotificationEvent, PresenceStatus

logger = structlog.get_logger(__name__)


class NotificationRepository(Protocol):
    async def poll_events(self) -> list[NotificationEvent]: ...


class RecipientDirectory(Protocol):
    async def list_internal_recipients(self) -> list[tuple[str, int, str, str]]: ...


class NotificationSink(Protocol):
    async def send(self, telegram_user_id: int, text: str) -> None: ...


class NotificationDedupeStore(Protocol):
    async def seen(self, key: str) -> bool: ...

    async def mark(self, key: str, ttl_seconds: int) -> None: ...


class RedisNotificationDedupeStore:
    def __init__(self, redis, prefix: str = "managerbot:notify") -> None:
        self._redis = redis
        self._prefix = prefix

    def _key(self, event_key: str) -> str:
        return f"{self._prefix}:{event_key}"

    async def seen(self, key: str) -> bool:
        return bool(await self._redis.get(self._key(key)))

    async def mark(self, key: str, ttl_seconds: int) -> None:
        await self._redis.set(self._key(key), "1", ex=ttl_seconds)


@dataclass(slots=True)
class NotificationPolicy:
    dedupe_ttl_seconds: int = 3600


class ManagerNotificationService:
    def __init__(
        self,
        events_repo: NotificationRepository,
        recipients: RecipientDirectory,
        sink: NotificationSink,
        dedupe: NotificationDedupeStore,
        policy: NotificationPolicy,
    ) -> None:
        self._events = events_repo
        self._recipients = recipients
        self._sink = sink
        self._dedupe = dedupe
        self._policy = policy

    async def run_once(self) -> int:
        events = await self._events.poll_events()
        recipients = await self._recipients.list_internal_recipients()
        recipients_by_actor = {r[0]: r for r in recipients}
        owner_ids = [r[1] for r in recipients if r[2] == "OWNER"]
        sent = 0
        for event in events:
            if await self._dedupe.seen(event.event_key):
                continue
            target_ids = self._targets_for_event(event, recipients_by_actor, owner_ids)
            if not target_ids:
                await self._dedupe.mark(event.event_key, self._policy.dedupe_ttl_seconds)
                continue
            text = self._render_event(event)
            for telegram_id in sorted(target_ids):
                await self._sink.send(telegram_id, text)
                sent += 1
            await self._dedupe.mark(event.event_key, self._policy.dedupe_ttl_seconds)
        return sent

    def _targets_for_event(
        self,
        event: NotificationEvent,
        recipients_by_actor: dict[str, tuple[str, int, str, str]],
        owner_ids: list[int],
    ) -> set[int]:
        targets: set[int] = set()
        assigned = recipients_by_actor.get(str(event.assigned_manager_actor_id)) if event.assigned_manager_actor_id else None
        assigned_presence = PresenceStatus(assigned[3]) if assigned else PresenceStatus.OFFLINE

        if event.kind == "case_visible":
            targets.update(owner_ids)
            targets.update(r[1] for r in recipients_by_actor.values() if r[2] == "MANAGER" and r[3] == PresenceStatus.ONLINE.value)
        elif event.kind == "new_inbound":
            if assigned:
                targets.add(assigned[1])
            if not assigned or assigned_presence in {PresenceStatus.BUSY, PresenceStatus.AWAY, PresenceStatus.OFFLINE}:
                targets.update(owner_ids)
        elif event.kind == "assigned_to_me":
            if assigned:
                targets.add(assigned[1])
        elif event.kind == "delivery_failed":
            if assigned:
                targets.add(assigned[1])
            if not assigned or assigned_presence == PresenceStatus.OFFLINE:
                targets.update(owner_ids)
        return targets

    def _render_event(self, event: NotificationEvent) -> str:
        if event.kind == "case_visible":
            return f"New case visible: Case #{event.case_display_number}. Open queue: New/Unassigned lane."
        if event.kind == "new_inbound":
            suffix = f" — {event.summary}" if event.summary else ""
            return f"New customer message on Case #{event.case_display_number}{suffix}"
        if event.kind == "assigned_to_me":
            return f"Case #{event.case_display_number} is assigned to you. Open Assigned to me lane."
        if event.kind == "delivery_failed":
            suffix = f" ({event.summary})" if event.summary else ""
            return f"Delivery failed for Case #{event.case_display_number}{suffix}. Reopen case and retry manually."
        return f"Case #{event.case_display_number} updated."


class ManagerBotNotificationSink:
    def __init__(self, bot) -> None:
        self._bot = bot

    async def send(self, telegram_user_id: int, text: str) -> None:
        await self._bot.send_message(chat_id=telegram_user_id, text=text)


async def run_notification_loop(service: ManagerNotificationService, poll_seconds: int, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            sent = await service.run_once()
            if sent:
                logger.info("manager_notifications_sent", sent=sent)
        except Exception as exc:  # pragma: no cover
            logger.exception("manager_notification_loop_failed", error=str(exc))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            continue
