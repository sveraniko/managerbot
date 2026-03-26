# ManagerBot V1 Release Checklist

## 1) Config / env checklist
- `MANAGERBOT_BOT_TOKEN` set and valid.
- `MANAGERBOT_CUSTOMER_BOT_TOKEN` set and valid.
- `MANAGERBOT_POSTGRES_DSN` reachable from runtime.
- `MANAGERBOT_REDIS_DSN` reachable from runtime.
- Optional handoff chats configured only if needed:
  - `MANAGERBOT_HANDOFF_PRODUCTION_CHAT_ID`
  - `MANAGERBOT_HANDOFF_WAREHOUSE_CHAT_ID`
  - `MANAGERBOT_HANDOFF_ACCOUNTANT_CHAT_ID`
- Optional AI config:
  - `MANAGERBOT_AI_ENABLED=true` only with `MANAGERBOT_AI_API_KEY` present.
  - Reader/recommender flags enabled only when AI root flag is enabled.

## 2) Operational preflight
- Startup logs confirm:
  - queue page size and notification polling interval,
  - AI runtime effective status,
  - configured handoff targets.
- Startup does **not** crash when AI or handoff config is absent.
- Notification loop starts and stops cleanly.
- Unauthorized Telegram user receives access denied and cannot enter manager flows.

## 3) Required smoke scenarios
Run these manually before release:
1. `/start` -> Workdesk renders in single panel.
2. Open queue -> open case -> Back -> Home path is deterministic.
3. Reply flow:
   - start reply,
   - edit/confirm send,
   - delivery status reflected in case detail.
4. Internal note flow:
   - create note,
   - save,
   - note appears in case detail.
5. AI flow (if enabled):
   - analyze/recommend,
   - adopt draft,
   - stale/wrong-case adoption blocked.
6. Search flow:
   - enter query,
   - open result,
   - no-result state is explicit.
7. Archive lane:
   - empty archive renders cleanly,
   - return navigation works.
8. Customer card/contact:
   - with missing contact data: no dead contact button in case panel,
   - with contact data: contact panel actions are actionable.
9. Order summary/handoff:
   - no linked order: no order action button in case panel,
   - linked order: summary panel opens,
   - missing PDF: no PDF action button,
   - missing handoff target: target action hidden.

## 4) Optional integrations (intentional)
- AI reader/recommender is optional and advisory only.
- Internal handoff chats are optional.
- Group topics bridge (MB8) is deferred and not required for V1 release.

## 5) Explicitly deferred (do not block V1)
- MB8 group topics bridge.
- ERP/1C integration.
- New system roles beyond OWNER/MANAGER.
- Autonomous AI actions.
- Admin analytics/dashboard wave.

## 6) Must-pass release assertions
- Empty states are compact and non-broken.
- Failure states are honest and recoverable.
- No dead buttons for missing order/PDF/contact/AI recommendation contexts.
- Navigation remains deterministic (Home/Back/Refresh).
- No migrations added in this repo.
