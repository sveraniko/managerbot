# MB-C AI/Assistant-to-Manager Handoff Alignment Report

Date: 2026-03-28  
Scope: MB-C only (AI handoff semantics for manager review surfaces)

## Files changed

- `managerbot/app/services/ai_recommender.py`
- `managerbot/app/services/rendering.py`
- `managerbot/app/bot/handlers.py`
- `managerbot/tests/test_ai_reader.py`
- `managerbot/tests/test_queue_and_case_views.py`

## AI handoff contract introduced/aligned

MB-C aligns manager-side AI recommendation payloads with an explicit, minimal handoff contract in `AIRecommendation`:

- `handoff_state` enum:
  - `resolved`
  - `ambiguous`
  - `alternatives_available`
  - `not_found`
  - `needs_human_review`
- `handoff_rationale` (short manager-readable explanation)
- `resolved_item_title` (optional AI-resolved identity hint)
- `alternatives` list (compact option records with title + commercial cues):
  - `selling_unit`
  - `min_order`
  - `increment`
  - `packaging_context`
  - `availability`
  - `rationale`

Additionally, a deterministic manager-control helper was added:

- `recommendation_supports_draft_adoption(...)`
  - allows AI draft adoption only for `resolved` and `alternatives_available`
  - blocks adoption for `ambiguous`, `not_found`, `needs_human_review`

## Manager-side representation of ambiguity / alternatives / not-found

Manager case detail rendering now includes a dedicated AI handoff section under recommendations:

- explicit `Handoff status`
- `Handoff rationale`
- `Resolved item` (prefer manager item detail truth)
- structured commercial constraints
- alternatives list (if present)
- explicit action-safety line for uncertain states

Deterministic override rules were added to prevent unsafe contradictions:

- AI says `resolved` but manager item semantics are incomplete -> render as `needs_human_review`
- AI says `not_found` while manager already has item detail -> render as `needs_human_review`

## MB-A and MB-B semantics preservation

### MB-A preservation (item-detail contract)

MB-C rendering explicitly reuses manager item-detail structured fields:

- title
- selling unit
- min order
- increment
- packaging context
- availability

These constraints are rendered in AI handoff output so manager review remains anchored to structured operational truth.

### MB-B preservation (wording discipline)

Recommender prompt contract now explicitly requests customer-facing terminology:

- `Selling unit`
- `Min order`
- `Increment`
- packaging context

And explicitly bans shorthand (`MOQ`, `step`) for customer-visible draft text.

AI draft adoption remains manager-controlled and now adds handoff-state gating to reduce unsafe usage.

## Intentionally left for MB-D

Kept out of MB-C by design:

- queue/panel visual redesign
- broader UI/navigation polish
- architecture/schema changes
- autonomous AI execution
- unrelated non-handoff UX expansion
