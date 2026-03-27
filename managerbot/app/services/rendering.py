from datetime import datetime, timezone

from app.models import CaseDetail, CustomerCard, HotTaskBucket, HotTaskItem, ManagerActor, PresenceStatus, QueueFilters, QueueItem, SearchResultItem
from app.services.escalation import is_escalated, normalize_escalation_level
from app.services.ai_reader import AIReaderAnalysis
from app.services.ai_recommender import AIRecommendation
from app.services.ai_state import AISnapshotMeta
from app.services.sla import SlaService


def render_hub(actor: ManagerActor, presence: PresenceStatus, counts: dict[str, int], buckets: list[HotTaskBucket]) -> str:
    presence_label = {
        "online": "🟢 Online",
        "busy": "🟠 Busy",
        "offline": "⚫ Offline",
    }.get(presence.value, presence.value)

    lines = [
        "ManagerBot Workdesk",
        f"{actor.display_name} · {actor.role.value}",
        f"Presence: {presence_label}",
        "",
        "🔥 Hot tasks",
    ]

    any_hot = any(bucket.items for bucket in buckets)
    if not any_hot:
        lines.append("All clear — no urgent items.")
    else:
        for bucket in buckets:
            count = len(bucket.items)
            if count == 0:
                lines.append(f"· {bucket.title}: 0")
            else:
                lines.append(f"🔴 {bucket.title}: {count}")
                for item in bucket.items[:3]:
                    lines.append(f"  — #{item.case_display_number} {item.customer_label or '—'}: {item.reason}")
                if count > 3:
                    lines.append(f"  … and {count - 3} more")

    lines.extend([
        "",
        "📋 Queue summary",
        f"New/Unassigned: {counts.get('new', 0)}",
        f"Assigned to me: {counts.get('mine', 0)}",
        f"Waiting for me: {counts.get('waiting_me', 0)}",
        f"Waiting customer: {counts.get('waiting_customer', 0)}",
        f"Urgent: {counts.get('urgent', 0)}",
        f"Escalated: {counts.get('escalated', 0)}",
    ])
    return "\n".join(lines)


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
        lines.append("Try another lane or adjust filters.")
    return "\n".join(lines)


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
    head.extend(_render_order_action_block(detail))
    if detail.last_delivery:
        delivery_line = f"Delivery: {detail.last_delivery.status}"
        if detail.last_delivery.error_message:
            delivery_line += f" ({detail.last_delivery.error_message})"
        head.append(delivery_line)
    head.extend(_render_customer_card(detail.customer_card or CustomerCard(label=detail.customer_label)))
    head.append("")
    head.append("Direct contact policy: use direct channel for quick clarification; keep case truth via internal note/reply.")
    head.append("\nCustomer thread:")
    if detail.thread_entries:
        for entry in detail.thread_entries[-5:]:
            suffix = f" [{entry.delivery_status}]" if entry.direction == "outbound" else ""
            side = entry.author_side or entry.direction
            head.append(f"- {side}: {_snippet(entry.body, 220)}{suffix}")
    else:
        head.append("- none")
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
    return "\n".join(head)


def render_order_summary_panel(detail: CaseDetail, *, configured_targets: dict[str, bool]) -> str:
    if not detail.linked_order_display_number:
        return (
            f"Order summary · Case #{detail.case_display_number}\n\n"
            "No linked order for this case.\n"
            "Return to case details."
        )
    lines = [
        f"Order summary · Case #{detail.case_display_number}",
        "",
        f"Order: #{detail.linked_order_display_number}",
        f"Quote: #{detail.linked_quote_display_number}",
        f"Customer: {detail.customer_label or 'Unavailable'}",
        f"Operational: {detail.operational_status}/{detail.waiting_state}",
        f"Priority/Escalation: {detail.priority.upper()}/{detail.escalation_level}",
    ]
    if detail.linked_order_status:
        lines.append(f"Order status: {detail.linked_order_status}")
    if detail.linked_order_summary:
        lines.append(f"Order cue: {detail.linked_order_summary}")
    lines.append(f"PDF: {'available' if detail.linked_order_pdf_url else 'not available'}")
    if detail.linked_order_pdf_url:
        lines.append(f"Document ref: {detail.linked_order_document_label or detail.linked_order_pdf_url}")
    lines.append("")
    lines.append("Handoff targets:")
    lines.append(f"- Production: {'configured' if configured_targets.get('production') else 'not configured'}")
    lines.append(f"- Warehouse: {'configured' if configured_targets.get('warehouse') else 'not configured'}")
    lines.append(f"- Accountant: {'configured' if configured_targets.get('accountant') else 'not configured'}")
    lines.append("")
    lines.append("Use compact summary send/handoff actions below.")
    return "\n".join(lines)


def render_contact_actions_panel(detail: CaseDetail) -> str:
    card = detail.customer_card or CustomerCard(label=detail.customer_label)
    lines = [f"Contact actions · Case #{detail.case_display_number}", ""]
    lines.extend(_render_customer_card(card))
    lines.append("")
    lines.append("Direct-contact cues:")
    lines.append("- Use direct contact for urgent clarification / voice discussion when faster than thread.")
    lines.append("- After direct contact, log summary via internal note to keep case operational record coherent.")
    if not _has_contact_data(card):
        lines.append("- Direct channel data is unavailable for this case.")
    return "\\n".join(lines)


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
    if is_escalated(item.escalation_level):
        cues.append(f"esc:{normalize_escalation_level(item.escalation_level)}")
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
        identity_hint = _identity_hint(item.customer_label, item.customer_actor_id, item.customer_telegram_chat_id)
        lines.append(
            f"#{item.case_display_number}{archive_mark}{order_hint} | {identity_hint} | {item.operational_status}/{item.waiting_state} | p:{item.priority} e:{item.escalation_level}"
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


def _render_customer_card(card: CustomerCard) -> list[str]:
    lines = ["Customer card:"]
    lines.append(f"- Label: {card.label or 'Unavailable'}")
    lines.append(f"- Actor ID: {card.actor_id or 'Unavailable'}")
    lines.append(f"- Telegram username: {card.telegram_username or 'Unavailable'}")
    lines.append(f"- Telegram chat ID: {card.telegram_chat_id if card.telegram_chat_id is not None else 'Unavailable'}")
    lines.append(f"- Telegram user ID: {card.telegram_user_id if card.telegram_user_id is not None else 'Unavailable'}")
    lines.append(f"- Phone: {card.phone_number or 'Unavailable'}")
    return lines


def _render_order_action_block(detail: CaseDetail) -> list[str]:
    if not detail.linked_order_display_number:
        return []
    lines = ["", "Order actions:"]
    lines.append(f"- Linked order: #{detail.linked_order_display_number}")
    if detail.linked_order_status:
        lines.append(f"- Status: {detail.linked_order_status}")
    if detail.linked_order_summary:
        lines.append(f"- Cue: {_snippet(detail.linked_order_summary, 160)}")
    lines.append(f"- PDF/document: {'available' if detail.linked_order_pdf_url else 'not available'}")
    lines.append("- Open order summary for share/handoff actions.")
    return lines


def _identity_hint(label: str | None, actor_id: str | None, telegram_chat_id: int | None) -> str:
    if label:
        return label
    if actor_id:
        return f"actor:{actor_id}"
    if telegram_chat_id is not None:
        return f"chat:{telegram_chat_id}"
    return "-"


def _has_contact_data(card: CustomerCard) -> bool:
    return any((card.telegram_username, card.telegram_chat_id, card.telegram_user_id, card.phone_number))
