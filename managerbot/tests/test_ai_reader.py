from __future__ import annotations

import asyncio

import httpx
from pydantic import ValidationError

from app.models import CaseDetail, ThreadEntry
from app.services.ai_reader import (
    AIReaderAnalysis,
    AIReaderConfig,
    AIReaderService,
    CaseAIPacketBuilder,
)
from app.services.ai_recommender import (
    AIRecommendation,
    AIRecommenderConfig,
    AIRecommenderService,
    RecommendedAction,
)
from app.services.ai_state import analysis_for_case, bind_ai_recommendation, bind_ai_result, clear_ai_snapshot, recommendation_for_case
from app.services.rendering import render_case_detail
from app.state.manager_session import ManagerSessionState


class FakeAIClient:
    def __init__(self, payload=None, exc: Exception | None = None) -> None:
        self.payload = payload
        self.exc = exc
        self.calls = 0

    async def complete_json(self, **kwargs):
        _ = kwargs
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.payload


def _sample_case() -> CaseDetail:
    from datetime import datetime, timezone
    from uuid import uuid4

    case_id = uuid4()
    return CaseDetail(
        case_id=case_id,
        case_display_number=7001,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="high",
        escalation_level=1,
        assignment_label="Manager One",
        linked_quote_display_number=7001,
        linked_order_display_number=9001,
        customer_label="Acme",
        thread_entries=[
            ThreadEntry(direction="inbound", body="Need urgent update and final price.", created_at=datetime.now(timezone.utc)),
            ThreadEntry(direction="outbound", body="We are checking stock and delivery ETA.", created_at=datetime.now(timezone.utc), delivery_status="sent"),
        ],
    )


def test_case_packet_builder_is_bounded_and_case_scoped() -> None:
    detail = _sample_case()
    detail.thread_entries.extend(detail.thread_entries * 8)
    builder = CaseAIPacketBuilder(max_input_chars=700, include_internal_notes=False)

    packet = builder.build(detail, sla_state="near_breach")
    raw = packet.model_dump_json()

    assert packet.case_display_number == 7001
    assert packet.customer_label == "Acme"
    assert packet.sla_state == "near_breach"
    assert packet.internal_notes_recent == []
    assert len(raw) <= 700
    assert "quote_case_ops_states" not in raw


def test_structured_output_validation_paths() -> None:
    valid = AIReaderAnalysis.model_validate(
        {
            "summary": "Customer requests ETA and final quote confirmation.",
            "customer_intent": "Get final delivery commitment",
            "risk_flags": ["SLA near breach"],
            "missing_information": ["Exact shipment date"],
            "recommended_next_step": "Confirm logistics ETA and respond with a concrete date.",
            "confidence": 0.82,
            "timeline_brief": ["Customer asked for update", "Manager replied pending check"],
            "tone_guidance": "Use confident but non-committal wording until ETA is confirmed.",
        }
    )
    assert valid.confidence == 0.82

    try:
        AIReaderAnalysis.model_validate(
            {
                "summary": "x",
                "customer_intent": "y",
                "risk_flags": [],
                "missing_information": [],
                "recommended_next_step": "z",
                "confidence": 1.4,
            }
        )
        assert False, "expected validation error"
    except ValidationError:
        pass


