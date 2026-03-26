from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services.ai_reader import AIReaderClient, AIReaderPacket

logger = structlog.get_logger(__name__)


class RecommendedAction(str, Enum):
    REPLY = "reply"
    CLARIFY = "clarify"
    ESCALATE = "escalate"
    WAIT = "wait"
    REVIEW_DELIVERY_ISSUE = "review_delivery_issue"


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


@dataclass(slots=True)
class AIRecommenderConfig:
    enabled: bool
    model: str
    timeout_seconds: float
    max_output_tokens: int


class AIRecommenderService:
    def __init__(self, config: AIRecommenderConfig, client: AIReaderClient | None) -> None:
        self._config = config
        self._client = client

    async def recommend(self, packet: AIReaderPacket) -> AIRecommendationResult:
        if not self._config.enabled:
            return AIRecommendationResult(ok=False, error_message="AI recommender is disabled.")
        if not self._client:
            return AIRecommendationResult(ok=False, error_message="AI provider is not configured.")

        logger.info(
            "ai_recommender_started",
            case_id=packet.case_id,
            case_display_number=packet.case_display_number,
            model=self._config.model,
        )
        try:
            payload = await self._client.complete_json(
                model=self._config.model,
                system_prompt=_recommender_system_prompt(),
                user_prompt=_recommender_user_prompt(packet),
                schema=AIRecommendation.model_json_schema(),
                timeout_seconds=self._config.timeout_seconds,
                max_output_tokens=self._config.max_output_tokens,
            )
            recommendation = AIRecommendation.model_validate(payload)
        except httpx.TimeoutException:
            logger.warning("ai_recommender_timeout", case_id=packet.case_id, model=self._config.model)
            return AIRecommendationResult(ok=False, error_message="AI recommender timed out. Try refresh.", model=self._config.model)
        except httpx.HTTPError as exc:
            logger.warning(
                "ai_recommender_provider_error",
                case_id=packet.case_id,
                model=self._config.model,
                error=str(exc),
            )
            return AIRecommendationResult(ok=False, error_message="AI recommender is temporarily unavailable.", model=self._config.model)
        except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as exc:
            logger.warning(
                "ai_recommender_parse_error",
                case_id=packet.case_id,
                model=self._config.model,
                error=str(exc),
            )
            return AIRecommendationResult(ok=False, error_message="AI recommender returned invalid output.", model=self._config.model)

        logger.info(
            "ai_recommender_succeeded",
            case_id=packet.case_id,
            model=self._config.model,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        return AIRecommendationResult(ok=True, recommendation=recommendation, model=self._config.model)


def _recommender_system_prompt() -> str:
    return (
        "You are ManagerBot AI Recommender. "
        "You are advisory-only and never execute actions. "
        "Use only the provided case packet facts and avoid invented events. "
        "Provide concise manager-ready recommendations, reply and internal note drafts, "
        "and escalation suggestions only when justified by packet risk. "
        "Use clarification questions only when genuinely needed. "
        "Avoid certainty beyond available facts and return strict JSON matching schema."
    )


def _recommender_user_prompt(packet: AIReaderPacket) -> str:
    return (
        "Generate controlled recommendations for this case packet. "
        "Return practical next step, a constrained action enum, concise reply draft, concise internal note draft, "
        "clarification questions when needed, and escalation rationale only when escalation is recommended.\n\n"
        f"CASE_PACKET_JSON:\n{packet.model_dump_json(indent=2)}"
    )
