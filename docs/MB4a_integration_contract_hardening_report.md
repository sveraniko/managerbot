# MB4a Integration Contract Hardening Report

## Scope
MB4a hardens MB4 bootstrap repositories against the canonical manager-side contract documented in `20/25/60` docs, without adding MB5 workflows.

## Contract drift found
1. **Presence write/read drift**
   - Repository used `ops.manager_presence_states.status`.
   - Canonical contract uses `presence_status` with unique `actor_id` row.

2. **Ops state naming drift**
   - Repository mixed `operational_status` write/read at table level.
   - Canonical active state column is `ops.quote_case_ops_states.status`; `operational_status` is a view/domain projection label.

3. **Assignment event drift**
   - Claim wrote non-canonical columns (`assigned_to_actor_id`, `assigned_by_actor_id`) and missed append-only sequence semantics.
   - Canonical events require `event_seq`, `event_kind`, `from_manager_actor_id`, `to_manager_actor_id`, `triggered_by_actor_id`.

4. **Queue dependency drift**
   - Queue repository depended on guessed `read.manager_case_queue_view` columns (`actor_id`, `sort_ts`, `operational_status`).
   - Canonical docs allow V1 queue derivation directly from `ops.quote_case_ops_states` + `core.quote_cases`.

5. **Thread entry field drift**
   - Case detail query used `body` instead of canonical `body_text`.

## Canonical semantics selected and applied
- Presence table uses `actor_id` + `presence_status`.
- Ops active state updates use `status='active'`, `waiting_state='waiting_manager'`, plus assignee metadata.
- Claim action appends assignment event with canonical event columns and computed `event_seq`.
- Queue reads are derived from canonical ops/core fields and MB3a-aligned deterministic ordering.
- Case detail reads ops canonical `status` and thread `body_text`.

## Code changes
- Updated SQL repositories (`presence`, `queue`, `case detail`, `claim`) to canonical columns and semantics.
- Removed hard dependency on `read.manager_case_queue_view` for MB4a queue behavior.
- Kept ManagerBot surface behavior intact (hub/queue/case read + claim/toggle).

## Integration tests added
Added DB-backed repository tests (`tests/test_sql_repositories_integration.py`) covering:
- actor lookup + access authorization,
- presence default/set/get roundtrip,
- queue summary/list filtering/order and stable display numbers,
- case detail read and claim persistence (ops state + assignment append).

Tests are schema-contract oriented: they create only canonical columns, so guessed legacy names fail fast.

## Docs synchronization
- Updated MB4 report to reflect MB4a reconciliation and queue derivation from canonical ops/core tables.

## Intentionally deferred to MB5
- reply compose/send,
- internal notes compose/send,
- delivery workflow UI,
- AI copilot.