def test_ai_reader_service_success_timeout_provider_and_feature_flag() -> None:
    detail = _sample_case()
    cfg = AIReaderConfig(True, "gpt-test", 0.5, 2000, 300, True)

    success_client = FakeAIClient(
        payload={
            "summary": "Case summary",
            "customer_intent": "Intent",
            "risk_flags": ["Risk"],
            "missing_information": ["Missing"],
            "recommended_next_step": "Do next step",
            "confidence": 0.6,
            "timeline_brief": [],
            "tone_guidance": None,
        }
    )
    ok = asyncio.run(AIReaderService(cfg, success_client).analyze_case(detail, sla_state="healthy"))
    assert ok.ok is True and ok.analysis is not None

    timeout_client = FakeAIClient(exc=httpx.TimeoutException("timeout"))
    timeout_res = asyncio.run(AIReaderService(cfg, timeout_client).analyze_case(detail, sla_state="healthy"))
    assert timeout_res.ok is False and "timed out" in (timeout_res.error_message or "")

    err_client = FakeAIClient(exc=httpx.HTTPStatusError("boom", request=httpx.Request("POST", "http://x"), response=httpx.Response(500)))
    err_res = asyncio.run(AIReaderService(cfg, err_client).analyze_case(detail, sla_state="healthy"))
    assert err_res.ok is False and "unavailable" in (err_res.error_message or "")

    disabled = asyncio.run(AIReaderService(AIReaderConfig(False, "gpt", 1, 1000, 200, True), success_client).analyze_case(detail, sla_state="healthy"))
    assert disabled.ok is False and "disabled" in (disabled.error_message or "")


def test_ai_state_binding_prevents_cross_case_bleed() -> None:
    from uuid import uuid4

    case_a = uuid4()
    case_b = uuid4()
    state = ManagerSessionState(selected_case_id=case_a)
    analysis = AIReaderAnalysis(
        summary="Summary",
        customer_intent="Intent",
        risk_flags=[],
        missing_information=[],
        recommended_next_step="Step",
        confidence=0.55,
        timeline_brief=[],
        tone_guidance=None,
    )

    bind_ai_result(state, case_a, analysis, None)
    hit, err = analysis_for_case(state, case_a)
    miss, miss_err = analysis_for_case(state, case_b)

    assert hit is not None and err is None
    assert miss is None and miss_err is None

    clear_ai_snapshot(state)
    assert state.ai_analysis is None and state.ai_case_id is None


def test_case_render_shows_advisory_ai_block() -> None:
    detail = _sample_case()
    analysis = AIReaderAnalysis(
        summary="Concise summary",
        customer_intent="Track delivery",
        risk_flags=["Potential SLA breach"],
        missing_information=["Final ETA"],
        recommended_next_step="Confirm ETA with logistics and reply customer.",
        confidence=0.74,
        timeline_brief=[],
        tone_guidance=None,
    )

    rendered = render_case_detail(detail, ai_analysis=analysis, ai_error=None)
    assert "AI reader (advisory only):" in rendered
    assert "Concise summary" in rendered

    rendered_err = render_case_detail(detail, ai_analysis=None, ai_error="AI timed out")
    assert "unavailable: AI timed out" in rendered_err


def test_recommender_schema_parses_and_constrains_action_enum() -> None:
    recommendation = AIRecommendation.model_validate(
        {
            "summary": "Customer asks for updated ETA and commit window.",
            "customer_intent": "Need delivery certainty before approval.",
            "risk_flags": ["Potential SLA breach"],
            "missing_information": ["Confirmed shipment date"],
            "recommended_next_step": "Confirm ETA with logistics and send concise status update.",
            "recommended_action": "clarify",
            "draft_reply": "Thanks for the follow-up. Could you confirm your required delivery date window?",
            "draft_internal_note": "Need logistics ETA confirmation before final customer commitment.",
            "clarification_questions": ["What delivery date do you need for go-live?"],
            "escalation_recommendation": False,
            "escalation_reason": None,
            "confidence": 0.71,
        }
    )
    assert recommendation.recommended_action == RecommendedAction.CLARIFY

    try:
        AIRecommendation.model_validate(
            {
                "summary": "x",
                "customer_intent": "y",
                "risk_flags": [],
                "missing_information": [],
                "recommended_next_step": "z",
                "recommended_action": "invent_new_action",
                "draft_reply": "a",
                "draft_internal_note": "b",
                "clarification_questions": [],
                "escalation_recommendation": False,
                "escalation_reason": None,
                "confidence": 0.6,
            }
        )
        assert False, "expected validation error"
    except ValidationError:
        pass


