import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.models import CaseDetail, ManagerActor, QueueItem, SystemRole, ThreadEntry
from app.repositories.fakes import FakeCaseRepository, FakePresenceRepository, FakeQueueRepository
from app.services.manager_surface import ManagerSurfaceService
from app.services.rendering import render_case_detail, render_queue
from app.state.manager_session import ManagerSessionState


def test_queue_rendering_stable_numbers_and_order() -> None:
    actor = ManagerActor(uuid4(), 1, "Manager", SystemRole.MANAGER)
    items = [
        QueueItem(uuid4(), 101, "Acme", "new", "none", None, "urgent", 1, datetime.now(timezone.utc)),
        QueueItem(uuid4(), 102, "Beta", "active", "waiting_manager", actor.actor_id, "normal", 0, datetime.now(timezone.utc)),
    ]
    service = ManagerSurfaceService(FakeQueueRepository({"new": items}), FakeCaseRepository({}), FakePresenceRepository(), page_size=2)
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
    service = ManagerSurfaceService(FakeQueueRepository({}), cases, FakePresenceRepository(), page_size=2)

    before = render_case_detail(detail)
    assert "Thread (read-only):" in before
    assert "Case #777" in before
    assert "Order #88" in before

    claimed = asyncio.run(service.claim_case(actor, case_id))
    assert claimed

    updated = asyncio.run(service.case_detail(actor, case_id))
    assert updated is not None
    assert updated.assignment_label == "Assigned to me"
    assert updated.operational_status == "active"
