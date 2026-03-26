from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MBCallback
from app.bot.keyboards import case_keyboard, compose_keyboard, hub_keyboard, note_preview_keyboard, queue_keyboard, reply_preview_keyboard
from app.bot.panel_manager import PanelManager
from app.services.access import AccessService
from app.services.ai_state import analysis_for_case, bind_ai_recommendation, bind_ai_result, clear_ai_snapshot, recommendation_for_case
from app.services.compose import ComposeStateService
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
    compose_service = ComposeStateService()

    async def authorize(message: Message):
        actor = await access_service.resolve_authorized_actor(message.from_user.id)
        if not actor:
            await message.answer("Access denied. ManagerBot is available only for OWNER/MANAGER.")
            return None
        return actor

    async def render_selected_case(message: Message, actor, state, prefix: str = "") -> None:
        if not state.selected_case_id:
            return
        detail = await surface_service.case_detail(actor, state.selected_case_id)
        if not detail:
            return
        ai_analysis, ai_error, ai_analysis_meta = analysis_for_case(state, detail.case_id)
        ai_recommendation, ai_recommendation_error, ai_recommendation_meta = recommendation_for_case(state, detail.case_id)
        low_conf = bool(ai_recommendation and ai_recommendation.confidence < surface_service.low_confidence_threshold)
        await panel_manager.render(
            message,
            prefix
            + render_case_detail(
                detail,
                ai_analysis=ai_analysis,
                ai_error=ai_error,
                ai_analysis_meta=ai_analysis_meta,
                ai_recommendation=ai_recommendation,
                ai_recommendation_error=ai_recommendation_error,
                ai_recommendation_meta=ai_recommendation_meta,
                low_confidence_threshold=surface_service.low_confidence_threshold,
            ),
            case_keyboard(has_ai_recommendation=ai_recommendation is not None, ai_low_confidence=low_conf),
        )

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

    @router.message(F.text)
    async def compose_input(message: Message) -> None:
        actor = await authorize(message)
        if not actor:
            return
        state = await session_store.get(message.from_user.id)
        if state.compose_mode not in {"reply", "note"}:
            return
        if compose_service.is_stale(state):
            compose_service.cancel(state)
            await session_store.set(message.from_user.id, state)
            await message.answer("Compose context expired. Re-open the case and start again.")
            return

        state.compose_draft_text = message.text.strip()
        if not state.compose_draft_text:
            await message.answer("Text is empty. Send text or cancel.")
            return

        if state.compose_mode == "reply":
            case_detail = await surface_service.case_detail(actor, state.compose_case_id)
            if not case_detail:
                compose_service.cancel(state)
                await session_store.set(message.from_user.id, state)
                await message.answer("Case context expired. Re-open the case.")
                return
            preview = f"Reply preview for Case #{case_detail.case_display_number}\n\n{state.compose_draft_text}"
            await panel_manager.render(message, preview, reply_preview_keyboard())
        else:
            note_preview = f"Internal note preview:\n\n{state.compose_draft_text}\n\nTap Save note draft to persist."
            await panel_manager.render(message, note_preview, note_preview_keyboard())
        await session_store.set(message.from_user.id, state)

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
            next_case_id = UUID(callback_data.value)
            if state.selected_case_id != next_case_id:
                clear_ai_snapshot(state)
            state.selected_case_id = next_case_id
            detail = await surface_service.case_detail(actor, state.selected_case_id)
            if not detail:
                await callback.answer("Case not found", show_alert=True)
            else:
                await render_selected_case(msg, actor, state)
        elif callback_data.action == "claim" and state.selected_case_id:
            await surface_service.claim_case(actor, state.selected_case_id)
            await render_selected_case(msg, actor, state)
        elif callback_data.action == "escalate_owner" and state.selected_case_id:
            ok = await surface_service.escalate_to_owner(actor, state.selected_case_id)
            await render_selected_case(msg, actor, state, prefix="Escalated to owner.\n\n" if ok else "Escalation failed.\n\n")
        elif callback_data.action == "reply_start":
            if not state.selected_case_id:
                await callback.answer("Open a case first", show_alert=True)
            else:
                compose_service.start_reply(state, state.selected_case_id)
                await panel_manager.render(
                    msg,
                    "Compose reply to customer.\nSend the reply text in the next message.\nYou will be asked to confirm before sending.",
                    compose_keyboard(),
                )
        elif callback_data.action == "note_start":
            if not state.selected_case_id:
                await callback.answer("Open a case first", show_alert=True)
            else:
                compose_service.start_note(state, state.selected_case_id)
                await panel_manager.render(msg, "Compose internal note.\nSend note text in the next message.\nThis note is internal-only.", compose_keyboard())
        elif callback_data.action == "reply_confirm":
            if state.compose_mode != "reply" or not state.compose_case_id or not state.compose_draft_text:
                await callback.answer("No reply draft to send.", show_alert=True)
            else:
                result_notice = await surface_service.send_reply(actor, state.compose_case_id, state.compose_draft_text)
                compose_service.cancel(state)
                await render_selected_case(msg, actor, state, prefix=f"{result_notice}\n\n")
        elif callback_data.action == "reply_edit":
            if state.compose_mode != "reply" or not state.compose_case_id:
                await callback.answer("Reply compose is not active.", show_alert=True)
            else:
                await panel_manager.render(msg, "Edit reply: send updated text in the next message.", compose_keyboard())
        elif callback_data.action == "compose_cancel":
            compose_service.cancel(state)
            if state.selected_case_id:
                await render_selected_case(msg, actor, state)
            else:
                presence, counts = await surface_service.hub_view(actor)
                await panel_manager.render(msg, render_hub(actor, presence, counts), hub_keyboard())
        elif callback_data.action == "compose_back_case":
            compose_service.back_to_case(state)
            await render_selected_case(msg, actor, state)
        elif callback_data.action == "note_save_draft":
            if state.compose_mode != "note" or not state.compose_case_id or not state.compose_draft_text:
                await callback.answer("No note draft to save.", show_alert=True)
            else:
                await surface_service.save_internal_note(actor, state.compose_case_id, state.compose_draft_text)
                compose_service.cancel(state)
                await render_selected_case(msg, actor, state)
        elif callback_data.action == "note_edit":
            if state.compose_mode != "note" or not state.compose_case_id:
                await callback.answer("Note compose is not active.", show_alert=True)
            else:
                await panel_manager.render(msg, "Edit internal note: send updated text in the next message.", compose_keyboard())
        elif callback_data.action == "ai_analyze":
            if not state.selected_case_id:
                await callback.answer("Open a case first", show_alert=True)
            else:
                detail = await surface_service.case_detail(actor, state.selected_case_id)
                if detail:
                    force_refresh = bool(state.ai_case_id == detail.case_id and (state.ai_analysis or state.ai_recommendation))
                    ai_result = await surface_service.analyze_case_reader(detail, force_refresh=force_refresh)
                    bind_ai_result(
                        state,
                        detail.case_id,
                        ai_result.analysis,
                        ai_result.error_message,
                        model=ai_result.model,
                        prompt_version=ai_result.prompt_version,
                        from_cache=ai_result.from_cache,
                    )
                    recommendation_result = await surface_service.recommend_case(detail, force_refresh=force_refresh)
                    bind_ai_recommendation(
                        state,
                        detail.case_id,
                        recommendation_result.recommendation,
                        recommendation_result.error_message,
                        model=recommendation_result.model,
                        prompt_version=recommendation_result.prompt_version,
                        from_cache=recommendation_result.from_cache,
                    )
                    await render_selected_case(msg, actor, state)
        elif callback_data.action == "ai_use_reply_draft":
            if not state.selected_case_id:
                await callback.answer("Open a case first", show_alert=True)
            else:
                recommendation, _, _ = recommendation_for_case(state, state.selected_case_id)
                if not recommendation or state.ai_case_id != state.selected_case_id:
                    await callback.answer("No valid AI recommendation for this case.", show_alert=True)
                elif not compose_service.start_reply_from_ai(state, state.selected_case_id, recommendation.draft_reply):
                    await callback.answer("AI reply draft is unavailable for this case.", show_alert=True)
                else:
                    detail = await surface_service.case_detail(actor, state.selected_case_id)
                    if detail:
                        await panel_manager.render(msg, f"AI reply draft loaded for Case #{detail.case_display_number}.\n\n{state.compose_draft_text}", reply_preview_keyboard())
        elif callback_data.action == "ai_use_note_draft":
            if not state.selected_case_id:
                await callback.answer("Open a case first", show_alert=True)
            else:
                recommendation, _, _ = recommendation_for_case(state, state.selected_case_id)
                if not recommendation or state.ai_case_id != state.selected_case_id:
                    await callback.answer("No valid AI recommendation for this case.", show_alert=True)
                elif not compose_service.start_note_from_ai(state, state.selected_case_id, recommendation.draft_internal_note):
                    await callback.answer("AI note draft is unavailable for this case.", show_alert=True)
                else:
                    await panel_manager.render(
                        msg,
                        "AI internal note draft loaded:\n\n" f"{state.compose_draft_text}\n\nTap Save note draft to persist or Edit to modify.",
                        note_preview_keyboard(),
                    )
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
                await render_selected_case(msg, actor, state)
            else:
                presence, counts = await surface_service.hub_view(actor)
                await panel_manager.render(msg, render_hub(actor, presence, counts), hub_keyboard())

        await session_store.set(callback.from_user.id, state)
        await callback.answer()

    return router
