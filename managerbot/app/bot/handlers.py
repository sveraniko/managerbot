from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MBCallback
from app.bot.keyboards import (
    case_keyboard,
    contact_actions_keyboard,
    compose_keyboard,
    filters_keyboard,
    hub_keyboard,
    order_actions_keyboard,
    note_preview_keyboard,
    queue_keyboard,
    reply_preview_keyboard,
    search_input_keyboard,
    search_results_keyboard,
)
import structlog

from app.models import CaseDetail, CustomerCard
from app.bot.panel_manager import PanelManager
from app.models import QueueFilters
from app.services.access import AccessService
from app.services.ai_state import analysis_for_case, bind_ai_recommendation, bind_ai_result, clear_ai_snapshot, recommendation_for_case
from app.services.ai_recommender import recommendation_supports_draft_adoption
from app.services.compose import ComposeStateService
from app.services.manager_surface import ManagerSurfaceService
from app.services.navigation import NavigationService
from app.services.order_actions import HandoffTargets, build_order_compact_summary, has_order, has_order_pdf, target_label
from app.services.rendering import (
    render_case_detail,
    render_contact_actions_panel,
    render_filters,
    render_hub,
    render_order_summary_panel,
    render_queue,
    render_reply_preview,
    render_search_results,
)
from app.state.manager_session import ManagerSessionStore

logger = structlog.get_logger(__name__)


