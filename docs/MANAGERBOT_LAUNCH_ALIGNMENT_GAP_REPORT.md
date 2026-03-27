# ManagerBot Launch Alignment Gap Report

Date: 2026-03-27
Scope: launch/V1 alignment only (no schema changes, no V2 redesign).

## 1) Current implementation surface

### Runtime/bootstrap and seams already present
- Separate ManagerBot runtime entrypoint and app assembly exist (`managerbot/app/main.py`, `managerbot/app/__main__.py`).
- Access gating is limited to OWNER/MANAGER via actor lookup (`managerbot/app/services/access.py`, `managerbot/app/repositories/sql.py`).
- Separate manager session state namespace exists (`managerbot/app/state/manager_session.py`) and is not shared with customer shell state.

### ManagerBot UI/runtime paths already implemented
- Hub/workdesk + queue lanes + search + filters + case detail navigation are implemented (`managerbot/app/bot/handlers.py`, `managerbot/app/bot/keyboards.py`, `managerbot/app/services/rendering.py`).
- Case detail includes customer thread, internal notes, delivery snapshot, order/contact action panels, and AI advisory blocks.
- Compose flows for reply and internal note are implemented with explicit preview/confirm and stale-compose guards (`managerbot/app/services/compose.py`, `managerbot/app/bot/handlers.py`).

### Persistence/repository contracts already implemented
- Queue/read model paths are derived from `ops.quote_case_ops_states` + `core.quote_cases` and not from topic/event-only assumptions (`managerbot/app/repositories/sql.py`).
- Case detail, claim, escalate, internal notes, outbound reply persistence, and reply-delivery attempts are implemented on canonical `ops.*` tables.
- Presence state repository uses `ops.manager_presence_states.presence_status`.

### Quote/ops dependencies currently used
- Core case anchor: `core.quote_cases` (+ optional `core.orders`).
- Operational state anchor: `ops.quote_case_ops_states`.
- Thread + notes + assignment history + delivery attempts: `ops.quote_case_thread_entries`, `ops.quote_case_internal_notes`, `ops.quote_case_assignment_events`, `ops.reply_delivery_attempts`.

## 2) Launch/V1-compatible gaps found

1. **Assignment flow gap:** only claim/escalate existed in service/repository contracts; explicit assign/reassign/unassign repository actions were missing as first-class operations.
2. **Timeline author-side degradation gap:** case timeline was rendered from direction/body/delivery only; author-side-compatible rendering was not wired through supported persisted role fields.
3. **Workdesk heading drift:** rendered workdesk header did not match current expected launch wording in tests.

## 3) Deferred items (intentionally out of scope)

The following remain intentionally deferred for this launch-alignment task:
- Persisted `entry_kind`-driven timeline semantics.
- Richer source/channel metadata beyond baseline-supported fields.
- ManagerBot V2 routing redesign and expanded role hierarchy.
- Group topics bridge (MB8) and non-launch integrations.
- Any schema expansion or migrations.

## 4) Execution plan (this task)

1. Add explicit assign/reassign/unassign methods in ManagerBot case repository contracts and implementations while preserving existing claim/escalate flows.
2. Persist canonical assignment events for assign/reassign/unassign and keep ops-state transitions baseline-compatible.
3. Thread author-side alignment: map persisted author role into timeline rendering as graceful author-side cue (without requiring deferred columns).
4. Fix launch-visible workdesk heading drift.
5. Add/update tests for:
   - assign/reassign/unassign event/state behavior in SQL integration tests,
   - existing queue/case/reply/presence paths regression stability via full suite.

## Notes on source-of-truth inputs

- `docs/MANAGERBOT_BASELINE_ALIGNMENT_AUDIT.md` is referenced by task instructions but is absent in this repository.
- `docs/Files from trade flow - ...` directory referenced by task instructions is also absent in this repository.
- Alignment decisions were therefore based on available ManagerBot docs, current reconciled repositories/runtime/tests, and explicit no-schema-change constraints.
