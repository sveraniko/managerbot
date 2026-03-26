# ERG5 Release Hardening V1 Report

## Scope delivered
ERG5 focused on release hardening of the existing ManagerBot V1 surface: empty/failure states, action gating, navigation determinism, startup/config sanity, and noise reduction. No new feature wave was introduced.

## What was hardened

### 1) Empty-state hardening
- Workdesk now explicitly shows when there are no hot tasks.
- Queue empty state now includes an operator guidance line instead of dead-end silence.
- Case detail now renders explicit `- none` when customer thread is empty.
- Contact panel explicitly indicates when direct channel data is unavailable.
- Order summary renderer now has a safe no-linked-order fallback text.

### 2) Failure-state hardening
- Added selected-case guard handling for callback actions so missing/expired case context is surfaced clearly and user is recovered to home panel.
- Stale compose confirmation paths (reply/note) are now blocked with explicit stale warnings and compose reset.
- Internal handoff send now catches delivery exceptions and reports failure in-panel with recovery guidance.
- Empty search text now handled explicitly in-panel.

### 3) Action gating / dead-button audit
- Workdesk no longer shows per-bucket `Open ...` buttons for empty buckets.
- Queue `Load more` now hidden when current page does not indicate a next page.
- Case keyboard now hides `Contact actions` when no usable contact channel data exists.
- Existing ERG3/ERG4 gating is preserved: order panel hidden without linked order, PDF action hidden without document reference, handoff targets hidden when not configured, AI adoption hidden without recommendation.

### 4) Navigation / panel cleanup
- `NavigationService.back()` no longer ping-pongs between two screens; it now resolves to deterministic previous panel and clears back-pointer.
- Contact/order “Back to case” now uses navigation service instead of direct panel-key mutation.
- Home reset now clears full AI snapshot state (analysis/recommendation + metadata) to avoid stale carry-over.

### 5) Message-noise cleanup
- Replaced extra `answer(...)` chat messages for:
  - order compact summary action,
  - order PDF/document reference action,
  with single-panel render updates.
- Stale compose and empty compose text feedback now updates panel instead of adding extra chat clutter.

### 6) Permission and action safety
- Existing OWNER/MANAGER gate remains strict.
- Callback-time case guards now reduce stale-callback side effects by validating selected case before sensitive actions.
- Cross-case stale compose confirmation now blocked explicitly.

### 7) Config/startup sanity hardening
- Added bounded settings constraints for key numeric operational config values.
- Startup log now reports effective runtime toggles (AI enabled/runtime enabled, handoff targets present).
- Explicit startup warnings added for:
  - AI enabled without API key,
  - AI subfeatures enabled while root AI flag is disabled.
- Missing handoff configuration remains non-fatal and now logged as expected optional state.

## Checklist document added
- Added `docs/95_managerbot_v1_release_checklist.md` with practical config, preflight, smoke scenarios, optional integrations, and explicit V1 deferrals.

## Migration discipline confirmation
- No migration created.
- No schema/table changes introduced.

## Intentionally deferred after V1
- MB8 group topics bridge.
- ERP/1C integration.
- New role model beyond OWNER/MANAGER.
- Autonomous AI actions.
- New analytics/admin console wave.
