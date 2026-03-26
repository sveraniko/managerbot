from datetime import datetime, timezone

from app.models import CaseDetail, HotTaskBucket, HotTaskItem, ManagerActor, PresenceStatus, QueueFilters, QueueItem, SearchResultItem
from app.services.ai_reader import AIReaderAnalysis
from app.services.ai_recommender import AIRecommendation
from app.services.ai_state import AISnapshotMeta
from app.services.sla import SlaService


def render_hub(actor: ManagerActor, presence: PresenceStatus, counts: dict[str, int], buckets: list[HotTaskBucket]) -> str:
    attention_load = len([bucket for bucket in buckets if bucket.items])
    lines = [
        "ManagerBot Workdesk",
        f"Manager: {actor.display_name} ({actor.role.value})",
        f"Presence: {presence.value}",
        (
            f"Attention: buckets {attention_load}/5 | "
            f"overdue {counts.get('sla_overdue', 0)} | failed {len(_bucket_items(buckets, 'failed_delivery'))} | "
            f"new {counts.get('new', 0)}"
        ),
        "",
        "Hot tasks",
    ]
    for bucket in buckets:
        lines.append(f"{bucket.title}: {len(bucket.items)}")
        if not bucket.items:
            lines.append("- none")
            continue
        for item in bucket.items:
            lines.append(f"- {_render_hot_task_item(item)}")

    lines.extend(
        [
            "",
            "Queue summary",
            f"New/Unassigned: {counts.get('new', 0)}",
            f"Assigned to me: {counts.get('mine', 0)}",
            f"Waiting for me: {counts.get('waiting_me', 0)}",
            f"Waiting for customer: {counts.get('waiting_customer', 0)}",
            f"Urgent: {counts.get('urgent', 0)}",
            f"Escalated: {counts.get('escalated', 0)}",
            f"SLA near: {counts.get('sla_near', 0)}",
            f"SLA overdue: {counts.get('sla_overdue', 0)}",
        ]
    )
    return "\\n".join(lines)


def render_queue(queue_key: str, items: list[QueueItem], offset: int, filters: QueueFilters | None = None) -> str:
    sla = SlaService()
    lines = [f"Queue: {queue_key}", f"Offset: {offset}"]
    if filters:
        lines.append(f"Filters: {render_filters(filters)}")
    lines.append("")
    for item in items:
        sla_state = sla.classify(item.sla_due_at)
        archive_mark = " [ARCHIVE]" if item.is_archived else ""
        lines.append(
            f"#{item.case_display_number}{archive_mark} | {item.customer_label or '-'} | {item.operational_status}/{item.waiting_state} | sla:{sla_state} | p:{item.priority} e:{item.escalation_level}"
        )
    if not items:
        lines.append("No cases in this queue.")
    return "\\n".join(lines)


