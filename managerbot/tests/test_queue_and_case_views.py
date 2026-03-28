import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.models import (
    CaseDetail,
    CustomerCard,
    HotTaskBucket,
    HotTaskBucketKey,
    HotTaskItem,
    ManagerActor,
    ManagerItemDetail,
    PresenceStatus,
    QueueItem,
    SystemRole,
    ThreadEntry,
)
from app.repositories.fakes import FakeCaseRepository, FakePresenceRepository, FakeQueueRepository
from app.services.ai_recommender import AIHandoffState, AIRecommendation, RecommendedAction
from app.services.delivery import DeliveryResult
from app.services.manager_surface import ManagerSurfaceService
from app.services.rendering import render_case_detail, render_contact_actions_panel, render_hub, render_queue, render_reply_preview
from app.state.manager_session import ManagerSessionState


class FakeDeliveryGateway:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def send_text(self, chat_id: int, text: str) -> DeliveryResult:
        _ = (chat_id, text)
        if self.ok:
            return DeliveryResult(ok=True, telegram_message_id=77)
        return DeliveryResult(ok=False, error_message="boom")


class CaptureDeliveryGateway(FakeDeliveryGateway):
    def __init__(self, ok: bool = True) -> None:
        super().__init__(ok=ok)
        self.sent: list[tuple[int, str]] = []

    async def send_text(self, chat_id: int, text: str) -> DeliveryResult:
        self.sent.append((chat_id, text))
        return await super().send_text(chat_id, text)


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
        escalation_level="manager_attention",
        assignment_label="Unassigned",
        linked_order_display_number=88,
        linked_quote_display_number=777,
        item_detail=ManagerItemDetail(
            title="Almond Dragee",
            brand="SweetCo",
            sku_code="SW-001",
            selling_unit="box",
            min_order="2 boxes",
            increment="1 box",
            packaging_context="24 pcs",
            shelf_life="9 months",
            origin="Italy",
            weight="2.4 kg",
            piece_weight="100 g",
            description="Crunchy almond dragee with cocoa coating.",
            is_active=True,
            in_draft=False,
        ),
        thread_entries=[ThreadEntry("customer", "Need update", datetime.now(timezone.utc))],
        customer_card=CustomerCard(label="Acme", actor_id="cust-1", telegram_chat_id=40001, telegram_user_id=40001),
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
    assert "Customer card:" in before
    assert "Telegram chat ID: 40001" in before
    assert "Direct contact policy" in before
    assert "SLA: healthy" in before
    assert "Item detail:" in before
    assert "- Selling unit: box" in before
    assert "- Min order: 2 boxes" in before
    assert "- Increment: 1 box" in before
    assert "- In box: 24 pcs" in before
    assert "- Shelf life: 9 months" in before
    assert "- Origin: Italy" in before
    assert "- Weight: 2.4 kg" in before
    assert "- Piece weight: 100 g" in before

    claimed = asyncio.run(service.claim_case(actor, case_id))
    assert claimed

    updated = asyncio.run(service.case_detail(actor, case_id))
    assert updated is not None
    assert updated.assignment_label == "Assigned to me"
    assert updated.operational_status == "active"


def test_contact_actions_panel_handles_missing_data_cleanly() -> None:
    detail = CaseDetail(
        case_id=uuid4(),
        case_display_number=778,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="normal",
        escalation_level="none",
        assignment_label="Assigned to me",
        linked_quote_display_number=778,
        customer_card=CustomerCard(label=None, actor_id=None, telegram_chat_id=None, telegram_user_id=None),
    )
    rendered = render_contact_actions_panel(detail)
    assert "Customer card:" in rendered
    assert "Label: Unavailable" in rendered
    assert "Telegram chat ID: Unavailable" in rendered
    assert "Direct-contact cues:" in rendered


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
        escalation_level="none",
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
                escalation_level="manager_attention",
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
        HotTaskBucket(HotTaskBucketKey.SLA_AT_RISK, "SLA at risk", "sla_risk", []),
        HotTaskBucket(HotTaskBucketKey.URGENT_ESCALATED, "Urgent / VIP / escalated", "urgent_escalated", []),
        HotTaskBucket(HotTaskBucketKey.FAILED_DELIVERY, "Failed delivery", "failed_delivery", []),
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