def test_ai_recommender_service_success_timeout_provider_and_disabled() -> None:
    detail = _sample_case()
    packet = CaseAIPacketBuilder(max_input_chars=1800, include_internal_notes=True).build(detail, sla_state="near_breach")
    cfg = AIRecommenderConfig(True, "gpt-test", 0.5, 400)

    success_client = FakeAIClient(
        payload={
            "summary": "Summary",
            "customer_intent": "Intent",
            "risk_flags": [],
            "missing_information": ["ETA"],
            "recommended_next_step": "Clarify ETA and reply.",
            "recommended_action": "reply",
            "draft_reply": "Thanks for your message. We are confirming ETA and will update today.",
            "draft_internal_note": "Await ETA from logistics, then send confirmed response.",
            "clarification_questions": [],
            "escalation_recommendation": False,
            "escalation_reason": None,
            "confidence": 0.67,
        }
    )
    ok = asyncio.run(AIRecommenderService(cfg, success_client).recommend(packet))
    assert ok.ok is True and ok.recommendation is not None

    timeout_client = FakeAIClient(exc=httpx.TimeoutException("timeout"))
    timeout_res = asyncio.run(AIRecommenderService(cfg, timeout_client).recommend(packet))
    assert timeout_res.ok is False and "timed out" in (timeout_res.error_message or "")

    err_client = FakeAIClient(exc=httpx.HTTPStatusError("boom", request=httpx.Request("POST", "http://x"), response=httpx.Response(500)))
    err_res = asyncio.run(AIRecommenderService(cfg, err_client).recommend(packet))
    assert err_res.ok is False and "unavailable" in (err_res.error_message or "")

    disabled = asyncio.run(AIRecommenderService(AIRecommenderConfig(False, "gpt", 1, 300), success_client).recommend(packet))
    assert disabled.ok is False and "disabled" in (disabled.error_message or "")


def test_ai_recommendation_state_is_case_bound_and_safe_for_draft_adoption() -> None:
    from uuid import uuid4

    case_a = uuid4()
    case_b = uuid4()
    state = ManagerSessionState(selected_case_id=case_a)
    recommendation = AIRecommendation(
        summary="Summary",
        customer_intent="Intent",
        risk_flags=[],
        missing_information=[],
        recommended_next_step="Reply with ETA",
        recommended_action=RecommendedAction.REPLY,
        draft_reply="We are checking this and will update shortly.",
        draft_internal_note="Need ETA from ops before final confirmation.",
        clarification_questions=[],
        escalation_recommendation=False,
        escalation_reason=None,
        confidence=0.6,
    )

    bind_ai_recommendation(state, case_a, recommendation, None)
    hit, hit_err = recommendation_for_case(state, case_a)
    miss, miss_err = recommendation_for_case(state, case_b)
    assert hit is not None and hit_err is None
    assert miss is None and miss_err is None
    assert hit.draft_reply.startswith("We are checking")

    clear_ai_snapshot(state)
    none_after_clear, _ = recommendation_for_case(state, case_a)
    assert none_after_clear is None


def test_rendering_shows_recommendation_advisory_clarifications_and_escalation() -> None:
    detail = _sample_case()
    recommendation = AIRecommendation(
        summary="Summary",
        customer_intent="Intent",
        risk_flags=["Delivery risk"],
        missing_information=["Exact requested date"],
        recommended_next_step="Ask one clarifying question then reply.",
        recommended_action=RecommendedAction.CLARIFY,
        draft_reply="Thanks for reaching out. Could you confirm the required delivery date?",
        draft_internal_note="Customer asks for ETA; need required date to set expectation.",
        clarification_questions=["What is your target delivery date?"],
        escalation_recommendation=True,
        escalation_reason="Escalation suggested due to repeated missed ETA commits.",
        confidence=0.78,
    )
    rendered = render_case_detail(detail, ai_recommendation=recommendation)
    assert "AI recommendations (advisory only — no auto-actions):" in rendered
    assert "Recommended action: clarify" in rendered
    assert "Escalation suggested: yes" in rendered
    assert "Clarifications:" in rendered
