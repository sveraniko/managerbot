from __future__ import annotations


TOP_TIER_PRIORITIES = {"urgent", "vip"}
ELEVATED_PRIORITIES = {"high", *TOP_TIER_PRIORITIES}


def priority_rank(priority: str) -> int:
    """Business ordering rank where lower means higher prominence."""
    if priority in TOP_TIER_PRIORITIES:
        return 0
    if priority == "high":
        return 1
    return 2


def is_top_tier_priority(priority: str) -> bool:
    return priority in TOP_TIER_PRIORITIES


def is_high_or_higher_priority(priority: str) -> bool:
    return priority in ELEVATED_PRIORITIES
