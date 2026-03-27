# ManagerBot Baseline Alignment Audit (Launch/V1)

## 1) Executive summary

TradeFlow had schema drift between the `ops` ORM layer and the launch migration contract. The biggest breakage was that repositories and services were writing/reading model fields that did not exist in baseline DB columns (or used different names), causing unstable behavior in quote thread persistence, manager presence, assignment event recording, and future delivery-attempt paths.

This stabilization task reconciles launch runtime code to the baseline schema while preserving application-facing attribute names where practical via `mapped_column("db_column", ...)` aliases.

## 2) Source of truth used in this task

Launch/V1 source of truth: `alembic/versions/20260323_0001_prelaunch_baseline_reset.py`.

This task intentionally did **not** implement richer future ManagerBot schema ideas that are ahead of this baseline.

## 3) Drift inventory

| Area | Drift observed | Baseline column(s) | Resolution | Status |
|---|---|---|---|---|
| `quote_case_thread_entries` | Model used `body`, `entry_kind`, `body_format`, `source_channel`, `telegram_chat_id`; `author_side` not explicitly mapped | `body_text`, no `entry_kind`, no `body_format`, no `source_channel`, no `telegram_chat_id`; `author_role` | Removed unsupported persisted fields; mapped `author_side -> author_role`; mapped `body_text` directly | Resolved now |
| `quote_case_internal_notes` | Model used `note_kind`, `body`; omitted `author_role`, `body_format`, `visibility_scope` | `author_role`, `body_text`, `body_format`, `visibility_scope` | Reconciled model fields to baseline names, kept app alias `author_side -> author_role` | Resolved now |
| `quote_case_assignment_events` | Model used `performed_by_actor_id` column name; omitted `event_seq` | `triggered_by_actor_id`, `event_seq` | Mapped `performed_by_actor_id -> triggered_by_actor_id`; added `event_seq`; repository now sets per-case sequence | Resolved now |
| `manager_presence_states` | Model used `manager_actor_id` as physical column | `actor_id` | Mapped `manager_actor_id -> actor_id` and kept repo/service API stable | Resolved now |
| `quote_case_routing_decisions` | No meaningful drift | Baseline already matched | Verified and left unchanged | Verified aligned |
| `reply_delivery_attempts` | Model fields diverged from baseline (`delivery_channel`, `delivery_status`, `provider_message_id`, `retry_count`, `delivered_at`/`failed_at`) | `transport`, `status`, `telegram_message_id`, `attempt_number`, `completed_at`, `error_message` | Added baseline mappings with app-facing aliases (`delivery_channel -> transport`, etc.); removed non-baseline timestamp split | Resolved now |
| Quote service customer-message persistence | Service persisted unsupported thread-entry fields and required persisted `entry_kind` semantics | Baseline thread-entry subset | Service now persists only baseline-supported thread-entry fields and keeps analytics semantics without persisted `entry_kind` dependency | Resolved now |
| Bot timeline rendering | Rendering read `entry.body` and depended on `entry_kind` existing | Baseline uses `body_text`; `entry_kind` non-baseline | Rendering now prefers `body_text`, and treats semantic kind as optional (`message_kind` fallback) | Resolved now |

## 4) What was fixed in this task

- Reconciled `app/db/models/ops/managerbot.py` with baseline column contract for all audited ops tables.
- Updated quote customer-message persistence path to stop writing non-baseline thread-entry columns.
- Preserved launch semantics for analytics events (`reply` / `revision` / `replacement`) without persisting `entry_kind`.
- Updated bot shell quote timeline helpers to consume reconciled body/semantic fields safely.
- Expanded repository tests to exercise thread entries, internal notes, assignment events, presence, routing decisions, and reply delivery attempts against reconciled models.
- Added schema regression guard assertions to fail fast on future model-vs-baseline drift.

## 5) Intentionally deferred items

The following remain intentionally deferred for later ManagerBot alignment because they are ahead of the launch baseline schema:

- Persisted, first-class `entry_kind` column for thread entries.
- Richer channel/source metadata persistence beyond baseline (`source_channel`, `telegram_chat_id`, etc.).
- Split delivery completion semantics into dedicated delivered/failed timestamp columns at the reply-attempt layer (baseline uses `completed_at` + status/error).
- Any broader ManagerBot V2 queue/routing redesign not represented in baseline migration.

## 6) Follow-up plan for later ManagerBot alignment

1. Produce a formal migration plan from baseline to target ManagerBot schema (additive migrations only).
2. Introduce new columns (e.g., `entry_kind`) behind compatibility adapters, then backfill from safe sources.
3. Move service/repository read paths to dual-read during transition, then cut over after backfill verification.
4. Update domain docs and tests to reference explicit schema version checkpoints (V1 baseline vs post-alignment schema).

## 7) Risk notes for launch/V1

- Launch timeline rendering remains intentionally simple when semantic message kind is unavailable from persistence.
- Delivery attempt persistence is baseline-minimal; richer transport telemetry is deferred.
- Further schema drift risk is now mitigated by explicit metadata regression tests, but any future doc-led changes must ship with concrete migrations first.
