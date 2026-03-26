from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models import NotificationEvent, PresenceStatus
from app.services.notifications import ManagerNotificationService, NotificationPolicy, run_notification_loop
from app.services.sla import SlaService


class FakeRecipients:
    def __init__(self, rows):
        self.rows = rows

    async def list_internal_recipients(self):
        return self.rows


class FakeEventsRepo:
    def __init__(self, events):
        self.events = events

    async def poll_events(self):
        return list(self.events)


class FakeSink:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send(self, telegram_user_id: int, text: str) -> None:
        self.sent.append((telegram_user_id, text))


class FakeDedupe:
    def __init__(self):
        self.keys: set[str] = set()

    async def seen(self, key: str) -> bool:
        return key in self.keys

    async def mark(self, key: str, ttl_seconds: int) -> None:
        _ = ttl_seconds
        self.keys.add(key)


def test_sla_classification_states() -> None:
    service = SlaService()
    now = datetime.now(timezone.utc)

    assert service.classify(None, now=now) == "healthy"
    assert service.classify(now + timedelta(minutes=20), now=now) == "near_breach"
    assert service.classify(now - timedelta(minutes=1), now=now) == "overdue"


def test_notification_dedupe_new_case_once() -> None:
    event = NotificationEvent(
        event_key="case_visible:c1:1",
        kind="case_visible",
        case_id=uuid4(),
        case_display_number=101,
        assigned_manager_actor_id=None,
    )
    recipients = FakeRecipients([
        ("owner", 1, "OWNER", PresenceStatus.ONLINE.value),
        ("m1", 2, "MANAGER", PresenceStatus.ONLINE.value),
    ])
    sink = FakeSink()
    dedupe = FakeDedupe()
    service = ManagerNotificationService(FakeEventsRepo([event]), recipients, sink, dedupe, NotificationPolicy(dedupe_ttl_seconds=10))

    assert asyncio.run(service.run_once()) == 2
    assert asyncio.run(service.run_once()) == 0


def test_case_visible_does_not_target_manager_without_presence_row() -> None:
    event = NotificationEvent(
        event_key="case_visible:c2:1",
        kind="case_visible",
        case_id=uuid4(),
        case_display_number=102,
        assigned_manager_actor_id=None,
    )
    recipients = FakeRecipients([
        ("owner", 1, "OWNER", PresenceStatus.ONLINE.value),
        ("m1", 2, "MANAGER", PresenceStatus.OFFLINE.value),
    ])
    sink = FakeSink()
    service = ManagerNotificationService(FakeEventsRepo([event]), recipients, sink, FakeDedupe(), NotificationPolicy())

    asyncio.run(service.run_once())
    assert {uid for uid, _ in sink.sent} == {1}

def test_new_inbound_busy_manager_falls_back_to_owner() -> None:
    assigned_actor_id = str(uuid4())
    event = NotificationEvent(
        event_key="new_inbound:t1",
        kind="new_inbound",
        case_id=uuid4(),
        case_display_number=500,
        assigned_manager_actor_id=assigned_actor_id,
        summary="Need help",
    )
    recipients = FakeRecipients([
        ("owner", 1, "OWNER", PresenceStatus.ONLINE.value),
        (assigned_actor_id, 2, "MANAGER", PresenceStatus.BUSY.value),
    ])
    sink = FakeSink()
    service = ManagerNotificationService(FakeEventsRepo([event]), recipients, sink, FakeDedupe(), NotificationPolicy())

    asyncio.run(service.run_once())
    notified_ids = {item[0] for item in sink.sent}
    assert notified_ids == {1, 2}


def test_assigned_to_me_and_failed_delivery_notifications() -> None:
    assigned_actor_id = str(uuid4())
    events = [
        NotificationEvent("assigned_to_me:a1", "assigned_to_me", uuid4(), 200, assigned_actor_id),
        NotificationEvent("delivery_failed:d1", "delivery_failed", uuid4(), 200, assigned_actor_id, summary="telegram error"),
    ]
    recipients = FakeRecipients([
        ("owner", 1, "OWNER", PresenceStatus.ONLINE.value),
        (assigned_actor_id, 2, "MANAGER", PresenceStatus.OFFLINE.value),
    ])
    sink = FakeSink()
    service = ManagerNotificationService(FakeEventsRepo(events), recipients, sink, FakeDedupe(), NotificationPolicy())

    asyncio.run(service.run_once())
    assert any(uid == 2 and "assigned to you" in text.lower() for uid, text in sink.sent)
    assert any(uid == 1 and "delivery failed" in text.lower() for uid, text in sink.sent)


def test_notification_loop_stops_cleanly() -> None:
    async def run() -> None:
        stop_event = asyncio.Event()
        service = ManagerNotificationService(FakeEventsRepo([]), FakeRecipients([]), FakeSink(), FakeDedupe(), NotificationPolicy())
        task = asyncio.create_task(run_notification_loop(service, poll_seconds=1, stop_event=stop_event))
        await asyncio.sleep(0.05)
        stop_event.set()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(run())
