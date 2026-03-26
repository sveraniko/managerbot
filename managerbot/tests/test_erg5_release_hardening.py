from uuid import uuid4

from app.bot.keyboards import case_keyboard, hub_keyboard, queue_keyboard
from app.models import CaseDetail, HotTaskBucket, HotTaskBucketKey, QueueItem
from app.services.rendering import render_contact_actions_panel, render_queue


def _texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_dead_buttons_are_hidden_for_empty_contexts() -> None:
    buckets = [
        HotTaskBucket(HotTaskBucketKey.NEEDS_REPLY_NOW, "Needs reply now", "waiting_me", []),
        HotTaskBucket(HotTaskBucketKey.NEW_BUSINESS, "New business", "new", []),
    ]
    hub = hub_keyboard(buckets)
    labels = _texts(hub)
    assert "Open Needs reply now" not in labels
    assert "Open New business" not in labels

    queue = queue_keyboard([], has_more=False)
    assert "Load more" not in _texts(queue)

    case = case_keyboard(has_contact_actions=False)
    assert "Contact actions" not in _texts(case)


def test_empty_queue_and_contact_panel_rendering_are_honest() -> None:
    rendered_queue = render_queue("archive", [], 0)
    assert "No cases in this queue." in rendered_queue
    assert "Try another lane or adjust filters." in rendered_queue

    detail = CaseDetail(
        case_id=uuid4(),
        case_display_number=1200,
        commercial_status="open",
        operational_status="active",
        waiting_state="waiting_manager",
        priority="normal",
        escalation_level=0,
        assignment_label="Assigned to me",
        linked_quote_display_number=1200,
        customer_label="Acme",
    )
    contact_panel = render_contact_actions_panel(detail)
    assert "Direct channel data is unavailable" in contact_panel


def test_queue_keyboard_shows_load_more_when_page_can_continue() -> None:
    items = [
        QueueItem(
            case_id=uuid4(),
            case_display_number=100,
            customer_label="Acme",
            operational_status="active",
            waiting_state="waiting_manager",
            assigned_manager_actor_id=None,
            priority="normal",
            escalation_level=0,
            last_customer_message_at=None,
        )
    ]
    labels = _texts(queue_keyboard(items, has_more=True))
    assert "Load more" in labels
