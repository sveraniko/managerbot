# ERG2a VIP Priority Semantics Hardening Report

## What inconsistency was found
After ERG2, `vip` was visible in rendering and supported by filters, but behavior drift remained in several ordering paths:
- duplicated priority-rank logic existed in multiple places;
- hot-task `Urgent / VIP / escalated` lane membership mistakenly included `high` but could exclude `vip` in one branch;
- escalation-to-owner logic demoted non-`urgent` priorities to `high`, which incorrectly downgraded `vip`;
- fake repository search/filter semantics were less aligned with SQL ordering semantics.

## Canonical VIP ordering rule chosen
ERG2a enforces a single business rule for V1:
- `urgent` and `vip` are top-tier prominence;
- `high` is next tier;
- `normal` and other values are lower tier.

Rendering remains explicit (`vip` is still rendered as `vip`), while ranking/ordering treats `vip` as top-tier.

## Code changes implemented
1. Added centralized priority semantics helper:
   - `managerbot/app/services/priority.py`
   - Provides canonical `priority_rank(...)`, top-tier predicate, and elevated-priority predicate.

2. Switched SQL queue/search/workdesk ordering to centralized helper:
   - `managerbot/app/repositories/sql.py`
   - Removed duplicated inline rank mappings and local helper drift.

3. Fixed hot-task lane membership:
   - `urgent_escalated` lane now consistently uses elevated priority (`high|urgent|vip`) plus escalation.
   - Top-tier checks (`urgent|vip`) are reused for urgent semantics.

4. Fixed escalation priority preservation:
   - `SqlCaseRepository.escalate_to_owner(...)` now preserves `vip` (and `urgent`) instead of demoting `vip` to `high`.

5. Aligned fake repository behavior:
   - `managerbot/app/repositories/fakes.py`
   - Search ordering now applies top-tier ranking cues and active-before-archived ordering.
   - Fake escalation now preserves `vip`/`urgent` instead of unconditional demotion to `high`.

## Tests added/updated
Updated tests to prove VIP semantics consistently:
- `managerbot/tests/test_workdesk_hot_tasks.py`
  - urgent/VIP/escalated bucket includes VIP cases and orders deterministically.
- `managerbot/tests/test_sql_repositories_integration.py`
  - urgent queue keeps top-tier semantics (`vip` included, `high` excluded from top-tier urgent queue);
  - search ordering keeps VIP prominence;
  - escalation preserves VIP priority.

## Migration discipline
- No migration created.
- No schema changes introduced.

## Scope guardrails
- ERG3 is out of scope and was not started.
- No customer card was added.
- No order action block was added.
- No archive/search/filter UI redesign was performed.
