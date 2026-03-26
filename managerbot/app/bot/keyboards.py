from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import MBCallback
from app.models import CustomerCard, HotTaskBucket, QueueFilters, QueueItem, SearchResultItem


def hub_keyboard(buckets: list[HotTaskBucket]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Presence", callback_data=MBCallback(action="presence").pack())],
        [InlineKeyboardButton(text="Search case/order/customer", callback_data=MBCallback(action="search_start").pack())],
        [InlineKeyboardButton(text="Filters", callback_data=MBCallback(action="filters_open").pack())],
        [InlineKeyboardButton(text="Archive / history", callback_data=MBCallback(action="queue", value="archive").pack())],
    ]
    for bucket in buckets:
        for item in bucket.items:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{_bucket_short(bucket.title)} · Case #{item.case_display_number}",
                        callback_data=MBCallback(action="case", value=str(item.case_id)).pack(),
                    )
                ]
            )
        rows.append(
            [InlineKeyboardButton(text=f"Open {bucket.title}", callback_data=MBCallback(action="queue", value=bucket.queue_key).pack())]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="New/Unassigned", callback_data=MBCallback(action="queue", value="new").pack())],
            [InlineKeyboardButton(text="Assigned to me", callback_data=MBCallback(action="queue", value="mine").pack())],
            [InlineKeyboardButton(text="Waiting for me", callback_data=MBCallback(action="queue", value="waiting_me").pack())],
            [InlineKeyboardButton(text="Waiting for customer", callback_data=MBCallback(action="queue", value="waiting_customer").pack())],
            [InlineKeyboardButton(text="Urgent", callback_data=MBCallback(action="queue", value="urgent").pack())],
            [InlineKeyboardButton(text="Escalated", callback_data=MBCallback(action="queue", value="escalated").pack())],
            [InlineKeyboardButton(text="Refresh", callback_data=MBCallback(action="refresh", value="hub").pack())],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def queue_keyboard(items: list[QueueItem]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"Case #{item.case_display_number}", callback_data=MBCallback(action="case", value=str(item.case_id)).pack())] for item in items]
    rows.append([InlineKeyboardButton(text="Load more", callback_data=MBCallback(action="load_more").pack())])
    rows.append([InlineKeyboardButton(text="Search", callback_data=MBCallback(action="search_start").pack())])
    rows.append([InlineKeyboardButton(text="Filters", callback_data=MBCallback(action="filters_open").pack())])
    rows.append([InlineKeyboardButton(text="Back", callback_data=MBCallback(action="back").pack()), InlineKeyboardButton(text="Home", callback_data=MBCallback(action="home").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def case_keyboard(*, has_ai_recommendation: bool = False, ai_low_confidence: bool = False) -> InlineKeyboardMarkup:
    ai_rows = []
    if has_ai_recommendation:
        reply_label = "Use AI reply draft" if not ai_low_confidence else "Use AI reply draft ⚠"
        note_label = "Use AI note draft" if not ai_low_confidence else "Use AI note draft ⚠"
        ai_rows.extend(
            [
                [InlineKeyboardButton(text=reply_label, callback_data=MBCallback(action="ai_use_reply_draft").pack())],
                [InlineKeyboardButton(text=note_label, callback_data=MBCallback(action="ai_use_note_draft").pack())],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Claim / Take into work", callback_data=MBCallback(action="claim").pack())],
            [InlineKeyboardButton(text="Escalate to owner", callback_data=MBCallback(action="escalate_owner").pack())],
            [
                InlineKeyboardButton(text="Priority: normal", callback_data=MBCallback(action="set_priority", value="normal").pack()),
                InlineKeyboardButton(text="Priority: high", callback_data=MBCallback(action="set_priority", value="high").pack()),
            ],
            [
                InlineKeyboardButton(text="Priority: urgent", callback_data=MBCallback(action="set_priority", value="urgent").pack()),
                InlineKeyboardButton(text="Priority: VIP", callback_data=MBCallback(action="set_priority", value="vip").pack()),
            ],
            [InlineKeyboardButton(text="Reply to customer", callback_data=MBCallback(action="reply_start").pack())],
            [InlineKeyboardButton(text="Add internal note", callback_data=MBCallback(action="note_start").pack())],
            [InlineKeyboardButton(text="Contact actions", callback_data=MBCallback(action="contact_panel").pack())],
            [InlineKeyboardButton(text="AI Analyze + Recommend / Refresh", callback_data=MBCallback(action="ai_analyze").pack())],
            *ai_rows,
            [InlineKeyboardButton(text="Refresh", callback_data=MBCallback(action="refresh", value="case").pack())],
            [InlineKeyboardButton(text="Back", callback_data=MBCallback(action="back").pack()), InlineKeyboardButton(text="Home", callback_data=MBCallback(action="home").pack())],
        ]
    )


def contact_actions_keyboard(card: CustomerCard) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    direct_link = _telegram_direct_link(card)
    if direct_link:
        rows.append([InlineKeyboardButton(text="Open Telegram direct", url=direct_link)])
    if card.telegram_username:
        rows.append(
            [InlineKeyboardButton(text="Show @username", callback_data=MBCallback(action="contact_copy", value="username").pack())]
        )
    if card.telegram_chat_id is not None:
        rows.append(
            [InlineKeyboardButton(text="Show chat ID", callback_data=MBCallback(action="contact_copy", value="chat_id").pack())]
        )
    if card.telegram_user_id is not None:
        rows.append(
            [InlineKeyboardButton(text="Show user ID", callback_data=MBCallback(action="contact_copy", value="user_id").pack())]
        )
    if card.phone_number:
        rows.append([InlineKeyboardButton(text="Show phone", callback_data=MBCallback(action="contact_copy", value="phone").pack())])
    rows.append([InlineKeyboardButton(text="Log contact outcome note", callback_data=MBCallback(action="log_contact_outcome").pack())])
    rows.append([InlineKeyboardButton(text="Back to case", callback_data=MBCallback(action="contact_back").pack())])
    rows.append([InlineKeyboardButton(text="Home", callback_data=MBCallback(action="home").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def compose_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data=MBCallback(action="compose_cancel").pack())],
            [InlineKeyboardButton(text="Back to case", callback_data=MBCallback(action="compose_back_case").pack())],
        ]
    )


def search_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Cancel search", callback_data=MBCallback(action="search_cancel").pack())],
            [InlineKeyboardButton(text="Home", callback_data=MBCallback(action="home").pack())],
        ]
    )


