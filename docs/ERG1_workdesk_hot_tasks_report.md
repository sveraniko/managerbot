# ERG1 Workdesk / Hot Tasks Report

## Scope
ERG1 reworks ManagerBot home hub into a compact operational workdesk while preserving canonical queue navigation.

## Hub -> Workdesk change
- Home now renders two layers:
  1. **Hot Tasks** with actionable case slices (top-N per bucket).
  2. **Queue Summary** with existing queue counters and queue entry points.
- Header includes manager identity/presence and concise attention summary (active slice, overdue, failed delivery, new business).

## Implemented hot-task buckets
Implemented canonical V1 buckets:
1. `needs_reply_now`
2. `new_business`
3. `sla_at_risk`
4. `urgent_escalated`
5. `failed_delivery`

Buckets are derived from canonical operational tables (`ops.quote_case_ops_states`, `ops.reply_delivery_attempts`, `core.quote_cases`) with deterministic logic in `SqlQueueRepository.list_hot_task_buckets`.

## Ordering policy (deterministic)
- **Needs reply now**: SLA pressure (overdue/near) -> earliest SLA due -> priority -> recent customer touch -> case number.
- **New business**: priority -> escalation desc -> freshness (recent touch first) -> case number.
- **SLA at risk**: overdue first -> near breach -> earliest due -> priority/escalation -> case number.
- **Urgent/escalated**: priority first -> escalation desc -> SLA pressure/due -> case number.
- **Failed delivery**: latest failed attempt first -> priority -> case number.

## Workdesk item ergonomics
Each hot-task row is compact and glanceable:
- case display number,
- customer label,
- hot-task reason,
- priority/escalation,
- SLA cue,
- compact time cue.

## Open-case actions from workdesk
- Hub keyboard now includes direct per-item case buttons (`Case #N`) for hot-task entries.
- Managers can jump from workdesk directly to case detail with existing deterministic panel flow.

## Compact top-slice + “see more” UX decision
- Selected UX: **top-N + “See more”**.
- Each bucket shows at most 3 entries on home.
- Each bucket provides a `See more` action that opens the closest canonical queue (no endless home scroll).

## Queue summary preservation
- Existing queue counters and queue entry actions remain visible and unchanged in concept.
- Refresh and queue paging behavior remain intact.

## Notifications consistency check
- Workdesk buckets use same operational truth family as MB6 notifications (new visibility, SLA pressure, escalation/priority, failed delivery) to avoid contradictory priority models.

## State/navigation discipline
- No bloated new state model was introduced.
- Existing single-panel navigation/back/home flow preserved.
- Refresh updates current panel deterministically.

## Migration discipline
- **No migration was created.**
- **No local DB tables were added.**

## Deferred intentionally (ERG2+)
- Search/filter/archive controls.
- Customer card/order action block.
- Any AI-driven workdesk ranking.
