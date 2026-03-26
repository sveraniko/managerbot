from app.models import CaseDetail, ManagerActor, PresenceStatus, QueueItem
from app.services.ai_reader import AIReaderAnalysis
from app.services.ai_recommender import AIRecommendation
from app.services.sla import SlaService


def render_hub(actor: ManagerActor, presence: PresenceStatus, counts: dict[str, int]) -> str:
    return (
        f"ManagerBot Hub\\n"
        f"Manager: {actor.display_name} ({actor.role.value})\\n"
        f"Presence: {presence.value}\\n\\n"
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
    ai_recommendation: AIRecommendation | None = None,
    ai_recommendation_error: str | None = None,
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
        suffix = ""
        if entry.direction == "outbound":
            suffix = f" [{entry.delivery_status}]"
        head.append(f"- {entry.direction}: {entry.body}{suffix}")
    head.append("\nInternal notes:")
    if detail.internal_notes:
        for note in detail.internal_notes[-3:]:
            head.append(f"- {note.author_label}: {note.body}")
    else:
        head.append("- none")
    head.append("\nAI reader (advisory only):")
    if ai_error:
        head.append(f"- unavailable: {ai_error}")
    elif ai_analysis:
        head.append(f"- Summary: {ai_analysis.summary}")
        head.append(f"- Customer intent: {ai_analysis.customer_intent}")
        if ai_analysis.risk_flags:
            head.append(f"- Risk flags: {', '.join(ai_analysis.risk_flags)}")
        else:
            head.append("- Risk flags: none")
        if ai_analysis.missing_information:
            head.append(f"- Missing info: {', '.join(ai_analysis.missing_information)}")
        else:
            head.append("- Missing info: none")
        head.append(f"- Recommended next step: {ai_analysis.recommended_next_step}")
        head.append(f"- Confidence: {ai_analysis.confidence:.2f}")
    else:
        head.append("- No AI analysis yet. Tap AI Analyze.")
    head.append("\nAI recommendations (advisory only — no auto-actions):")
    if ai_recommendation_error:
        head.append(f"- unavailable: {ai_recommendation_error}")
    elif ai_recommendation:
        head.append(f"- Recommended action: {ai_recommendation.recommended_action.value}")
        head.append(f"- Next step: {ai_recommendation.recommended_next_step}")
        head.append(f"- Reply draft: {_snippet(ai_recommendation.draft_reply)}")
        head.append(f"- Internal note draft: {_snippet(ai_recommendation.draft_internal_note)}")
        if ai_recommendation.clarification_questions:
            head.append(f"- Clarifications: {'; '.join(ai_recommendation.clarification_questions)}")
        else:
            head.append("- Clarifications: none")
        if ai_recommendation.escalation_recommendation:
            rationale = ai_recommendation.escalation_reason or "No rationale provided."
            head.append(f"- Escalation suggested: yes ({rationale})")
        else:
            head.append("- Escalation suggested: no")
        head.append(f"- Confidence: {ai_recommendation.confidence:.2f}")
    else:
        head.append("- No recommendation yet. Tap AI Analyze + Recommend.")
    return "\\n".join(head)


def _snippet(text: str, limit: int = 140) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