def test_item_detail_omits_missing_fields_without_placeholder_filler() -> None:
    detail = CaseDetail(
        case_id=uuid4(),
        case_display_number=779,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="normal",
        escalation_level="none",
        assignment_label="Assigned to me",
        linked_quote_display_number=779,
        item_detail=ManagerItemDetail(title="Hazelnut Cream", min_order="1 box"),
    )
    rendered = render_case_detail(detail)
    assert "Item detail:" in rendered
    assert "- Item: Hazelnut Cream" in rendered
    assert "- Min order: 1 box" in rendered
    assert "Increment" not in rendered
    assert "In box" not in rendered
    assert "Description: n/a" not in rendered.lower()


def test_reply_preview_includes_customer_visible_text_and_commercial_constraints() -> None:
    detail = CaseDetail(
        case_id=uuid4(),
        case_display_number=901,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="normal",
        escalation_level="none",
        assignment_label="Assigned to me",
        linked_quote_display_number=901,
        item_detail=ManagerItemDetail(
            selling_unit="display box",
            min_order="2 display boxes",
            increment="1 display box",
            packaging_context="12 trays",
            is_active=True,
            in_draft=False,
        ),
    )
    draft = "Available now. Min order is 2 display boxes, increment 1 display box."
    rendered = render_reply_preview(detail, draft, guardrail_issues=[])
    assert "Customer-visible message (exactly as sent):" in rendered
    assert draft in rendered
    assert "Commercial context check before send:" in rendered
    assert "- Selling unit: display box" in rendered
    assert "- Min order: 2 display boxes" in rendered
    assert "- Increment: 1 display box" in rendered
    assert "- In box: 12 trays" in rendered
    assert "- Availability: active" in rendered
    assert "- Draft quote: no" in rendered


def test_reply_preview_omits_absent_commercial_lines() -> None:
    detail = CaseDetail(
        case_id=uuid4(),
        case_display_number=902,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="normal",
        escalation_level="none",
        assignment_label="Assigned to me",
        linked_quote_display_number=902,
        item_detail=ManagerItemDetail(title="Classic Nougat"),
    )
    rendered = render_reply_preview(detail, "Thanks, we will update shortly.")
    assert "Customer-visible message (exactly as sent):" in rendered
    assert "Commercial context check before send:" not in rendered


def test_compose_guardrails_flag_legacy_internal_terms() -> None:
    from app.services.compose import ComposeStateService

    service = ComposeStateService()
    issues = service.customer_visible_guardrail_issues("MOQ 3 boxes, step 1 box.")
    assert "Min order" in " ".join(issues)
    assert "Increment" in " ".join(issues)


def test_reply_preview_message_matches_final_sent_message() -> None:
    actor = ManagerActor(uuid4(), 1, "Manager", SystemRole.MANAGER)
    case_id = uuid4()
    detail = CaseDetail(
        case_id=case_id,
        case_display_number=903,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="normal",
        escalation_level="none",
        assignment_label="Assigned to me",
        linked_quote_display_number=903,
        customer_card=CustomerCard(label="Acme", telegram_chat_id=42001),
        item_detail=ManagerItemDetail(min_order="2 boxes", increment="1 box"),
    )
    gateway = CaptureDeliveryGateway(ok=True)
    service = ManagerSurfaceService(
        FakeQueueRepository({}),
        FakeCaseRepository({case_id: detail}),
        FakePresenceRepository(),
        delivery_gateway=gateway,
    )
    draft = "Confirmed: Min order 2 boxes, increment 1 box."
    preview = render_reply_preview(detail, draft)
    notice = asyncio.run(service.send_reply(actor, case_id, draft))

    assert draft in preview
    assert gateway.sent and gateway.sent[0][1] == draft
    assert "sent to customer" in notice.lower()


