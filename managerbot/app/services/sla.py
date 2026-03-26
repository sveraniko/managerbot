from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class SlaPolicy:
    near_breach_window: timedelta = timedelta(minutes=30)


class SlaService:
    def __init__(self, policy: SlaPolicy | None = None) -> None:
        self._policy = policy or SlaPolicy()

    def classify(self, sla_due_at: datetime | None, *, now: datetime | None = None) -> str:
        if sla_due_at is None:
            return "healthy"
        ref = now or datetime.now(timezone.utc)
        if sla_due_at <= ref:
            return "overdue"
        if sla_due_at <= ref + self._policy.near_breach_window:
            return "near_breach"
        return "healthy"
