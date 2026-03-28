from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services.ai_cache import InMemoryAICache
from app.services.ai_reader import AIReaderClient, AIReaderPacket

logger = structlog.get_logger(__name__)


class RecommendedAction(str, Enum):
    REPLY = "reply"
    CLARIFY = "clarify"
    ESCALATE = "escalate"
    WAIT = "wait"
    REVIEW_DELIVERY_ISSUE = "review_delivery_issue"


class AIHandoffState(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    ALTERNATIVES_AVAILABLE = "alternatives_available"
    NOT_FOUND = "not_found"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class AIAlternativeSuggestion(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    selling_unit: str | None = Field(default=None, max_length=80)
    min_order: str | None = Field(default=None, max_length=80)
    increment: str | None = Field(default=None, max_length=80)
    packaging_context: str | None = Field(default=None, max_length=120)
    availability: str | None = Field(default=None, max_length=80)
    rationale: str | None = Field(default=None, max_length=220)


class AIRecommendation(BaseModel):
    summary: str = Field(min_length=1, max_length=500)
    customer_intent: str = Field(min_length=1, max_length=300)
    risk_flags: list[str] = Field(default_factory=list, max_length=8)
    missing_information: list[str] = Field(default_factory=list, max_length=10)
    recommended_next_step: str = Field(min_length=1, max_length=280)
    recommended_action: RecommendedAction
    draft_reply: str = Field(min_length=1, max_length=2000)
    draft_internal_note: str = Field(min_length=1, max_length=1200)
    clarification_questions: list[str] = Field(default_factory=list, max_length=5)
    escalation_recommendation: bool = False
    escalation_reason: str | None = Field(default=None, max_length=300)
    handoff_state: AIHandoffState = AIHandoffState.NEEDS_HUMAN_REVIEW
    handoff_rationale: str = Field(default="Needs manager review.", min_length=1, max_length=260)
    resolved_item_title: str | None = Field(default=None, max_length=180)
    alternatives: list[AIAlternativeSuggestion] = Field(default_factory=list, max_length=5)
    confidence: float

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


@dataclass(slots=True)
class AIRecommendationResult:
    ok: bool
    recommendation: AIRecommendation | None = None
    error_message: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    from_cache: bool = False


@dataclass(slots=True)
class AIRecommenderConfig:
    enabled: bool
    model: str
    prompt_version: str
    timeout_seconds: float
    max_output_tokens: int


class AIRecommenderService:
    def __init__(self, config: AIRecommenderConfig, client: AIReaderClient | None, cache: InMemoryAICache | None = None) -> None:
        self._config = config
        self._client = client
        self._cache = cache

    async def recommend(self, packet: AIReaderPacket, *, force_refresh: bool = False) -> AIRecommendationResult:
        if not self._config.enabled:
            return AIRecommendationResult(ok=False, error_message="AI recommender is disabled.")
        if not self._client:
            return AIRecommendationResult(ok=False, error_message="AI provider is not configured.")

        cache_key = self._cache_key(packet)
        if self._cache and not force_refresh:
            cached = self._cache.get(cache_key)
            if cached:
                try:
                    recommendation = AIRecommendation.model_validate(cached["recommendation"])
                    return AIRecommendationResult(
                        ok=True,
                        recommendation=recommendation,
                        model=self._config.model,
                        prompt_version=self._config.prompt_version,
                        from_cache=True,
                    )
                except Exception:
                    logger.warning("ai_recommender_cache_payload_invalid", case_id=packet.case_id)
                    self._cache.delete(cache_key)

        logger.info(
            "ai_recommender_started",
            case_id=packet.case_id,
            case_display_number=packet.case_display_number,
            model=self._config.model,
            prompt_version=self._config.prompt_version,
            force_refresh=force_refresh,
        )
        try:
            payload = await self._client.complete_json(
                model=self._config.model,
                system_prompt=_recommender_system_prompt(self._config.prompt_version),
                user_prompt=_recommender_user_prompt(packet),
                schema=AIRecommendation.model_json_schema(),
                timeout_seconds=self._config.timeout_seconds,
                max_output_tokens=self._config.max_output_tokens,
            )
            recommendation = AIRecommendation.model_validate(payload)
        except httpx.TimeoutException:
            logger.warning("ai_recommender_timeout", case_id=packet.case_id, model=self._config.model)
            return AIRecommendationResult(ok=False, error_message="AI recommender timed out. Try refresh.", model=self._config.model, prompt_version=self._config.prompt_version)
        except httpx.HTTPError as exc:
            logger.warning(
                "ai_recommender_provider_error",
                case_id=packet.case_id,
                model=self._config.model,
                prompt_version=self._config.prompt_version,
                error=str(exc),
            )
            return AIRecommendationResult(ok=False, error_message="AI recommender is temporarily unavailable.", model=self._config.model, prompt_version=self._config.prompt_version)
        except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as exc:
            logger.warning(
                "ai_recommender_parse_error",
                case_id=packet.case_id,
                model=self._config.model,
                prompt_version=self._config.prompt_version,
                error=str(exc),
            )
            return AIRecommendationResult(ok=False, error_message="AI recommender returned invalid output.", model=self._config.model, prompt_version=self._config.prompt_version)

        if self._cache:
            self._cache.set(cache_key, {"recommendation": recommendation.model_dump(mode="json")})
        logger.info(
            "ai_recommender_succeeded",
            case_id=packet.case_id,
            model=self._config.model,
            prompt_version=self._config.prompt_version,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        return AIRecommendationResult(
            ok=True,
            recommendation=recommendation,
            model=self._config.model,
            prompt_version=self._config.prompt_version,
            from_cache=False,
        )

    def _cache_key(self, packet: AIReaderPacket) -> str:
        digest = hashlib.sha256(json.dumps(packet.model_dump(mode="json"), sort_keys=True).encode("utf-8")).hexdigest()
        return f"recommender:{self._config.model}:{self._config.prompt_version}:{packet.case_id}:{digest}"


def recommendation_supports_draft_adoption(recommendation: AIRecommendation) -> bool:
    return recommendation.handoff_state in {
        AIHandoffState.RESOLVED,
        AIHandoffState.ALTERNATIVES_AVAILABLE,
    }


def _recommender_system_prompt(prompt_version: str) -> str:
    return (
        f"You are ManagerBot AI Recommender (prompt {prompt_version}). "
        "You are advisory-only and never execute actions. "
        "Use only the provided case packet facts and avoid invented events. "
        "Provide concise manager-ready recommendations, explicit AI-to-manager handoff status, "
        "resolved item identity or alternatives where relevant, and escalation suggestions only when justified by packet risk. "
        "When commercial constraints are present, use customer-readable terms: Selling unit, Min order, Increment, packaging context. "
        "Never use internal shorthand like MOQ/step in customer-visible draft text. "
        "Use clarification questions only when genuinely needed. "
        "Avoid certainty beyond available facts and return strict JSON matching schema."
    )


def _recommender_user_prompt(packet: AIReaderPacket) -> str:
    return (
        "Generate controlled recommendations for this case packet. "
        "Return practical next step, a constrained action enum, concise reply draft, concise internal note draft, "
        "clarification questions when needed, and escalation rationale only when escalation is recommended. "
        "Set handoff_state to one of: resolved, ambiguous, alternatives_available, not_found, needs_human_review.\n\n"
        f"CASE_PACKET_JSON:\n{packet.model_dump_json(indent=2)}"
    )
