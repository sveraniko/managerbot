from datetime import datetime, timezone

from app.models import CaseDetail, HotTaskItem, ManagerActor, PresenceStatus, QueueItem
from app.services.ai_reader import AIReaderAnalysis
from app.services.ai_recommender import AIRecommendation
from app.services.ai_state import AISnapshotMeta
from app.services.sla import SlaService


def render_hub(
    actor: ManagerActor,
    presence: PresenceStatus,
    counts: dict[str, int],
    hot_tasks: dict[str, list[HotTaskItem]],
) -> str:
    active_load = sum(len(items) for items in hot_tasks.values())
    summary_line = (
        f"Attention: {active_load} | overdue: {counts.get('sla_overdue', 0)} | "
        f"failed delivery: {len(hot_tasks.get('failed_delivery', []))} | new business: {len(hot_tasks.get('new_business', []))}"
    )
    head = (
        f"ManagerBot Hub\\n"
        f"Manager: {actor.display_name} ({actor.role.value})\\n"
        f"Presence: {presence.value}\\n\\n"
        f"{summary_line}\\n\\n"
        f"Hot Tasks\\n"
    )
    buckets = [
        ("needs_reply_now", "Needs reply now"),
        ("new_business", "New business"),
        ("sla_at_risk", "SLA at risk"),
        ("urgent_escalated", "Urgent / VIP / escalated"),
        ("failed_delivery", "Failed delivery"),
    ]
    lines = [head]
    for key, title in buckets:
        items = hot_tasks.get(key, [])
        lines.append(f"{title}: {len(items)}")
        if not items:
            lines.append("- none")
            continue
        for item in items:
            lines.append(f"- {_render_hot_task_item(item)}")
        lines.append("")

    lines.append(
        f"Queues\\n"
        f"New/Unassigned: {counts.get('new', 0)}\\n"
        f"Assigned to me: {counts.get('mine', 0)}\\n"
        f"Waiting for me: {counts.get('waiting_me', 0)}\\n"
        f"Waiting for customer: {counts.get('waiting_customer', 0)}\\n"
        f"Urgent: {counts.get('urgent', 0)}\\n"
        f"Escalated: {counts.get('escalated', 0)}\\n"
        f"SLA near: {counts.get('sla_near', 0)}\\n"
        f"SLA overdue: {counts.get('sla_overdue', 0)}"
    )
    return "\\n".join(lines)


def render_queue(queue_key: str, items: list[QueueItem], offset: int) -> str:
    sla = SlaService()
    lines = [f"Queue: {queue_key}", f"Offset: {offset}", ""]
    for item in items:
        sla_state = sla.classify(item.sla_due_at)
        lines.append(
            f"#{item.case_display_number} | {item.customer_label or '-'} | {item.operational_status}/{item.waiting_state} | sla:{sla_state} | p:{item.priority} e:{item.escalation_level}"
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
        f"Priority/Escalation: {detail.priority}/{detail.escalation_level}",
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


def _render_hot_task_item(item: HotTaskItem) -> str:
    sla = SlaService().classify(item.sla_due_at)
    cue = "t:-"
    marker_ts = item.failed_delivery_at or item.last_customer_message_at or item.sla_due_at
    if marker_ts:
        dt = marker_ts if marker_ts.tzinfo else marker_ts.replace(tzinfo=timezone.utc)
        delta_minutes = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
        cue = f"t:{abs(delta_minutes)}m"
    customer = item.customer_label or "-"
    return (
        f"#{item.case_display_number} {customer} | {item.reason} | "
        f"p:{item.priority} e:{item.escalation_level} sla:{sla} {cue}"
    )
