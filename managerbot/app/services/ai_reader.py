from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx
import structlog
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.models import CaseDetail
from app.services.ai_cache import InMemoryAICache

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
    prompt_version: str | None = None
    from_cache: bool = False


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
    prompt_version: str
    timeout_seconds: float
    max_input_chars: int
    max_output_tokens: int
    include_internal_notes: bool
    max_thread_entries: int
    max_internal_notes: int


class CaseAIPacketBuilder:
    def __init__(
        self,
        *,
        max_input_chars: int,
        include_internal_notes: bool = True,
        max_thread_entries: int = 6,
        max_internal_notes: int = 3,
    ) -> None:
        self._max_input_chars = max_input_chars
        self._include_internal_notes = include_internal_notes
        self._max_thread_entries = max(0, max_thread_entries)
        self._max_internal_notes = max(0, max_internal_notes)

    def build(self, detail: CaseDetail, *, sla_state: str) -> AIReaderPacket:
        thread_lines = [
            self._clip(self._sanitize(f"{entry.direction}: {entry.body}"), 280)
            for entry in detail.thread_entries[-self._max_thread_entries :]
        ]
        note_lines: list[str] = []
        if self._include_internal_notes and self._max_internal_notes > 0:
            note_lines = [
                self._clip(self._sanitize(f"{note.author_label}: {note.body}"), 240)
                for note in detail.internal_notes[-self._max_internal_notes :]
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
        trimmed = packet.model_copy(deep=True)
        while len(trimmed.model_dump_json()) > self._max_input_chars and trimmed.customer_thread_recent:
            trimmed.customer_thread_recent.pop(0)
        while len(trimmed.model_dump_json()) > self._max_input_chars and trimmed.internal_notes_recent:
            trimmed.internal_notes_recent.pop(0)
        while len(trimmed.model_dump_json()) > self._max_input_chars and any(
            len(x) > 80 for x in trimmed.customer_thread_recent
        ):
            trimmed.customer_thread_recent = [self._clip(x, max(80, len(x) - 40)) for x in trimmed.customer_thread_recent]
        while len(trimmed.model_dump_json()) > self._max_input_chars and any(
            len(x) > 80 for x in trimmed.internal_notes_recent
        ):
            trimmed.internal_notes_recent = [self._clip(x, max(80, len(x) - 30)) for x in trimmed.internal_notes_recent]
        return trimmed

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    @staticmethod
    def _sanitize(text: str) -> str:
        text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", "[redacted-email]", text)
        text = re.sub(r"\+?\d[\d\s\-()]{6,}\d", "[redacted-number]", text)
        return text


class AIReaderService:
    def __init__(self, config: AIReaderConfig, client: AIReaderClient | None, cache: InMemoryAICache | None = None) -> None:
        self._config = config
        self._client = client
        self._cache = cache
        self._packet_builder = CaseAIPacketBuilder(
            max_input_chars=config.max_input_chars,
            include_internal_notes=config.include_internal_notes,
            max_thread_entries=config.max_thread_entries,
            max_internal_notes=config.max_internal_notes,
        )

    async def analyze_case(self, detail: CaseDetail, *, sla_state: str, force_refresh: bool = False) -> AIReaderResult:
        if not self._config.enabled:
            return AIReaderResult(ok=False, error_message="AI reader is disabled.")
        if not self._client:
            return AIReaderResult(ok=False, error_message="AI provider is not configured.")

        packet = self._packet_builder.build(detail, sla_state=sla_state)
        cache_key = self._cache_key(packet)
        if self._cache and not force_refresh:
            cached = self._cache.get(cache_key)
            if cached:
                try:
                    analysis = AIReaderAnalysis.model_validate(cached["analysis"])
                    return AIReaderResult(
                        ok=True,
                        analysis=analysis,
                        model=self._config.model,
                        prompt_version=self._config.prompt_version,
                        from_cache=True,
                    )
                except Exception:
                    logger.warning("ai_reader_cache_payload_invalid", case_id=str(detail.case_id))
                    self._cache.delete(cache_key)

        logger.info(
            "ai_reader_case_analysis_started",
            case_id=str(detail.case_id),
            case_display_number=detail.case_display_number,
            model=self._config.model,
            prompt_version=self._config.prompt_version,
            force_refresh=force_refresh,
        )
        try:
            payload = await self._client.complete_json(
                model=self._config.model,
                system_prompt=_reader_system_prompt(self._config.prompt_version),
                user_prompt=_reader_user_prompt(packet),
                schema=AIReaderAnalysis.model_json_schema(),
                timeout_seconds=self._config.timeout_seconds,
                max_output_tokens=self._config.max_output_tokens,
            )
            analysis = AIReaderAnalysis.model_validate(payload)
        except httpx.TimeoutException:
            logger.warning("ai_reader_case_analysis_timeout", case_id=str(detail.case_id), model=self._config.model)
            return AIReaderResult(ok=False, error_message="AI timed out. Try refresh.", model=self._config.model, prompt_version=self._config.prompt_version)
        except httpx.HTTPError as exc:
            logger.warning(
                "ai_reader_case_analysis_provider_error",
                case_id=str(detail.case_id),
                model=self._config.model,
                prompt_version=self._config.prompt_version,
                error=str(exc),
            )
            return AIReaderResult(ok=False, error_message="AI is temporarily unavailable.", model=self._config.model, prompt_version=self._config.prompt_version)
        except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as exc:
            logger.warning(
                "ai_reader_case_analysis_parse_error",
                case_id=str(detail.case_id),
                model=self._config.model,
                prompt_version=self._config.prompt_version,
                error=str(exc),
            )
            return AIReaderResult(ok=False, error_message="AI returned invalid analysis.", model=self._config.model, prompt_version=self._config.prompt_version)

        if self._cache:
            self._cache.set(cache_key, {"analysis": analysis.model_dump(mode="json")})
        logger.info(
            "ai_reader_case_analysis_succeeded",
            case_id=str(detail.case_id),
            model=self._config.model,
            prompt_version=self._config.prompt_version,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        return AIReaderResult(
            ok=True,
            analysis=analysis,
            model=self._config.model,
            prompt_version=self._config.prompt_version,
            from_cache=False,
        )

    def build_packet(self, detail: CaseDetail, *, sla_state: str) -> AIReaderPacket:
        return self._packet_builder.build(detail, sla_state=sla_state)

    def _cache_key(self, packet: AIReaderPacket) -> str:
        digest = hashlib.sha256(json.dumps(packet.model_dump(mode="json"), sort_keys=True).encode("utf-8")).hexdigest()
        return f"reader:{self._config.model}:{self._config.prompt_version}:{packet.case_id}:{digest}"


def _reader_system_prompt(prompt_version: str) -> str:
    return (
        f"You are ManagerBot AI Reader (prompt {prompt_version}). "
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
