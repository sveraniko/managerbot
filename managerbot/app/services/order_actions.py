from __future__ import annotations

from dataclasses import dataclass

from app.models import CaseDetail


@dataclass(frozen=True, slots=True)
class HandoffTargets:
    production_chat_id: int | None = None
    warehouse_chat_id: int | None = None
    accountant_chat_id: int | None = None

    def chat_id_for(self, key: str) -> int | None:
        return {
            "production": self.production_chat_id,
            "warehouse": self.warehouse_chat_id,
            "accountant": self.accountant_chat_id,
        }.get(key)


def has_order(detail: CaseDetail) -> bool:
    return detail.linked_order_display_number is not None


def has_order_pdf(detail: CaseDetail) -> bool:
    return bool(detail.linked_order_pdf_url)


def build_order_compact_summary(detail: CaseDetail, *, handoff_target_label: str | None = None) -> str:
    lines = [
        f"Order #{detail.linked_order_display_number}",
        f"Case #{detail.case_display_number}",
        f"Customer: {detail.customer_label or 'Unavailable'}",
        f"Priority/Escalation: {detail.priority.upper()}/{detail.escalation_level}",
        f"Operational: {detail.operational_status}/{detail.waiting_state}",
    ]
    if detail.linked_order_status:
        lines.append(f"Order status: {detail.linked_order_status}")
    if detail.linked_order_summary:
        lines.append(f"Order cue: {detail.linked_order_summary}")
    if handoff_target_label:
        lines.append(f"Handoff target: {handoff_target_label}")
    if detail.linked_order_pdf_url:
        label = detail.linked_order_document_label or "Order PDF"
        lines.append(f"{label}: {detail.linked_order_pdf_url}")
    else:
        lines.append("Order PDF: not available from backbone")
    return "\n".join(lines)


def target_label(key: str) -> str:
    return {
        "production": "Production",
        "warehouse": "Warehouse",
        "accountant": "Accountant",
    }.get(key, key)