def search_results_keyboard(results: list[SearchResultItem]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"Case #{r.case_display_number}", callback_data=MBCallback(action="case", value=str(r.case_id)).pack())]
        for r in results
    ]
    rows.append([InlineKeyboardButton(text="New search", callback_data=MBCallback(action="search_start").pack())])
    rows.append([InlineKeyboardButton(text="Filters", callback_data=MBCallback(action="filters_open").pack())])
    rows.append([InlineKeyboardButton(text="Back", callback_data=MBCallback(action="back").pack()), InlineKeyboardButton(text="Home", callback_data=MBCallback(action="home").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def filters_keyboard(filters: QueueFilters) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Lifecycle: {filters.lifecycle_scope}", callback_data=MBCallback(action="filter_cycle", value="lifecycle").pack())],
            [InlineKeyboardButton(text=f"Assignment: {filters.assignment_scope}", callback_data=MBCallback(action="filter_cycle", value="assignment").pack())],
            [InlineKeyboardButton(text=f"Waiting: {filters.waiting_scope}", callback_data=MBCallback(action="filter_cycle", value="waiting").pack())],
            [InlineKeyboardButton(text=f"Priority: {filters.priority_scope}", callback_data=MBCallback(action="filter_cycle", value="priority").pack())],
            [InlineKeyboardButton(text=f"Escalation: {filters.escalation_scope}", callback_data=MBCallback(action="filter_cycle", value="escalation").pack())],
            [InlineKeyboardButton(text=f"SLA: {filters.sla_scope}", callback_data=MBCallback(action="filter_cycle", value="sla").pack())],
            [InlineKeyboardButton(text="Reset filters", callback_data=MBCallback(action="filters_reset").pack())],
            [InlineKeyboardButton(text="Apply / Back", callback_data=MBCallback(action="back").pack())],
            [InlineKeyboardButton(text="Home", callback_data=MBCallback(action="home").pack())],
        ]
    )


def note_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Save note draft", callback_data=MBCallback(action="note_save_draft").pack())],
            [InlineKeyboardButton(text="Edit", callback_data=MBCallback(action="note_edit").pack())],
            [InlineKeyboardButton(text="Cancel", callback_data=MBCallback(action="compose_cancel").pack())],
        ]
    )


def reply_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Confirm send", callback_data=MBCallback(action="reply_confirm").pack())],
            [InlineKeyboardButton(text="Edit", callback_data=MBCallback(action="reply_edit").pack())],
            [InlineKeyboardButton(text="Cancel", callback_data=MBCallback(action="compose_cancel").pack())],
        ]
    )


def _bucket_short(title: str) -> str:
    mapping = {
        "Needs reply now": "Reply",
        "New business": "New",
        "SLA at risk": "SLA",
        "Urgent / VIP / escalated": "Urgent",
        "Failed delivery": "Failed",
    }
    return mapping.get(title, "Hot")


def _telegram_direct_link(card: CustomerCard) -> str | None:
    if card.telegram_username:
        handle = card.telegram_username.lstrip("@")
        return f"https://t.me/{handle}"
    user_id = card.telegram_user_id if card.telegram_user_id is not None else card.telegram_chat_id
    if user_id is not None and int(user_id) > 0:
        return f"tg://user?id={int(user_id)}"
    return None