def build_router(
    access_service: AccessService,
    session_store: ManagerSessionStore,
    surface_service: ManagerSurfaceService,
    navigation_service: NavigationService,
    panel_manager: PanelManager,
    handoff_targets: HandoffTargets,
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
        can_use_ai_draft = bool(ai_recommendation and recommendation_supports_draft_adoption(ai_recommendation))
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
            case_keyboard(
                has_ai_recommendation=can_use_ai_draft,
                ai_low_confidence=low_conf,
                has_order_actions=has_order(detail),
                has_contact_actions=_has_contact_actions(detail),
            ),
        )

    async def require_selected_case_detail(
        callback: CallbackQuery, actor, state, *, action_label: str = "action"
    ) -> CaseDetail | None:
        if not state.selected_case_id:
            await callback.answer("Open a case first.", show_alert=True)
            return None
        detail = await surface_service.case_detail(actor, state.selected_case_id)
        if detail:
            return detail
        compose_service.cancel(state)
        state.selected_case_id = None
        state.panel_key = "hub:home"
        state.back_panel_key = None
        state.search_mode = False
        state.search_query = None
        await callback.answer(f"Case is no longer available for {action_label}.", show_alert=True)
        presence, counts, buckets = await surface_service.hub_view(actor)
        await panel_manager.render(callback.message, render_hub(actor, presence, counts, buckets), hub_keyboard(buckets))
        return None

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        actor = await authorize(message)
        if not actor:
            return
        state = await session_store.get(message.from_user.id)
        state.panel_key = "hub:home"
        state.queue_offset = 0
        await session_store.set(message.from_user.id, state)
        from app.models import PresenceStatus
        await surface_service.set_presence(actor, PresenceStatus.OFFLINE)
        presence, counts, buckets = await surface_service.hub_view(actor)
        await panel_manager.render(message, render_hub(actor, presence, counts, buckets), hub_keyboard(buckets))

    @router.message(F.text)
    async def compose_input(message: Message) -> None:
        actor = await authorize(message)
        if not actor:
            return
        state = await session_store.get(message.from_user.id)
        if state.search_mode:
            query = message.text.strip()
            if not query:
                await panel_manager.render(message, "Search query is empty. Enter case #, order #, or customer.", search_input_keyboard())
                await session_store.set(message.from_user.id, state)
                return
            state.search_query = query
            state.search_mode = False
            state = navigation_service.open_panel(state, "search:results")
            results = await surface_service.search_cases(actor, query, state)
            await panel_manager.render(
                message,
                render_search_results(query, results, _filters_from_state(state)),
                search_results_keyboard(results),
            )
            await session_store.set(message.from_user.id, state)
            return
        if state.compose_mode not in {"reply", "note"}:
            return
        if compose_service.is_stale(state):
            compose_service.cancel(state)
            await session_store.set(message.from_user.id, state)
            await panel_manager.render(message, "Compose context expired. Re-open case and start again.", compose_keyboard())
            return

        state.compose_draft_text = message.text.strip()
        if not state.compose_draft_text:
            await panel_manager.render(message, "Text is empty. Send text or cancel.", compose_keyboard())
            return

        if state.compose_mode == "reply":
            case_detail = await surface_service.case_detail(actor, state.compose_case_id)
            if not case_detail:
                compose_service.cancel(state)
                await session_store.set(message.from_user.id, state)
                await message.answer("Case context expired. Re-open the case.")
                return
            preview = render_reply_preview(
                case_detail,
                state.compose_draft_text,
                guardrail_issues=compose_service.customer_visible_guardrail_issues(state.compose_draft_text),
            )
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
            presence, counts, buckets = await surface_service.hub_view(actor)
            await panel_manager.render(msg, render_hub(actor, presence, counts, buckets), hub_keyboard(buckets))
        elif callback_data.action == "presence":
            await surface_service.toggle_presence(actor)
            presence, counts, buckets = await surface_service.hub_view(actor)
            await panel_manager.render(msg, render_hub(actor, presence, counts, buckets), hub_keyboard(buckets))
        elif callback_data.action == "queue":
            state = navigation_service.open_panel(state, f"queue:{callback_data.value}")
            state.queue_key = callback_data.value
            state.queue_offset = 0
            items = await surface_service.queue_page(actor, state)
            has_more = len(items) >= surface_service._page_size
            await panel_manager.render(
                msg,
                render_queue(callback_data.value, items, state.queue_offset, _filters_from_state(state)),
                queue_keyboard(items, has_more=has_more),
            )
        elif callback_data.action == "load_more":
            state.queue_offset += surface_service._page_size
            items = await surface_service.queue_page(actor, state)
            has_more = len(items) >= surface_service._page_size
            await panel_manager.render(
                msg,
                render_queue(state.queue_key or "", items, state.queue_offset, _filters_from_state(state)),
                queue_keyboard(items, has_more=has_more),
            )
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
        elif callback_data.action == "set_priority" and state.selected_case_id:
            ok = await surface_service.update_case_priority(actor, state.selected_case_id, callback_data.value)
            await render_selected_case(msg, actor, state, prefix=f"Priority updated to {callback_data.value}.\n\n" if ok else "Priority update failed.\n\n")
        elif callback_data.action == "search_start":
            state.search_mode = True
            state = navigation_service.open_panel(state, "search:input")
            await panel_manager.render(
                msg,
                "Search mode is active.\nSend query text (case #, order #, customer).\nExample: Q-101, O-9001, Acme.",
                search_input_keyboard(),
            )
        elif callback_data.action == "search_cancel":
            state.search_mode = False
            state.search_query = None
            state = navigation_service.back(state)
            if state.panel_key.startswith("queue:") and state.queue_key:
                items = await surface_service.queue_page(actor, state)
                await panel_manager.render(msg, render_queue(state.queue_key, items, state.queue_offset, _filters_from_state(state)), queue_keyboard(items))
            else:
                presence, counts, buckets = await surface_service.hub_view(actor)
                await panel_manager.render(msg, render_hub(actor, presence, counts, buckets), hub_keyboard(buckets))
        elif callback_data.action == "filters_open":
            state = navigation_service.open_panel(state, "filters:panel")
            await panel_manager.render(msg, f"Active filters\n{render_filters(_filters_from_state(state))}", filters_keyboard(_filters_from_state(state)))
        elif callback_data.action == "filter_cycle":
            _cycle_filter(state, callback_data.value)
            await panel_manager.render(msg, f"Active filters\n{render_filters(_filters_from_state(state))}", filters_keyboard(_filters_from_state(state)))
        elif callback_data.action == "filters_reset":
            _reset_filters(state)
            await panel_manager.render(msg, f"Filters reset.\n{render_filters(_filters_from_state(state))}", filters_keyboard(_filters_from_state(state)))
        elif callback_data.action == "reply_start":
            if not state.selected_case_id:
                await callback.answer("Open a case first", show_alert=True)
            else:
                compose_service.start_reply(state, state.selected_case_id)
                await panel_manager.render(
                    msg,
                    "Compose customer-visible reply.\nKeep wording commercially clear (for example: Min order, Increment, In box).\nSend text in the next message, then confirm before sending.",
                    compose_keyboard(),
                )
        elif callback_data.action == "note_start":
            if not state.selected_case_id:
                await callback.answer("Open a case first", show_alert=True)
            else:
                compose_service.start_note(state, state.selected_case_id)
                await panel_manager.render(msg, "Compose internal note.\nSend note text in the next message.\nThis note is internal-only.", compose_keyboard())
        elif callback_data.action == "contact_panel":
            detail = await require_selected_case_detail(callback, actor, state, action_label="contact actions")
            if detail:
                if not _has_contact_actions(detail):
                    await callback.answer("No direct-contact data for this case.", show_alert=True)
                else:
                    state = navigation_service.open_panel(state, "case:contact")
                    card = detail.customer_card or CustomerCard(label=detail.customer_label)
                    await panel_manager.render(msg, render_contact_actions_panel(detail), contact_actions_keyboard(card))
        elif callback_data.action == "contact_copy":
            if not state.selected_case_id:
                await callback.answer("Open a case first", show_alert=True)
            else:
                detail = await surface_service.case_detail(actor, state.selected_case_id)
                if not detail:
                    await callback.answer("Case not found", show_alert=True)
                else:
                    card = detail.customer_card or CustomerCard(label=detail.customer_label)
                    value = {
                        "username": card.telegram_username or "Unavailable",
                        "chat_id": str(card.telegram_chat_id) if card.telegram_chat_id is not None else "Unavailable",
                        "user_id": str(card.telegram_user_id) if card.telegram_user_id is not None else "Unavailable",
                        "phone": card.phone_number or "Unavailable",
                    }.get(callback_data.value, "Unavailable")
                    await callback.answer(f"Copy manually: {value}", show_alert=True)
        elif callback_data.action == "log_contact_outcome":
            if not state.selected_case_id:
                await callback.answer("Open a case first", show_alert=True)
            else:
                compose_service.start_note_template(
                    state,
                    state.selected_case_id,
                    "Direct contact outcome:\n- Channel:\n- Summary:\n- Next step:",
                )
                await panel_manager.render(
                    msg,
                    "Contact note template loaded.\nEdit if needed, then save note draft.",
                    note_preview_keyboard(),
                )
        elif callback_data.action == "contact_back":
            state = navigation_service.back(state)
            await render_selected_case(msg, actor, state)
        elif callback_data.action == "order_summary_open":
            detail = await require_selected_case_detail(callback, actor, state, action_label="order summary")
            if detail:
                if not has_order(detail):
                    await callback.answer("No linked order for this case.", show_alert=True)
                else:
                    state = navigation_service.open_panel(state, "case:order")
                    targets = _configured_handoff_targets(handoff_targets)
                    await panel_manager.render(
                        msg,
                        render_order_summary_panel(detail, configured_targets=targets),
                        order_actions_keyboard(has_pdf=has_order_pdf(detail), configured_targets=targets),
                    )
        elif callback_data.action == "order_send_summary_here":
            detail = await require_selected_case_detail(callback, actor, state, action_label="order summary")
            if detail:
                if not has_order(detail):
                    await callback.answer("No linked order for this case.", show_alert=True)
                else:
                    targets = _configured_handoff_targets(handoff_targets)
                    await panel_manager.render(
                        msg,
                        "Compact order summary:\n\n" + build_order_compact_summary(detail) + "\n\n" + render_order_summary_panel(detail, configured_targets=targets),
                        order_actions_keyboard(has_pdf=has_order_pdf(detail), configured_targets=targets),
                    )
        elif callback_data.action == "order_send_pdf_here":
            detail = await require_selected_case_detail(callback, actor, state, action_label="order document")
            if detail:
                if not has_order(detail):
                    await callback.answer("No linked order for this case.", show_alert=True)
                elif not detail.linked_order_pdf_url:
                    await callback.answer("Order PDF/document is not available.", show_alert=True)
                else:
                    label = detail.linked_order_document_label or "Order PDF"
                    targets = _configured_handoff_targets(handoff_targets)
                    await panel_manager.render(
                        msg,
                        f"Document reference:\n{label}: {detail.linked_order_pdf_url}\n\n" + render_order_summary_panel(detail, configured_targets=targets),
                        order_actions_keyboard(has_pdf=has_order_pdf(detail), configured_targets=targets),
                    )
        elif callback_data.action == "order_handoff":
            detail = await require_selected_case_detail(callback, actor, state, action_label="order handoff")
            if detail:
                if not has_order(detail):
                    await callback.answer("No linked order for this case.", show_alert=True)
                else:
                    target_key = callback_data.value
                    target_chat_id = handoff_targets.chat_id_for(target_key)
                    label = target_label(target_key)
                    if not target_chat_id:
                        await callback.answer(f"{label} target is not configured.", show_alert=True)
                    else:
                        text = build_order_compact_summary(detail, handoff_target_label=label)
                        try:
                            await msg.bot.send_message(chat_id=target_chat_id, text=text)
                        except Exception as exc:  # pragma: no cover - network/telegram errors
                            logger.warning(
                                "order_handoff_send_failed",
                                case_id=str(detail.case_id),
                                order_display_number=detail.linked_order_display_number,
                                target=target_key,
                                target_chat_id=target_chat_id,
                                error=str(exc),
                            )
                            await panel_manager.render(
                                msg,
                                f"Handoff failed for {label}. Check target chat and bot access.\n\n"
                                + render_order_summary_panel(detail, configured_targets=_configured_handoff_targets(handoff_targets)),
                                order_actions_keyboard(
                                    has_pdf=has_order_pdf(detail), configured_targets=_configured_handoff_targets(handoff_targets)
                                ),
                            )
                        else:
                            await surface_service.save_internal_note(
                                actor,
                                state.selected_case_id,
                                f"Order handoff sent to {label} (chat {target_chat_id}) for Order #{detail.linked_order_display_number}.",
                            )
                            await panel_manager.render(
                                msg,
                                f"Handoff sent to {label}.\n\n" + render_order_summary_panel(detail, configured_targets=_configured_handoff_targets(handoff_targets)),
                                order_actions_keyboard(has_pdf=has_order_pdf(detail), configured_targets=_configured_handoff_targets(handoff_targets)),
                            )
        elif callback_data.action == "order_back":
            state = navigation_service.back(state)
            await render_selected_case(msg, actor, state)
        elif callback_data.action == "reply_confirm":
            if state.compose_mode != "reply" or not state.compose_case_id or not state.compose_draft_text:
                await callback.answer("No reply draft to send.", show_alert=True)
            elif compose_service.is_stale(state):
                compose_service.cancel(state)
                await callback.answer("Reply draft is stale. Re-open case and compose again.", show_alert=True)
            else:
                guardrail_issues = compose_service.customer_visible_guardrail_issues(state.compose_draft_text)
                if guardrail_issues:
                    detail = await surface_service.case_detail(actor, state.compose_case_id)
                    if detail:
                        await panel_manager.render(
                            msg,
                            render_reply_preview(
                                detail,
                                state.compose_draft_text,
                                guardrail_issues=guardrail_issues,
                            ),
                            reply_preview_keyboard(),
                        )
                    await callback.answer("Update wording to commercial terms before sending.", show_alert=True)
                    await session_store.set(callback.from_user.id, state)
                    return
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
                presence, counts, buckets = await surface_service.hub_view(actor)
                await panel_manager.render(msg, render_hub(actor, presence, counts, buckets), hub_keyboard(buckets))
        elif callback_data.action == "compose_back_case":
            compose_service.back_to_case(state)
            await render_selected_case(msg, actor, state)
        elif callback_data.action == "note_save_draft":
            if state.compose_mode != "note" or not state.compose_case_id or not state.compose_draft_text:
                await callback.answer("No note draft to save.", show_alert=True)
            elif compose_service.is_stale(state):
                compose_service.cancel(state)
                await callback.answer("Note draft is stale. Re-open case and create a new note.", show_alert=True)
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
                elif not recommendation_supports_draft_adoption(recommendation):
                    await callback.answer("AI handoff state requires manual review before adopting draft.", show_alert=True)
                elif not compose_service.start_reply_from_ai(state, state.selected_case_id, recommendation.draft_reply):
                    await callback.answer("AI reply draft is unavailable for this case.", show_alert=True)
                else:
                    detail = await surface_service.case_detail(actor, state.selected_case_id)
                    if detail:
                        await panel_manager.render(
                            msg,
                            render_reply_preview(
                                detail,
                                state.compose_draft_text,
                                guardrail_issues=compose_service.customer_visible_guardrail_issues(state.compose_draft_text),
                            ),
                            reply_preview_keyboard(),
                        )
        elif callback_data.action == "ai_use_note_draft":
            if not state.selected_case_id:
                await callback.answer("Open a case first", show_alert=True)
            else:
                recommendation, _, _ = recommendation_for_case(state, state.selected_case_id)
                if not recommendation or state.ai_case_id != state.selected_case_id:
                    await callback.answer("No valid AI recommendation for this case.", show_alert=True)
                elif not recommendation_supports_draft_adoption(recommendation):
                    await callback.answer("AI handoff state requires manual review before adopting draft.", show_alert=True)
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
                has_more = len(items) >= surface_service._page_size
                await panel_manager.render(
                    msg,
                    render_queue(state.queue_key, items, state.queue_offset, _filters_from_state(state)),
                    queue_keyboard(items, has_more=has_more),
                )
            elif state.panel_key.startswith("search:") and state.search_query:
                results = await surface_service.search_cases(actor, state.search_query, state)
                await panel_manager.render(msg, render_search_results(state.search_query, results, _filters_from_state(state)), search_results_keyboard(results))
            else:
                presence, counts, buckets = await surface_service.hub_view(actor)
                await panel_manager.render(msg, render_hub(actor, presence, counts, buckets), hub_keyboard(buckets))
        elif callback_data.action == "refresh":
            if callback_data.value == "case" and state.selected_case_id:
                await render_selected_case(msg, actor, state)
            else:
                presence, counts, buckets = await surface_service.hub_view(actor)
                await panel_manager.render(msg, render_hub(actor, presence, counts, buckets), hub_keyboard(buckets))

        await session_store.set(callback.from_user.id, state)
        await callback.answer()

    return router