def test_fake_case_repository_preserves_manager_item_contract() -> None:
    actor = ManagerActor(uuid4(), 1, "Manager", SystemRole.MANAGER)
    case_id = uuid4()
    detail = CaseDetail(
        case_id=case_id,
        case_display_number=810,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="high",
        escalation_level="none",
        assignment_label="Assigned to me",
        linked_quote_display_number=810,
        item_detail=ManagerItemDetail(
            title="Truffle Mix",
            selling_unit="pack",
            min_order="3 packs",
            increment="1 pack",
            packaging_context="12 pcs",
        ),
    )
    service = ManagerSurfaceService(
        FakeQueueRepository({}),
        FakeCaseRepository({case_id: detail}),
        FakePresenceRepository(),
        delivery_gateway=FakeDeliveryGateway(),
    )

    loaded = asyncio.run(service.case_detail(actor, case_id))
    assert loaded is not None
    assert loaded.item_detail is not None
    assert loaded.item_detail.selling_unit == "pack"
    assert loaded.item_detail.min_order == "3 packs"
    assert loaded.item_detail.increment == "1 pack"
    assert loaded.item_detail.packaging_context == "12 pcs"


def test_ai_handoff_rendering_shows_structured_constraints_and_ambiguity_safely() -> None:
    detail = CaseDetail(
        case_id=uuid4(),
        case_display_number=811,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="high",
        escalation_level="none",
        assignment_label="Assigned to me",
        linked_quote_display_number=811,
        item_detail=ManagerItemDetail(
            title="Nougat Selection Box",
            selling_unit="box",
            min_order="2 boxes",
            increment="1 box",
            packaging_context="24 pcs",
            is_active=True,
        ),
    )
    recommendation = AIRecommendation(
        summary="Suggested alternatives due to uncertain customer preference.",
        customer_intent="Customer needs closest substitute.",
        risk_flags=["Primary SKU uncertain"],
        missing_information=["Preferred flavor"],
        recommended_next_step="Confirm preferred flavor and choose one alternative.",
        recommended_action=RecommendedAction.CLARIFY,
        draft_reply="We can offer alternatives. Please confirm your preferred flavor.",
        draft_internal_note="Use alternatives list and verify flavor preference.",
        clarification_questions=["Do you prefer almond or pistachio variant?"],
        escalation_recommendation=False,
        escalation_reason=None,
        handoff_state=AIHandoffState.AMBIGUOUS,
        handoff_rationale="Two similarly named SKUs matched; requires manager confirmation.",
        resolved_item_title=None,
        alternatives=[
            {
                "title": "Nougat Selection Box Almond",
                "selling_unit": "box",
                "min_order": "2 boxes",
                "increment": "1 box",
                "packaging_context": "24 pcs",
                "availability": "active",
                "rationale": "Closest match by title.",
            }
        ],
        confidence=0.58,
    )

    rendered = render_case_detail(detail, ai_recommendation=recommendation, low_confidence_threshold=0.65)
    assert "Handoff status: ambiguous" in rendered
    assert "Structured commercial constraints" in rendered
    assert "Selling unit: box" in rendered
    assert "Min order: 2 boxes" in rendered
    assert "Increment: 1 box" in rendered
    assert "Manager action safety: do not send AI draft without manual correction/review." in rendered


def test_ai_handoff_not_found_with_existing_item_forces_human_review_state() -> None:
    detail = CaseDetail(
        case_id=uuid4(),
        case_display_number=812,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="normal",
        escalation_level="none",
        assignment_label="Assigned to me",
        linked_quote_display_number=812,
        item_detail=ManagerItemDetail(
            title="Truffle Gift Box",
            selling_unit="box",
            min_order="1 box",
            increment="1 box",
        ),
    )
    recommendation = AIRecommendation(
        summary="No item found.",
        customer_intent="Unknown",
        risk_flags=[],
        missing_information=["Exact SKU"],
        recommended_next_step="Request exact SKU code.",
        recommended_action=RecommendedAction.CLARIFY,
        draft_reply="Could you share the exact SKU code?",
        draft_internal_note="AI reported not_found.",
        clarification_questions=["Can you share SKU code?"],
        escalation_recommendation=False,
        escalation_reason=None,
        handoff_state=AIHandoffState.NOT_FOUND,
        handoff_rationale="No direct match from AI.",
        resolved_item_title=None,
        alternatives=[],
        confidence=0.5,
    )

    rendered = render_case_detail(detail, ai_recommendation=recommendation)
    assert "Handoff status: needs_human_review" in rendered
    assert "AI marked not found, but case already has item details." in rendered
