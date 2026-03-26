# MB6a Presence Semantics Hardening Report

## Inconsistency found
After MB6, presence behavior was inconsistent across the codebase:
- `SqlPresenceRepository.get_status(...)` treated missing presence rows as `online`.
- Internal notification recipient listing (`list_internal_recipients`) already coalesced missing rows to `offline`.
- As a result, the same manager could appear online in hub/home while being treated offline in notification targeting.

This created an operational mismatch for queue visibility and alert expectations.

## Canonical default rule chosen
MB6a hardens one canonical rule and applies it everywhere:

- **If no persisted presence row exists for a manager, default presence is `offline`.**

Why this rule:
- absence of persisted presence is not proof of availability;
- notification policy already aligned more closely with this safer behavior;
- it avoids false-positive online signaling.

## Code changes made
1. Presence repository default:
- `SqlPresenceRepository.get_status` now returns `PresenceStatus.OFFLINE` when no row exists.

2. Fake repository parity for service-level tests:
- `FakePresenceRepository.get_status` now also defaults to `PresenceStatus.OFFLINE`.

3. No notification architecture rewrite:
- targeting logic remains unchanged;
- recipient-list SQL keeps `coalesce(..., 'offline')`, which now matches repository/hub behavior.

## Tests added/updated
1. Presence consistency tests:
- integration test now asserts missing presence row resolves to `offline` in SQL repository;
- integration test added for internal recipient listing defaulting to `offline` for actors without presence rows;
- service-level hub test added to verify hub-facing behavior reports `offline` by default.

2. Toggle flow tests:
- updated presence toggle test now verifies:
  - default `offline`,
  - first toggle -> `online`,
  - second toggle -> `away`,
  - persisted state is reflected after each toggle.

3. Notification targeting tests:
- added test proving `case_visible` does **not** target a manager whose presence is effectively missing/offline (owner still receives).
- existing tests for busy/away/offline fallback and assigned-to-me policy continue to pass.

4. Regression scope:
- MB6 notification loop and policy tests remain in place and passing;
- MB5 reply/delivery integration tests remain in place and passing.

## Migration discipline confirmation
- **No migration was created in MB6a.**

## Scope control confirmation
- **MB7 remains out of scope** (no AI copilot work).
- **Group topics bridge remains out of scope**.
- PR is narrow and limited to presence semantics hardening and related tests/docs alignment.
