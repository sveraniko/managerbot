from aiogram.filters.callback_data import CallbackData


class MBCallback(CallbackData, prefix="mb4"):
    action: str
    value: str = ""