def _filters_from_state(state) -> QueueFilters:
    return QueueFilters(
        assignment_scope=state.filter_assignment_scope,
        waiting_scope=state.filter_waiting_scope,
        priority_scope=state.filter_priority_scope,
        sla_scope=state.filter_sla_scope,
        escalation_scope=state.filter_escalation_scope,
        lifecycle_scope=state.filter_lifecycle_scope,
    )


def _cycle_filter(state, kind: str) -> None:
    options = {
        "lifecycle": ["active", "archive", "all"],
        "assignment": ["any", "mine", "unassigned"],
        "waiting": ["any", "waiting_manager", "waiting_customer"],
        "priority": ["any", "high_or_urgent", "urgent_or_vip", "vip"],
        "escalation": ["any", "escalated"],
        "sla": ["any", "at_risk"],
    }
    attr = {
        "lifecycle": "filter_lifecycle_scope",
        "assignment": "filter_assignment_scope",
        "waiting": "filter_waiting_scope",
        "priority": "filter_priority_scope",
        "escalation": "filter_escalation_scope",
        "sla": "filter_sla_scope",
    }.get(kind)
    if not attr:
        return
    seq = options[kind]
    current = getattr(state, attr)
    nxt = seq[(seq.index(current) + 1) % len(seq)] if current in seq else seq[0]
    setattr(state, attr, nxt)


def _reset_filters(state) -> None:
    state.filter_assignment_scope = "any"
    state.filter_waiting_scope = "any"
    state.filter_priority_scope = "any"
    state.filter_sla_scope = "any"
    state.filter_escalation_scope = "any"
    state.filter_lifecycle_scope = "active"


def _configured_handoff_targets(targets: HandoffTargets) -> dict[str, bool]:
    return {
        "production": targets.production_chat_id is not None,
        "warehouse": targets.warehouse_chat_id is not None,
        "accountant": targets.accountant_chat_id is not None,
    }


def _has_contact_actions(detail: CaseDetail) -> bool:
    card = detail.customer_card or CustomerCard(label=detail.customer_label)
    return any(
        value
        for value in (
            card.telegram_username,
            card.telegram_chat_id,
            card.telegram_user_id,
            card.phone_number,
        )
    )
