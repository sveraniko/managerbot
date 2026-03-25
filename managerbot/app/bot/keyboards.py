from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import MBCallback
from app.models import QueueItem


def hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Presence", callback_data=MBCallback(action="presence").pack())],
            [InlineKeyboardButton(text="New/Unassigned", callback_data=MBCallback(action="queue", value="new").pack())],
            [InlineKeyboardButton(text="Assigned to me", callback_data=MBCallback(action="queue", value="mine").pack())],
            [InlineKeyboardButton(text="Waiting for me", callback_data=MBCallback(action="queue", value="waiting_me").pack())],
            [InlineKeyboardButton(text="Waiting for customer", callback_data=MBCallback(action="queue", value="waiting_customer").pack())],
            [InlineKeyboardButton(text="Urgent", callback_data=MBCallback(action="queue", value="urgent").pack())],
            [InlineKeyboardButton(text="Escalated", callback_data=MBCallback(action="queue", value="escalated").pack())],
            [InlineKeyboardButton(text="Refresh", callback_data=MBCallback(action="refresh", value="hub").pack())],
        ]
    )


def queue_keyboard(items: list[QueueItem]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"Case #{item.case_display_number}", callback_data=MBCallback(action="case", value=str(item.case_id)).pack())] for item in items]
    rows.append([InlineKeyboardButton(text="Load more", callback_data=MBCallback(action="load_more").pack())])
    rows.append([InlineKeyboardButton(text="Back", callback_data=MBCallback(action="back").pack()), InlineKeyboardButton(text="Home", callback_data=MBCallback(action="home").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def case_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Claim / Take into work", callback_data=MBCallback(action="claim").pack())],
            [InlineKeyboardButton(text="Refresh", callback_data=MBCallback(action="refresh", value="case").pack())],
            [InlineKeyboardButton(text="Back", callback_data=MBCallback(action="back").pack()), InlineKeyboardButton(text="Home", callback_data=MBCallback(action="home").pack())],
        ]
    )
