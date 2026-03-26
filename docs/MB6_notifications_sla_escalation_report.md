# MB6 Notifications, SLA, Escalation, and Queue Hardening Report

## Scope implemented
MB6 adds manager-side operational hardening in the standalone ManagerBot repository only:
- internal manager notifications for new case visibility, inbound customer messages, assigned-to-me events, and failed outbound delivery;
- Redis TTL dedupe for notification events (no schema changes);
- SLA state classification (`healthy`, `near_breach`, `overdue`) and visibility in hub/queue/case detail;
- deterministic queue ordering with SLA pressure added to existing priority/escalation ordering;
- escalate-to-owner action from case detail;
- busy/away/offline fallback policy in notification targeting;
- compose-state hardening for back-to-case behavior;
- startup/shutdown integration for a lightweight notification worker loop.

## Notifications added
Notification events are polled from canonical operational tables:
- `case_visible` from `ops.quote_case_ops_states.status='new'`
- `new_inbound` from inbound entries in `ops.quote_case_thread_entries`
- `assigned_to_me` from assignment events
- `delivery_failed` from failed rows in `ops.reply_delivery_attempts`

Manager-facing text is compact and case-number anchored.

## Dedupe policy
No local DB tables were introduced.
Dedupe uses Redis keys:
- key prefix: `managerbot:notify:`
- key: deterministic per event (`<kind>:<source-id-or-timestamp>`)
- TTL: configurable (`MANAGERBOT_NOTIFICATION_DEDUPE_TTL_SECONDS`, default 3600)

Effect: the same event is not re-notified on each poll/refresh.

## SLA policy / heuristics
Read-side SLA policy:
- if `sla_due_at` is null -> `healthy`
- if `sla_due_at <= now` -> `overdue`
- if `sla_due_at <= now + 30min` -> `near_breach`
- else -> `healthy`

Rendering:
- hub counters include `SLA near` and `SLA overdue`
- queue rows include `sla:<state>`
- case detail includes `SLA: <state>`

## Queue hardening policy
Ordering remains deterministic and business-driven:
1. priority rank (`urgent`, `high`, then others)
2. SLA pressure rank (`overdue`, `near_breach`, healthy)
3. escalation level descending
4. earliest SLA due / customer touch timestamp
5. stable case display number ascending

## Escalation behavior
Added `Escalate to owner` action in case detail.
Behavior:
- finds OWNER actor from canonical actor-role contract;
- updates ops state to owner assignment (`waiting_owner`, escalation level set, active status);
- appends canonical assignment event `escalated_to_owner`;
- escalation appears in queue/detail naturally through ops fields.

## Busy/offline fallback policy
Notification targeting policy:
- new unassigned case -> OWNER + online managers
- new inbound message -> assigned manager; also OWNER when assigned manager is busy/away/offline or absent
- assigned-to-me -> only assigned manager
- delivery failed -> assigned manager; also OWNER when assignee is offline or missing

## Failed delivery hardening
Delivery failures from MB5 remain honest (`failed`, never marked sent) and are now actively surfaced via manager notifications, not only case-detail rendering.

## Compose-state hardening
`Back to case` now clears compose context (`compose_mode`, `compose_case_id`, `compose_draft_text`) to prevent unsafe stale-send behavior after leaving compose UI.

## Startup / runtime worker integration
App startup now launches a lightweight async notification loop task.
Shutdown sets a stop event and waits for clean task termination.
No Celery/external worker framework was introduced.

## Migration discipline confirmation
- No Alembic migration created.
- No local shadow tables created.
- MB6 remains read/write against existing `core.*` / `ops.*` contracts.

## Backbone contract notes
MB6 assumes canonical ops fields are present (including `sla_due_at` on ops state). If not present in a deployment backbone, reconciliation must happen in the backbone contract, not via local ManagerBot migrations.

## Deferred beyond MB6
- AI copilot work remains for MB7.
- Group topics bridge remains for MB8.
- Rich retry workflows for failed outbound delivery remain intentionally small/deferred.
