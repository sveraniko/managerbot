from uuid import uuid4

from app.bot.keyboards import contact_actions_keyboard
from app.models import CaseDetail, CustomerCard, SearchResultItem
from app.services.rendering import render_contact_actions_panel, render_search_results


def _texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_contact_actions_keyboard_is_data_driven() -> None:
    rich = CustomerCard(label="Acme", telegram_chat_id=40001, telegram_user_id=7777, telegram_username="acme_mgr", phone_number="+1555001")
    rich_kb = contact_actions_keyboard(rich)
    rich_texts = _texts(rich_kb)
    assert "Open Telegram direct" in rich_texts
    assert "Show @username" in rich_texts
    assert "Show chat ID" in rich_texts
    assert "Show phone" in rich_texts

    sparse = CustomerCard(label="Acme")
    sparse_kb = contact_actions_keyboard(sparse)
    sparse_texts = _texts(sparse_kb)
    assert "Open Telegram direct" not in sparse_texts
    assert "Show @username" not in sparse_texts
    assert "Show chat ID" not in sparse_texts
    assert "Show phone" not in sparse_texts
    assert "Log contact outcome note" in sparse_texts


def test_contact_panel_and_search_identity_are_consistent() -> None:
    case_id = uuid4()
    detail = CaseDetail(
        case_id=case_id,
        case_display_number=501,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="vip",
        escalation_level="manager_attention",
        assignment_label="Assigned to me",
        linked_quote_display_number=501,
        customer_label="ACME",
        customer_card=CustomerCard(label="ACME", actor_id="cust", telegram_chat_id=40001),
    )

    contact_panel = render_contact_actions_panel(detail)
    assert "Label: ACME" in contact_panel

    search = render_search_results(
        "acme",
        [
            SearchResultItem(
                case_id=case_id,
                case_display_number=501,
                linked_order_display_number=None,
                customer_label="ACME",
                customer_actor_id="cust",
                customer_telegram_chat_id=40001,
                operational_status="active",
                waiting_state="waiting_manager",
                priority="vip",
                escalation_level="manager_attention",
                is_archived=False,
            )
        ],
    )
    assert "| ACME |" in search
