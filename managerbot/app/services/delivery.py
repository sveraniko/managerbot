from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # pragma: no cover
    from aiogram import Bot


@dataclass(slots=True)
class DeliveryResult:
    ok: bool
    telegram_message_id: int | None = None
    error_message: str | None = None


class CustomerDeliveryGateway(Protocol):
    async def send_text(self, chat_id: int, text: str) -> DeliveryResult: ...


class TelegramCustomerDeliveryGateway:
    def __init__(self, customer_bot: "Bot") -> None:
        self._customer_bot = customer_bot

    async def send_text(self, chat_id: int, text: str) -> DeliveryResult:
        try:
            message = await self._customer_bot.send_message(chat_id=chat_id, text=text)
        except Exception as exc:  # transport failures must be reflected in ops state
            return DeliveryResult(ok=False, error_message=str(exc))
        return DeliveryResult(ok=True, telegram_message_id=message.message_id)
