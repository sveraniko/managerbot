from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import MBCallback
from app.models import HotTaskItem, QueueItem


def hub_keyboard(hot_tasks: dict[str, list[HotTaskItem]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [[InlineKeyboardButton(text="Presence", callback_data=MBCallback(action="presence").pack())]]
    bucket_order = [
        ("needs_reply_now", "Needs reply", "waiting_me"),
        ("new_business", "New business", "new"),
        ("sla_at_risk", "SLA risk", "urgent"),
        ("urgent_escalated", "Urgent/escalated", "urgent"),
        ("failed_delivery", "Failed delivery", "mine"),
    ]
    for key, title, queue_key in bucket_order:
        items = hot_tasks.get(key, [])
        for item in items:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{title}: Case #{item.case_display_number}",
                        callback_data=MBCallback(action="case", value=str(item.case_id)).pack(),
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"See more: {title}",
                    callback_data=MBCallback(action="queue", value=queue_key).pack(),
                )
            ]
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
            [InlineKeyboardButton(text="Reply to customer", callback_data=MBCallback(action="reply_start").pack())],
            [InlineKeyboardButton(text="Add internal note", callback_data=MBCallback(action="note_start").pack())],
            [InlineKeyboardButton(text="AI Analyze + Recommend / Refresh", callback_data=MBCallback(action="ai_analyze").pack())],
            *ai_rows,
            [InlineKeyboardButton(text="Refresh", callback_data=MBCallback(action="refresh", value="case").pack())],
            [InlineKeyboardButton(text="Back", callback_data=MBCallback(action="back").pack()), InlineKeyboardButton(text="Home", callback_data=MBCallback(action="home").pack())],
        ]
    )


def compose_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data=MBCallback(action="compose_cancel").pack())],
            [InlineKeyboardButton(text="Back to case", callback_data=MBCallback(action="compose_back_case").pack())],
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
