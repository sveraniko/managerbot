from __future__ import annotations

from typing import Any

ESCALATION_NONE = "none"
ESCALATION_MANAGER_ATTENTION = "manager_attention"
ESCALATION_OWNER_ATTENTION = "owner_attention"

_CANONICAL_BY_RANK = {
    0: ESCALATION_NONE,
    1: ESCALATION_MANAGER_ATTENTION,
    2: ESCALATION_OWNER_ATTENTION,
}


def normalize_escalation_level(value: Any) -> str:
    """Normalize runtime escalation values to the canonical launch enum."""
    if value is None:
        return ESCALATION_NONE

    if isinstance(value, bool):
        return ESCALATION_MANAGER_ATTENTION if value else ESCALATION_NONE

    if isinstance(value, (int, float)):
        return _CANONICAL_BY_RANK.get(_numeric_rank(value), ESCALATION_OWNER_ATTENTION)

    text = str(value).strip().lower()
    if text in {"", "none", "null", "false"}:
        return ESCALATION_NONE
    if text in {"manager_attention", "manager", "low", "1", "1.0", "true"}:
        return ESCALATION_MANAGER_ATTENTION
    if text in {"owner_attention", "owner", "high", "2", "2.0"}:
        return ESCALATION_OWNER_ATTENTION
    try:
        as_num = float(text)
    except ValueError:
        return ESCALATION_NONE
    return _CANONICAL_BY_RANK.get(_numeric_rank(as_num), ESCALATION_OWNER_ATTENTION)


def escalation_rank(value: Any) -> int:
    normalized = normalize_escalation_level(value)
    if normalized == ESCALATION_MANAGER_ATTENTION:
        return 1
    if normalized == ESCALATION_OWNER_ATTENTION:
        return 2
    return 0


def is_escalated(value: Any) -> bool:
    return escalation_rank(value) > 0


def _numeric_rank(value: int | float) -> int:
    if value <= 0:
        return 0
    if value <= 1:
        return 1
    return 2
