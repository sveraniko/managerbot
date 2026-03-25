# MB4 ManagerBot Bootstrap Surface Report

## Implemented surface/screens
- `hub:home` manager hub with identity, presence, queue counters, and queue entry points.
- `queue:*` queue panels for canonical buckets (`new`, `mine`, `waiting_me`, `waiting_customer`, `urgent`, `escalated`) with load-more and deterministic back/home controls.
- `case:detail` read-first case panel showing stable display numbers, operational fields, and read-only customer-visible thread preview.

## Access control
- Explicit actor resolution via `AccessService` using actor lookup by Telegram user id.
- Only `OWNER` and `MANAGER` roles are authorized.
- Unauthorized callers receive explicit denial (`Access denied...`) and no surface actions are executed.

## ManagerSessionState
- Introduced dedicated `ManagerSessionState` (separate from customer shell state concepts).
- Stores active panel key, back panel key, current queue key, selected case id, and queue pagination offset.
- Implemented Redis-backed state store (`RedisManagerSessionStore`) and in-memory store for tests.
- Back/Home behavior is deterministic from stored state instead of callback payload-only inference.

## Queue backing and read-model integration
- Added explicit repository contracts for actor/presence/queue/case operations.
- Implemented SQL repositories targeting `core`, `ops`, and `read` schemas (for MB3/MB3a-prepared operational backbone).
- MB4a hardening switched queue derivation to canonical `ops.quote_case_ops_states` + `core.quote_cases` fields, with deterministic business ordering (priority, escalation, recency, display number) while preserving stable display-number identity in UI.

## Actions supported in MB4
- Presence toggle (`online <-> away`) persisted through backend presence repository.
- Claim/take-into-work action from case detail persisted to operational state and assignment history.
- Refresh, back, home, and load-more controls implemented with single-panel update discipline.

## Deferred to MB5+
- Free-form manager reply compose/send flow.
- Internal note compose/send workflow.
- AI copilot suggestions/summaries/actions.
- Group topics bridge and collaboration sync.
- Full reassignment workflows beyond minimal claim action.

## Repo-specific integration decisions
- Since this standalone repo had docs only, MB4 includes minimum production-lean application scaffolding:
  - pydantic-settings configuration.
  - aiogram bootstrap/router surface.
  - SQLAlchemy async session wiring.
  - Redis session state wiring.
  - structlog logging and FastAPI lifecycle.
- Integration is designed DB-first against shared TradeFlow logical schemas (`core`, `ops`, `read`) with focused repository seams to keep future adapters small.
