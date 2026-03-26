# ERG2 Search / Filters / Archive / Priority Report

## Scope delivered
ERG2 introduces manager-side retrieval and control ergonomics in standalone ManagerBot:
- explicit search mode entry from hub/queues;
- compact search results with direct case open;
- practical queue/search filters with one-tap reset;
- archive/history lane separated from active workspace by default;
- manual priority controls (normal/high/urgent/vip) in case detail;
- priority-aware ordering/cues in queue/workdesk/search rendering.

No migration was added.

## Search entry and execution
- Search starts only through explicit callbacks (`Search case/order/customer` / `Search`) and arms `ManagerSessionState.search_mode`.
- Free text is interpreted as search only while `search_mode=True`; reply/note compose flows remain isolated.
- Search query is executed through repository-level bounded search (`limit=10`) and returns compact result rows with stable identifiers and open-case actions.

## Searchable fields in ERG2
Implemented targeted search by:
- case display number (`Q-101`, `101`, `quote 101`);
- linked order display number (`O-9002`, `9002`, `order 9002`);
- customer label prefix/contains match;
- customer actor/chat identifiers when available in canonical quote-case fields.

Backbone limitation observed:
- Telegram username/handle search is not guaranteed because the current repo contracts do not expose a canonical customer username field in read/query paths. ERG2 therefore uses available identity columns only.

## Filters behavior
Filters are session-scoped and visible in queue/search rendering:
- lifecycle: `active | archive | all`
- assignment: `any | mine | unassigned`
- waiting: `any | waiting_manager | waiting_customer`
- priority: `any | high_or_urgent | urgent_or_vip | vip`
- escalation: `any | escalated`
- SLA: `any | at_risk`

A dedicated filter panel cycles each dimension and supports one-tap reset.

## Archive/history separation
- Active workspace stays default (`lifecycle=active`).
- New explicit `archive` queue lane exists and can be opened intentionally from hub.
- Archive items are marked `[ARCHIVE]` in list/search rendering and remain openable/searchable.
- Archive is historical view only (not deletion).

## Manual priority control and surfacing
- Case detail now exposes direct priority actions: normal/high/urgent/vip.
- Priority updates persist through canonical ops state update (no local shadow table).
- Priority is visible in case detail, queue rows, hot-task cues, and search result cues.

## Ordering integration
- Priority ordering was introduced for `vip`, but ERG2a later hardened several inconsistent paths (notably urgent/escalated lane membership and helper drift in some ranking branches).
- Queue/search sorting remains deterministic with explicit tuple ordering; see ERG2a report for final canonical VIP semantics.

## State/navigation discipline
- Added minimal session fields for search mode/query and filter values.
- Home/back/navigation remains deterministic.
- Search/filter context does not overwrite compose draft flows for reply/note.

## Migration discipline confirmation
- No Alembic migration created.
- No local persistence table created for filters/archive/search state.

## Deferred intentionally (ERG3+)
- Customer card block and direct-contact ergonomics (ERG3).
- Order action block / share-handoff actions (ERG4).
