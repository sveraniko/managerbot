from __future__ import annotations

import asyncio
import time

import httpx
from pydantic import ValidationError

from app.config.settings import Settings
from app.models import CaseDetail, InternalNote, ThreadEntry
from app.services.ai_cache import InMemoryAICache
from app.services.ai_reader import AIReaderAnalysis, AIReaderConfig, AIReaderService, CaseAIPacketBuilder
from app.services.ai_recommender import AIRecommendation, AIRecommenderConfig, AIRecommenderService, RecommendedAction
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
            ThreadEntry(direction="inbound", body="Need urgent update and final price, contact john@example.com or +1 415 555 1000", created_at=datetime.now(timezone.utc)),
            ThreadEntry(direction="outbound", body="We are checking stock and delivery ETA. Call +1 (415) 555-1212", created_at=datetime.now(timezone.utc), delivery_status="sent"),
        ],
        internal_notes=[InternalNote(body="Sensitive note: jane@company.com", author_label="Manager", created_at=datetime.now(timezone.utc))],
    )


def test_ai_policy_settings_and_flags() -> None:
    settings = Settings(
        ai_enabled=True,
        ai_reader_enabled=True,
        ai_recommender_enabled=False,
        ai_include_internal_notes=False,
        ai_max_thread_entries=4,
        ai_max_internal_notes=2,
        ai_max_input_chars=1200,
        ai_cache_ttl_seconds=30,
    )
    assert settings.ai_enabled is True
    assert settings.ai_reader_enabled is True
    assert settings.ai_recommender_enabled is False
    assert settings.ai_include_internal_notes is False
    assert settings.ai_max_thread_entries == 4
    assert settings.ai_max_internal_notes == 2
    assert settings.ai_cache_ttl_seconds == 30


def test_case_packet_builder_minimization_redaction_and_budget() -> None:
    detail = _sample_case()
    detail.thread_entries.extend(detail.thread_entries * 10)
    detail.internal_notes.extend(detail.internal_notes * 4)
    builder = CaseAIPacketBuilder(max_input_chars=550, include_internal_notes=True, max_thread_entries=5, max_internal_notes=2)

    packet = builder.build(detail, sla_state="near_breach")
    raw = packet.model_dump_json()

    assert packet.case_display_number == 7001
    assert len(packet.customer_thread_recent) <= 5
    assert len(packet.internal_notes_recent) <= 2
    assert "[redacted-email]" in raw
    assert "415" not in raw
    assert len(raw) <= 550


def test_case_packet_builder_respects_internal_notes_policy() -> None:
    detail = _sample_case()
    with_notes = CaseAIPacketBuilder(max_input_chars=2000, include_internal_notes=True).build(detail, sla_state="healthy")
    without_notes = CaseAIPacketBuilder(max_input_chars=2000, include_internal_notes=False).build(detail, sla_state="healthy")
    assert with_notes.internal_notes_recent
    assert without_notes.internal_notes_recent == []


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
    cfg = AIReaderConfig(True, "gpt-test", "reader-v1", 0.5, 2000, 300, True, 6, 3)

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
    assert ok.ok is True and ok.analysis is not None and ok.prompt_version == "reader-v1"

    timeout_client = FakeAIClient(exc=httpx.TimeoutException("timeout"))
    timeout_res = asyncio.run(AIReaderService(cfg, timeout_client).analyze_case(detail, sla_state="healthy"))
    assert timeout_res.ok is False and "timed out" in (timeout_res.error_message or "")

    err_client = FakeAIClient(exc=httpx.HTTPStatusError("boom", request=httpx.Request("POST", "http://x"), response=httpx.Response(500)))
    err_res = asyncio.run(AIReaderService(cfg, err_client).analyze_case(detail, sla_state="healthy"))
    assert err_res.ok is False and "unavailable" in (err_res.error_message or "")

    disabled = asyncio.run(AIReaderService(AIReaderConfig(False, "gpt", "reader-v1", 1, 1000, 200, True, 6, 3), success_client).analyze_case(detail, sla_state="healthy"))
    assert disabled.ok is False and "disabled" in (disabled.error_message or "")


def test_ai_cache_hit_miss_ttl_and_malformed_payload_fail_safe() -> None:
    detail = _sample_case()
    cache = InMemoryAICache(ttl_seconds=1)
    cfg = AIReaderConfig(True, "gpt-test", "reader-v1", 0.5, 2000, 300, True, 6, 3)
    client = FakeAIClient(
        payload={
            "summary": "Case summary",
            "customer_intent": "Intent",
            "risk_flags": [],
            "missing_information": [],
            "recommended_next_step": "Step",
            "confidence": 0.7,
            "timeline_brief": [],
            "tone_guidance": None,
        }
    )
    service = AIReaderService(cfg, client, cache=cache)

    first = asyncio.run(service.analyze_case(detail, sla_state="healthy"))
    second = asyncio.run(service.analyze_case(detail, sla_state="healthy"))
    assert first.ok and second.ok and second.from_cache is True
    assert client.calls == 1

    cache.set("reader:bad", {"analysis": {"summary": "missing fields"}})
    cache.get("reader:bad")  # should not crash path

    time.sleep(1.1)
    third = asyncio.run(service.analyze_case(detail, sla_state="healthy"))
    assert third.ok is True and third.from_cache is False
    assert client.calls == 2


def test_recommender_schema_and_service_and_prompt_version_metadata() -> None:
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

    detail = _sample_case()
    packet = CaseAIPacketBuilder(max_input_chars=1800, include_internal_notes=True).build(detail, sla_state="near_breach")
    cfg = AIRecommenderConfig(True, "gpt-test", "reco-v3", 0.5, 400)
    client = FakeAIClient(payload=recommendation.model_dump(mode="json"))
    res = asyncio.run(AIRecommenderService(cfg, client, cache=InMemoryAICache(30)).recommend(packet))
    assert res.ok is True and res.prompt_version == "reco-v3"


def test_ai_state_binding_prevents_cross_case_bleed_and_keeps_meta() -> None:
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

    bind_ai_result(state, case_a, analysis, None, model="gpt-x", prompt_version="reader-v1", from_cache=True)
    hit, err, meta = analysis_for_case(state, case_a)
    miss, miss_err, _ = analysis_for_case(state, case_b)

    assert hit is not None and err is None and meta and meta.from_cache is True
    assert miss is None and miss_err is None

    clear_ai_snapshot(state)
    assert state.ai_analysis is None and state.ai_case_id is None and state.ai_analysis_meta is None


def test_recommendation_state_case_bound_and_rendering_low_confidence_warning() -> None:
    from uuid import uuid4

    case_a = uuid4()
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
        confidence=0.42,
    )
    bind_ai_recommendation(state, case_a, recommendation, None, model="gpt-r", prompt_version="reco-v1", from_cache=False)
    hit, _, meta = recommendation_for_case(state, case_a)
    assert hit is not None and meta and meta.prompt_version == "reco-v1"

    rendered = render_case_detail(_sample_case(), ai_recommendation=hit, ai_recommendation_meta=meta, low_confidence_threshold=0.65)
    assert "low" in rendered
    assert "Model/prompt" in rendered

    clear_ai_snapshot(state)
    none_after_clear, _, _ = recommendation_for_case(state, case_a)
    assert none_after_clear is None
