from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MBCallback
from app.bot.keyboards import case_keyboard, hub_keyboard, queue_keyboard
from app.bot.panel_manager import PanelManager
from app.services.access import AccessService
from app.services.manager_surface import ManagerSurfaceService
from app.services.navigation import NavigationService
from app.services.rendering import render_case_detail, render_hub, render_queue
from app.state.manager_session import ManagerSessionStore


def build_router(
    access_service: AccessService,
    session_store: ManagerSessionStore,
    surface_service: ManagerSurfaceService,
    navigation_service: NavigationService,
    panel_manager: PanelManager,
) -> Router:
    router = Router(name="managerbot")

    async def authorize(message: Message):
        actor = await access_service.resolve_authorized_actor(message.from_user.id)
        if not actor:
            await message.answer("Access denied. ManagerBot is available only for OWNER/MANAGER.")
            return None
        return actor

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        actor = await authorize(message)
        if not actor:
            return
        state = await session_store.get(message.from_user.id)
        state.panel_key = "hub:home"
        state.queue_offset = 0
        await session_store.set(message.from_user.id, state)
        presence, counts = await surface_service.hub_view(actor)
        await panel_manager.render(message, render_hub(actor, presence, counts), hub_keyboard())

    @router.callback_query(MBCallback.filter())
    async def cb_handler(callback: CallbackQuery, callback_data: MBCallback) -> None:
        msg = callback.message
        actor = await access_service.resolve_authorized_actor(callback.from_user.id)
        if not actor:
            await callback.answer("Not authorized", show_alert=True)
            return
        state = await session_store.get(callback.from_user.id)

        if callback_data.action == "home":
            state = navigation_service.go_home(state)
            presence, counts = await surface_service.hub_view(actor)
            await panel_manager.render(msg, render_hub(actor, presence, counts), hub_keyboard())
        elif callback_data.action == "presence":
            await surface_service.toggle_presence(actor)
            presence, counts = await surface_service.hub_view(actor)
            await panel_manager.render(msg, render_hub(actor, presence, counts), hub_keyboard())
        elif callback_data.action == "queue":
            state = navigation_service.open_panel(state, f"queue:{callback_data.value}")
            state.queue_key = callback_data.value
            state.queue_offset = 0
            items = await surface_service.queue_page(actor, state)
            await panel_manager.render(msg, render_queue(callback_data.value, items, state.queue_offset), queue_keyboard(items))
        elif callback_data.action == "load_more":
            state.queue_offset += surface_service._page_size
            items = await surface_service.queue_page(actor, state)
            await panel_manager.render(msg, render_queue(state.queue_key or "", items, state.queue_offset), queue_keyboard(items))
        elif callback_data.action == "case":
            state = navigation_service.open_panel(state, "case:detail")
            state.selected_case_id = UUID(callback_data.value)
            detail = await surface_service.case_detail(actor, state.selected_case_id)
            if not detail:
                await callback.answer("Case not found", show_alert=True)
            else:
                await panel_manager.render(msg, render_case_detail(detail), case_keyboard())
        elif callback_data.action == "claim":
            if state.selected_case_id:
                await surface_service.claim_case(actor, state.selected_case_id)
                detail = await surface_service.case_detail(actor, state.selected_case_id)
                if detail:
                    await panel_manager.render(msg, render_case_detail(detail), case_keyboard())
        elif callback_data.action == "back":
            state = navigation_service.back(state)
            if state.panel_key.startswith("queue:") and state.queue_key:
                items = await surface_service.queue_page(actor, state)
                await panel_manager.render(msg, render_queue(state.queue_key, items, state.queue_offset), queue_keyboard(items))
            else:
                presence, counts = await surface_service.hub_view(actor)
                await panel_manager.render(msg, render_hub(actor, presence, counts), hub_keyboard())
        elif callback_data.action == "refresh":
            if callback_data.value == "case" and state.selected_case_id:
                detail = await surface_service.case_detail(actor, state.selected_case_id)
                if detail:
                    await panel_manager.render(msg, render_case_detail(detail), case_keyboard())
            else:
                presence, counts = await surface_service.hub_view(actor)
                await panel_manager.render(msg, render_hub(actor, presence, counts), hub_keyboard())

        await session_store.set(callback.from_user.id, state)
        await callback.answer()

    return router
