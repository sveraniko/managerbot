import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.models import (
    CaseDetail,
    HotTaskBucket,
    HotTaskBucketKey,
    HotTaskItem,
    ManagerActor,
    PresenceStatus,
    QueueItem,
    SystemRole,
    ThreadEntry,
)
from app.repositories.fakes import FakeCaseRepository, FakePresenceRepository, FakeQueueRepository
from app.services.delivery import DeliveryResult
from app.services.manager_surface import ManagerSurfaceService
from app.services.rendering import render_case_detail, render_hub, render_queue
from app.state.manager_session import ManagerSessionState


class FakeDeliveryGateway:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def send_text(self, chat_id: int, text: str) -> DeliveryResult:
        _ = (chat_id, text)
        if self.ok:
            return DeliveryResult(ok=True, telegram_message_id=77)
        return DeliveryResult(ok=False, error_message="boom")


def test_queue_rendering_stable_numbers_and_order() -> None:
    actor = ManagerActor(uuid4(), 1, "Manager", SystemRole.MANAGER)
    items = [
        QueueItem(uuid4(), 101, "Acme", "new", "none", None, "urgent", 1, datetime.now(timezone.utc)),
        QueueItem(uuid4(), 102, "Beta", "active", "waiting_manager", actor.actor_id, "normal", 0, datetime.now(timezone.utc)),
    ]
    service = ManagerSurfaceService(
        FakeQueueRepository({"new": items}),
        FakeCaseRepository({}),
        FakePresenceRepository(),
        delivery_gateway=FakeDeliveryGateway(),
        page_size=2,
    )
    state = ManagerSessionState(queue_key="new", queue_offset=0)

    page = asyncio.run(service.queue_page(actor, state))
    rendered = render_queue("new", page, 0)

    assert "#101" in rendered and "#102" in rendered
    assert rendered.index("#101") < rendered.index("#102")


def test_case_detail_render_read_only_and_claim_updates() -> None:
    actor = ManagerActor(uuid4(), 1, "Manager", SystemRole.MANAGER)
    case_id = uuid4()
    detail = CaseDetail(
        case_id=case_id,
        case_display_number=777,
        commercial_status="open",
        operational_status="new",
        waiting_state="none",
        priority="high",
        escalation_level=1,
        assignment_label="Unassigned",
        linked_order_display_number=88,
        linked_quote_display_number=777,
        thread_entries=[ThreadEntry("customer", "Need update", datetime.now(timezone.utc))],
    )
    cases = FakeCaseRepository({case_id: detail})
    service = ManagerSurfaceService(
        FakeQueueRepository({}),
        cases,
        FakePresenceRepository(),
        delivery_gateway=FakeDeliveryGateway(),
        page_size=2,
    )

    before = render_case_detail(detail)
    assert "Customer thread:" in before
    assert "Internal notes:" in before
    assert "Case #777" in before
    assert "Order #88" in before
    assert "SLA: healthy" in before

    claimed = asyncio.run(service.claim_case(actor, case_id))
    assert claimed

    updated = asyncio.run(service.case_detail(actor, case_id))
    assert updated is not None
    assert updated.assignment_label == "Assigned to me"
    assert updated.operational_status == "active"


def test_reply_send_updates_delivery_status_and_note_is_internal_only() -> None:
    actor = ManagerActor(uuid4(), 1, "Manager", SystemRole.MANAGER)
    case_id = uuid4()
    detail = CaseDetail(
        case_id=case_id,
        case_display_number=500,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="normal",
        escalation_level=0,
        assignment_label="Assigned to me",
        linked_quote_display_number=500,
    )
    repo = FakeCaseRepository({case_id: detail})
    service = ManagerSurfaceService(
        FakeQueueRepository({}),
        repo,
        FakePresenceRepository(),
        delivery_gateway=FakeDeliveryGateway(ok=False),
        page_size=2,
    )

    send_notice = asyncio.run(service.send_reply(actor, case_id, "We are checking this now."))
    assert "delivery failed" in send_notice.lower()

    asyncio.run(service.save_internal_note(actor, case_id, "Internal follow-up only"))
    rendered = render_case_detail(detail)
    assert "Internal follow-up only" in rendered
    assert "We are checking this now." in rendered
    assert "[failed]" in rendered


def test_workdesk_rendering_shows_hot_tasks_and_queue_summary() -> None:
    actor = ManagerActor(uuid4(), 1, "Manager", SystemRole.MANAGER)
    hot = HotTaskBucket(
        key=HotTaskBucketKey.NEEDS_REPLY_NOW,
        title="Needs reply now",
        queue_key="waiting_me",
        items=[
            HotTaskItem(
                case_id=uuid4(),
                case_display_number=300,
                customer_label="Acme",
                reason="Customer waiting for manager response.",
                priority="urgent",
                escalation_level=1,
                waiting_state="waiting_manager",
                sla_due_at=datetime.now(timezone.utc),
                last_customer_message_at=datetime.now(timezone.utc),
                last_event_at=datetime.now(timezone.utc),
            )
        ],
    )
    buckets = [
        hot,
        HotTaskBucket(HotTaskBucketKey.NEW_BUSINESS, "New business", "new", []),
        HotTaskBucket(HotTaskBucketKey.SLA_AT_RISK, "SLA at risk", "waiting_me", []),
        HotTaskBucket(HotTaskBucketKey.URGENT_ESCALATED, "Urgent / VIP / escalated", "urgent", []),
        HotTaskBucket(HotTaskBucketKey.FAILED_DELIVERY, "Failed delivery", "waiting_me", []),
    ]
    rendered = render_hub(
        actor,
        presence=PresenceStatus.ONLINE,
        counts={"new": 2, "mine": 3, "waiting_me": 1, "waiting_customer": 0, "urgent": 1, "escalated": 1, "sla_near": 0, "sla_overdue": 1},
        buckets=buckets,
    )
    assert "ManagerBot Workdesk" in rendered
    assert "Hot tasks" in rendered
    assert "Needs reply now: 1" in rendered
    assert "#300" in rendered
    assert "Queue summary" in rendered
    assert "New/Unassigned: 2" in rendered
