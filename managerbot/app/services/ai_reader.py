from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx
import structlog
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.models import CaseDetail

logger = structlog.get_logger(__name__)


class AIReaderPacket(BaseModel):
    case_id: str
    case_display_number: int
    customer_label: str | None = None
    commercial_status: str
    operational_status: str
    waiting_state: str
    priority: str
    escalation_level: int
    assignment_label: str
    linked_quote_display_number: int | None = None
    linked_order_display_number: int | None = None
    sla_state: str
    delivery_status_summary: str
    customer_thread_recent: list[str] = Field(default_factory=list)
    internal_notes_recent: list[str] = Field(default_factory=list)


class AIReaderAnalysis(BaseModel):
    summary: str = Field(min_length=1, max_length=600)
    customer_intent: str = Field(min_length=1, max_length=300)
    risk_flags: list[str] = Field(default_factory=list, max_length=8)
    missing_information: list[str] = Field(default_factory=list, max_length=10)
    recommended_next_step: str = Field(min_length=1, max_length=300)
    confidence: float
    timeline_brief: list[str] = Field(default_factory=list, max_length=6)
    tone_guidance: str | None = Field(default=None, max_length=200)

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


@dataclass(slots=True)
class AIReaderResult:
    ok: bool
    analysis: AIReaderAnalysis | None = None
    error_message: str | None = None
    model: str | None = None


class AIReaderClient(Protocol):
    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> dict[str, Any]: ...


class OpenAIChatCompletionsClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "managerbot_ai_reader_analysis",
                    "strict": True,
                    "schema": schema,
                },
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(f"{self._base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()

        content = body["choices"][0]["message"]["content"]
        return json.loads(content)


@dataclass(slots=True)
class AIReaderConfig:
    enabled: bool
    model: str
    timeout_seconds: float
    max_input_chars: int
    max_output_tokens: int
    include_internal_notes: bool


class CaseAIPacketBuilder:
    def __init__(self, *, max_input_chars: int, include_internal_notes: bool = True) -> None:
        self._max_input_chars = max_input_chars
        self._include_internal_notes = include_internal_notes

    def build(self, detail: CaseDetail, *, sla_state: str) -> AIReaderPacket:
        thread_lines = [
            self._clip(f"{entry.direction}: {entry.body}", 280)
            for entry in detail.thread_entries[-6:]
        ]
        note_lines: list[str] = []
        if self._include_internal_notes:
            note_lines = [
                self._clip(f"{note.author_label}: {note.body}", 240)
                for note in detail.internal_notes[-3:]
            ]
        packet = AIReaderPacket(
            case_id=str(detail.case_id),
            case_display_number=detail.case_display_number,
            customer_label=detail.customer_label,
            commercial_status=detail.commercial_status,
            operational_status=detail.operational_status,
            waiting_state=detail.waiting_state,
            priority=detail.priority,
            escalation_level=detail.escalation_level,
            assignment_label=detail.assignment_label,
            linked_quote_display_number=detail.linked_quote_display_number,
            linked_order_display_number=detail.linked_order_display_number,
            sla_state=sla_state,
            delivery_status_summary=detail.last_delivery.status if detail.last_delivery else "none",
            customer_thread_recent=thread_lines,
            internal_notes_recent=note_lines,
        )
        return self._truncate_packet(packet)

    def _truncate_packet(self, packet: AIReaderPacket) -> AIReaderPacket:
        raw = packet.model_dump_json()
        if len(raw) <= self._max_input_chars:
            return packet
        trimmed = packet.model_copy(deep=True)
        while len(trimmed.model_dump_json()) > self._max_input_chars and trimmed.customer_thread_recent:
            trimmed.customer_thread_recent.pop(0)
        while len(trimmed.model_dump_json()) > self._max_input_chars and trimmed.internal_notes_recent:
            trimmed.internal_notes_recent.pop(0)
        return trimmed

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"


class AIReaderService:
    def __init__(self, config: AIReaderConfig, client: AIReaderClient | None) -> None:
        self._config = config
        self._client = client
        self._packet_builder = CaseAIPacketBuilder(
            max_input_chars=config.max_input_chars,
            include_internal_notes=config.include_internal_notes,
        )

    async def analyze_case(self, detail: CaseDetail, *, sla_state: str) -> AIReaderResult:
        if not self._config.enabled:
            return AIReaderResult(ok=False, error_message="AI reader is disabled.")
        if not self._client:
            return AIReaderResult(ok=False, error_message="AI provider is not configured.")

        packet = self._packet_builder.build(detail, sla_state=sla_state)
        logger.info(
            "ai_reader_case_analysis_started",
            case_id=str(detail.case_id),
            case_display_number=detail.case_display_number,
            model=self._config.model,
        )
        try:
            payload = await self._client.complete_json(
                model=self._config.model,
                system_prompt=_reader_system_prompt(),
                user_prompt=_reader_user_prompt(packet),
                schema=AIReaderAnalysis.model_json_schema(),
                timeout_seconds=self._config.timeout_seconds,
                max_output_tokens=self._config.max_output_tokens,
            )
            analysis = AIReaderAnalysis.model_validate(payload)
        except httpx.TimeoutException:
            logger.warning("ai_reader_case_analysis_timeout", case_id=str(detail.case_id), model=self._config.model)
            return AIReaderResult(ok=False, error_message="AI timed out. Try refresh.", model=self._config.model)
        except httpx.HTTPError as exc:
            logger.warning(
                "ai_reader_case_analysis_provider_error",
                case_id=str(detail.case_id),
                model=self._config.model,
                error=str(exc),
            )
            return AIReaderResult(ok=False, error_message="AI is temporarily unavailable.", model=self._config.model)
        except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as exc:
            logger.warning(
                "ai_reader_case_analysis_parse_error",
                case_id=str(detail.case_id),
                model=self._config.model,
                error=str(exc),
            )
            return AIReaderResult(ok=False, error_message="AI returned invalid analysis.", model=self._config.model)

        logger.info(
            "ai_reader_case_analysis_succeeded",
            case_id=str(detail.case_id),
            model=self._config.model,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        return AIReaderResult(ok=True, analysis=analysis, model=self._config.model)


def _reader_system_prompt() -> str:
    return (
        "You are ManagerBot AI Reader. "
        "You are read-only and advisory. "
        "Use only provided case packet facts. "
        "Do not invent data, do not claim actions were taken, "
        "and avoid legal or financial certainty unless directly grounded in packet text. "
        "Return strict JSON that matches the schema exactly."
    )


def _reader_user_prompt(packet: AIReaderPacket) -> str:
    return (
        "Analyze this manager case packet for reader mode. "
        "Provide concise summary, intent, risk flags, missing info, and the next manager step.\n\n"
        f"CASE_PACKET_JSON:\n{packet.model_dump_json(indent=2)}"
    )
