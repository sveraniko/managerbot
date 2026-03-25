from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, Message


class PanelManager:
    def __init__(self) -> None:
        self._message_ids: dict[int, int] = {}

    async def render(self, message: Message, text: str, reply_markup: InlineKeyboardMarkup) -> None:
        key = message.chat.id
        message_id = self._message_ids.get(key)
        if message_id:
            try:
                await message.bot.edit_message_text(text, chat_id=message.chat.id, message_id=message_id, reply_markup=reply_markup)
                return
            except Exception:
                pass
        sent = await message.answer(text, reply_markup=reply_markup)
        self._message_ids[key] = sent.message_id
