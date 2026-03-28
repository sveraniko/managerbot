from datetime import datetime, timezone
from uuid import uuid4

from app.bot.keyboards import case_keyboard, order_actions_keyboard
from app.models import CaseDetail
from app.services.order_actions import HandoffTargets, build_order_compact_summary
from app.services.rendering import render_case_detail, render_order_summary_panel


def _texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_order_block_renders_only_when_case_has_linked_order() -> None:
    with_order = CaseDetail(
        case_id=uuid4(),
        case_display_number=901,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="urgent",
        escalation_level="manager_attention",
        assignment_label="Assigned to me",
        linked_quote_display_number=901,
        linked_order_display_number=9901,
        thread_entries=[],
    )
    without_order = CaseDetail(
        case_id=uuid4(),
        case_display_number=902,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="normal",
        escalation_level="none",
        assignment_label="Assigned to me",
        linked_quote_display_number=902,
        thread_entries=[],
    )

    rendered_with = render_case_detail(with_order)
    rendered_without = render_case_detail(without_order)

    assert "Order actions:" in rendered_with
    assert "Linked order: #9901" in rendered_with
    assert "Order actions:" not in rendered_without


def test_order_summary_panel_and_handoff_summary_are_compact_and_operational() -> None:
    detail = CaseDetail(
        case_id=uuid4(),
        case_display_number=903,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="vip",
        escalation_level="owner_attention",
        assignment_label="Owner",
        linked_quote_display_number=903,
        linked_order_display_number=9903,
        linked_order_status="approved",
        linked_order_summary="Large order requires same-day packing.",
        linked_order_pdf_url="https://docs.example.local/o-9903.pdf",
        linked_order_document_label="Order PDF",
        customer_label="ACME",
        sla_due_at=datetime.now(timezone.utc),
    )

    panel = render_order_summary_panel(
        detail,
        configured_targets={"production": True, "warehouse": False, "accountant": True},
    )
    assert "Order summary · Case #903" in panel
    assert "Order: #9903" in panel
    assert "PDF: available" in panel
    assert "Warehouse: not configured" in panel

    summary = build_order_compact_summary(detail, handoff_target_label="Production")
    assert "Order #9903" in summary
    assert "Case #903" in summary
    assert "Customer: ACME" in summary
    assert "Handoff target: Production" in summary
    assert "Order PDF: https://docs.example.local/o-9903.pdf" in summary


def test_order_pdf_absence_and_target_configuration_do_not_create_dead_actions() -> None:
    kb = order_actions_keyboard(
        has_pdf=False,
        configured_targets={"production": True, "warehouse": False, "accountant": False},
    )
    texts = _texts(kb)
    assert "Send compact summary here" in texts
    assert "Send PDF/document ref here" not in texts
    assert "Send to production" in texts
    assert "Send to warehouse" not in texts
    assert "Send to accountant" not in texts

    case_kb = case_keyboard(has_order_actions=True, has_contact_actions=True)
    assert "Order summary and handoff" in _texts(case_kb)


def test_handoff_targets_mapping_for_config_safety() -> None:
    targets = HandoffTargets(production_chat_id=10001, warehouse_chat_id=None, accountant_chat_id=10003)
    assert targets.chat_id_for("production") == 10001
    assert targets.chat_id_for("warehouse") is None
    assert targets.chat_id_for("accountant") == 10003