def render_case_detail(
    detail: CaseDetail,
    *,
    ai_analysis: AIReaderAnalysis | None = None,
    ai_error: str | None = None,
    ai_analysis_meta: AISnapshotMeta | None = None,
    ai_recommendation: AIRecommendation | None = None,
    ai_recommendation_error: str | None = None,
    ai_recommendation_meta: AISnapshotMeta | None = None,
    low_confidence_threshold: float = 0.65,
) -> str:
    sla_state = SlaService().classify(detail.sla_due_at)
    head = [
        f"Case #{detail.case_display_number}",
        f"Commercial: {detail.commercial_status}",
        f"Operational: {detail.operational_status}",
        f"Waiting: {detail.waiting_state}",
        f"Assignment: {detail.assignment_label}",
        f"Priority/Escalation: {detail.priority.upper()}/{detail.escalation_level}",
        f"SLA: {sla_state}",
        f"Quote #{detail.linked_quote_display_number}",
    ]
    if detail.linked_order_display_number:
        head.append(f"Order #{detail.linked_order_display_number}")
    if detail.last_delivery:
        delivery_line = f"Delivery: {detail.last_delivery.status}"
        if detail.last_delivery.error_message:
            delivery_line += f" ({detail.last_delivery.error_message})"
        head.append(delivery_line)
    head.append("\nCustomer thread:")
    for entry in detail.thread_entries[-5:]:
        suffix = f" [{entry.delivery_status}]" if entry.direction == "outbound" else ""
        head.append(f"- {entry.direction}: {_snippet(entry.body, 220)}{suffix}")
    head.append("\nInternal notes:")
    if detail.internal_notes:
        for note in detail.internal_notes[-3:]:
            head.append(f"- {note.author_label}: {_snippet(note.body, 180)}")
    else:
        head.append("- none")

    head.append("\nAI reader (advisory only):")
    if ai_error:
        head.append(f"- unavailable: {ai_error}")
    elif ai_analysis:
        if ai_analysis_meta and ai_analysis_meta.model:
            source = "cached" if ai_analysis_meta.from_cache else "fresh"
            head.append(f"- Model/prompt: {ai_analysis_meta.model} / {ai_analysis_meta.prompt_version} ({source})")
        head.append(f"- Summary: {_snippet(ai_analysis.summary, 240)}")
        head.append(f"- Customer intent: {_snippet(ai_analysis.customer_intent, 180)}")
        head.append(f"- Risk flags: {', '.join(ai_analysis.risk_flags) if ai_analysis.risk_flags else 'none'}")
        head.append(
            f"- Missing info: {', '.join(ai_analysis.missing_information) if ai_analysis.missing_information else 'none'}"
        )
        head.append(f"- Recommended next step: {_snippet(ai_analysis.recommended_next_step, 200)}")
        head.append(f"- Confidence: {ai_analysis.confidence:.2f}")
    else:
        head.append("- No AI analysis yet. Tap AI Analyze.")

    head.append("\nAI recommendations (advisory only — no auto-actions):")
    if ai_recommendation_error:
        head.append(f"- unavailable: {ai_recommendation_error}")
    elif ai_recommendation:
        if ai_recommendation_meta and ai_recommendation_meta.model:
            source = "cached" if ai_recommendation_meta.from_cache else "fresh"
            head.append(f"- Model/prompt: {ai_recommendation_meta.model} / {ai_recommendation_meta.prompt_version} ({source})")
        head.append(f"- Recommended action: {ai_recommendation.recommended_action.value}")
        head.append(f"- Next step: {_snippet(ai_recommendation.recommended_next_step, 220)}")
        head.append(f"- Reply draft: {_snippet(ai_recommendation.draft_reply)}")
        head.append(f"- Internal note draft: {_snippet(ai_recommendation.draft_internal_note)}")
        head.append(
            f"- Clarifications: {'; '.join(ai_recommendation.clarification_questions) if ai_recommendation.clarification_questions else 'none'}"
        )
        if ai_recommendation.escalation_recommendation:
            rationale = ai_recommendation.escalation_reason or "No rationale provided."
            head.append(f"- Escalation suggested: yes ({_snippet(rationale, 180)})")
        else:
            head.append("- Escalation suggested: no")
        confidence_line = f"- Confidence: {ai_recommendation.confidence:.2f}"
        if ai_recommendation.confidence < low_confidence_threshold:
            confidence_line += f" ⚠ low (< {low_confidence_threshold:.2f}); verify before using drafts"
        head.append(confidence_line)
    else:
        head.append("- No recommendation yet. Tap AI Analyze + Recommend.")
    return "\\n".join(head)


def _snippet(text: str, limit: int = 140) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _bucket_items(buckets: list[HotTaskBucket], key: str) -> list[HotTaskItem]:
    for bucket in buckets:
        if bucket.key.value == key:
            return bucket.items
    return []


def _render_hot_task_item(item: HotTaskItem) -> str:
    order_suffix = f" · O#{item.linked_order_display_number}" if item.linked_order_display_number else ""
    customer = item.customer_label or "-"
    cues = [f"p:{item.priority}"]
    if item.escalation_level > 0:
        cues.append(f"esc:{item.escalation_level}")
    if item.sla_due_at:
        cues.append(f"sla:{_age_hint(item.sla_due_at)}")
    if item.last_event_at:
        cues.append(f"t:{_age_hint(item.last_event_at)}")
    return f"#{item.case_display_number}{order_suffix} {customer} — {item.reason} ({', '.join(cues)})"


def render_search_results(query: str, results: list[SearchResultItem], filters: QueueFilters | None = None) -> str:
    lines = [f"Search: {query}"]
    if filters:
        lines.append(f"Filters: {render_filters(filters)}")
    lines.append("")
    if not results:
        lines.append("No cases found.")
        lines.append("Try case/order number or customer label.")
        return "\\n".join(lines)
    for item in results:
        archive_mark = " [ARCHIVE]" if item.is_archived else ""
        order_hint = f" O#{item.linked_order_display_number}" if item.linked_order_display_number else ""
        lines.append(
            f"#{item.case_display_number}{archive_mark}{order_hint} | {item.customer_label or '-'} | {item.operational_status}/{item.waiting_state} | p:{item.priority} e:{item.escalation_level}"
        )
    return "\\n".join(lines)


def render_filters(filters: QueueFilters) -> str:
    return (
        f"lifecycle={filters.lifecycle_scope}, assignment={filters.assignment_scope}, waiting={filters.waiting_scope}, "
        f"priority={filters.priority_scope}, escalation={filters.escalation_scope}, sla={filters.sla_scope}"
    )


def _age_hint(ts: datetime) -> str:
    now = datetime.now(timezone.utc)
    delta = int((now - ts).total_seconds())
    if delta >= 0:
        mins = max(1, delta // 60)
        return f"{mins}m ago"
    mins = max(1, abs(delta) // 60)
    return f"in {mins}m"
