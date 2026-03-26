# ERG1 Workdesk / Hot Tasks Report

## Scope delivered
ERG1 turns the previous counter-only hub into an operational **Workdesk** with two layers:
1. **Hot Tasks** (actionable, case-level entries)
2. **Queue Summary** (canonical counters + queue entry points)

No migration was added. Work is fully inside standalone ManagerBot repo.

## Hub -> Workdesk changes
- Hub rendering now includes a concise operator header, hot-task block with compact case items, and queue summary.
- Hub keyboard now includes direct **open case** actions for hot-task items and per-bucket **Open ...** transitions.
- Existing queue navigation remains intact (`new`, `mine`, `waiting_me`, `waiting_customer`, `urgent`, `escalated`) plus refresh/presence.

## Implemented hot-task buckets (V1)
Implemented canonical buckets:
1. `needs_reply_now`
2. `new_business`
3. `sla_at_risk`
4. `urgent_escalated`
5. `failed_delivery`

Each bucket is derived from operational DB truth (`ops.quote_case_ops_states`, `core.quote_cases`, latest failed delivery attempt) and returns real case items with direct case-open callback actions.

## Bucket ordering policy (deterministic)
`SqlQueueRepository.hot_task_buckets(...)` explicitly documents and applies deterministic ordering:
- **Needs reply now**: priority rank -> SLA pressure -> escalation -> freshest customer touch -> case number
- **New business**: priority rank -> escalation -> freshness (`ops.updated_at`) -> case number
- **SLA at risk**: overdue first, then near breach -> priority -> escalation -> earliest due -> case number
- **Urgent/escalated**: priority rank -> escalation -> SLA pressure -> freshest touch -> case number
- **Failed delivery**: most recent failed delivery first -> priority -> escalation -> case number

AI does not influence bucket membership or ordering.

## Case opening from workdesk
- Every rendered hot-task item has a direct `case` callback action and opens case detail deterministically.
- Bucket-level “Open ...” actions are semantically strict:
  - `Needs reply now` -> `waiting_me`
  - `New business` -> `new`
  - `SLA at risk` -> `sla_risk` (bucket-specific lane)
  - `Urgent / VIP / escalated` -> `urgent_escalated` (bucket-specific lane)
  - `Failed delivery` -> `failed_delivery` (bucket-specific lane)

## Compactness / see-more UX decision
Chosen pattern:
- Show top-N per bucket (configurable via `workdesk_bucket_size`, default 3)
- Provide per-bucket **Open <bucket title>** action to jump to queue lane

This keeps home compact and avoids long scrolling.

## Notification consistency
Hot-task buckets align with existing MB6 notification semantics:
- `new_inbound` -> `needs_reply_now`
- `case_visible` -> `new_business`
- `delivery_failed` -> `failed_delivery`
- escalation/priority alerts -> `urgent_escalated`
- SLA warning semantics -> `sla_at_risk`

## Session/navigation discipline
No heavy UI state was introduced. Existing single-panel flow remains:
- Home/Back/Refresh deterministic
- Queue/detail flows unchanged
- Compose and AI case-bound state safety unaffected

## Migration discipline confirmation
- **No migration created**.
- **No new local DB tables created**.
- Data reads leverage existing canonical tables/views only.

## Deferred intentionally (ERG2+)
- Search/filter ergonomics
- Customer card block
- Order action block
- Archive/priority controls beyond existing baseline
- Any AI-led ranking or autonomous triage
