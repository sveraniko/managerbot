from app.models import CaseDetail, ManagerActor, PresenceStatus, QueueItem
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


def render_case_detail(detail: CaseDetail) -> str:
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
    return "\\n".join(head)
