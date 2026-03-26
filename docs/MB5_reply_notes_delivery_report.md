# MB5 Reply + Notes + Delivery Tracking Report

## Implemented user-visible MB5 flows
- Added **Reply to customer** action in case detail with dedicated compose mode, preview/confirm step, and deterministic return to case detail.
- Added **Add internal note** action in case detail with dedicated compose mode and internal-only persistence path.
- Case detail now shows customer thread (with outbound delivery markers), internal notes block, and latest delivery attempt status.

## Reply compose + confirm behavior
- Reply starts from case detail and arms `ManagerSessionState` compose context (`compose_mode=reply`, case-bound context).
- Next manager text is captured as draft and shown in explicit preview (`Reply preview for Case #N`).
- Manager can confirm send, edit draft, cancel, or return back to case.
- Stale compose context (compose case != selected case) is rejected and reset safely.

## Internal notes behavior
- Note action arms `compose_mode=note`.
- Next text is stored in `ops.quote_case_internal_notes` with `visibility_scope=internal_only`.
- Notes render in a separate **Internal notes** section and never enter customer thread storage.

## Delivery channel/integration used
- Added a dedicated customer-facing delivery gateway (`TelegramCustomerDeliveryGateway`) and configured separate `MANAGERBOT_CUSTOMER_BOT_TOKEN`.
- ManagerBot surface still runs on manager bot token; outbound customer replies are sent via the dedicated customer bot client.

## Delivery persistence + rendering semantics
- On confirm send:
  1) persist outbound thread entry in `ops.quote_case_thread_entries` with `delivery_status=pending`,
  2) create delivery attempt row in `ops.reply_delivery_attempts` with `status=pending`,
  3) call customer-facing Telegram delivery,
  4) update both thread entry + attempt to `sent` or `failed` honestly.
- On successful delivery, ops state is updated with:
  - `last_manager_message_at = now()`
  - `waiting_state = waiting_customer`
- Failed deliveries remain failed and visible; no fake “sent” UI is shown.

## Retry support
- Retry action is **deferred** for MB5 to keep scope small and canonical.
- Current MB5 keeps failed attempt visibility explicit so retry can be added as a narrow MB6+ operation.

## Migration discipline confirmation
- **No repo migration was created in this PR.**
- MB5 integrates with existing backbone schema contracts (`ops.*`, `core.*`) and updates repositories/services only.

## Backbone contract gaps discovered
- Delivery target resolution required a canonical customer Telegram target. Implementation currently resolves from:
  - `core.quote_cases.customer_telegram_chat_id`, fallback to
  - `core.quote_cases.customer_actor_id -> core.actor_telegram_bindings.telegram_user_id`.
- If deployment schema differs, this must be reconciled in TradeFlow backbone contract docs/implementation.

## Deferred for MB6+
- Failed-reply retry action.
- SLA/escalation notification hardening.
- AI copilot and group topics bridge remain intentionally out of scope.
