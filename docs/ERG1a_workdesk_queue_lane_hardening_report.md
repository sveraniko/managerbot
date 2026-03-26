# ERG1a Workdesk Queue-Lane Hardening Report

## Scope
ERG1a is a narrow stabilization pass after ERG1.
It fixes semantic mismatches where hot-task bucket-level `Open ...` actions previously routed to approximate canonical queues (`waiting_me` / `urgent`) instead of truthful bucket lanes.

## Mismatch fixed
Before ERG1a:
- `SLA at risk` could open `waiting_me`.
- `Failed delivery` could open `waiting_me`.
- `Urgent / VIP / escalated` could open `urgent`.

After ERG1a:
- `SLA at risk` opens `sla_risk`.
- `Failed delivery` opens `failed_delivery`.
- `Urgent / VIP / escalated` opens `urgent_escalated`.

This makes each button label honest about the resulting list.

## List keys / views added or adjusted
Read-side queue/list support was expanded in `SqlQueueRepository.list_queue(...)` for:
- `sla_risk`
- `failed_delivery`
- `urgent_escalated`

Canonical queues (`new`, `mine`, `waiting_me`, `waiting_customer`, `urgent`, `escalated`) remain intact.

## Ordering behavior
Deterministic ordering for new bucket-specific lanes:
- `sla_risk`: overdue first, then near-breach, then priority, escalation, earliest due time, case number.
- `failed_delivery`: latest failed delivery timestamp first, then priority, escalation, case number.
- `urgent_escalated`: priority, escalation, SLA pressure, freshest customer activity, case number.

Hot-task bucket ordering and list ordering remain aligned.

## Navigation integrity
Navigation remains compact and unchanged in shape:
- Workdesk -> bucket `Open ...` -> queue list
- Queue list -> case detail
- Back/Home/Refresh flows unchanged and deterministic

## Migration / scope guardrail confirmation
- No migration created.
- No schema changes.
- ERG2 features remain out of scope (no search, filters, archive controls, priority UI extensions, customer card, or order action block).
