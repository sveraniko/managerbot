# MB7b Controlled Recommender Report

## Scope delivered
MB7b extends MB7a reader-only AI into a **controlled recommender copilot** mode for manager case handling.
The AI can now propose actionable drafts and recommendations, while all operational actions remain manager-confirmed.

## Recommender schema/service added
- Added `app/services/ai_recommender.py` with strict typed output model `AIRecommendation`.
- Added constrained `RecommendedAction` enum:
  - `reply`
  - `clarify`
  - `escalate`
  - `wait`
  - `review_delivery_issue`
- Added `AIRecommenderService` with:
  - strict JSON-schema response contract,
  - timeout/provider/invalid-output safe handling,
  - advisory-only prompt contract constrained to case packet facts.

## Triggering decision and implementation
Decision: **single AI action in case detail** that refreshes both MB7a reader analysis and MB7b recommendations.
- Action label updated to: `AI Analyze + Recommend / Refresh`.
- Handler now runs:
  1) reader analysis
  2) recommender generation
  3) case-bound state binding for both outputs.

Rationale:
- keeps operator mental model simple (one AI refresh entry point),
- avoids duplicated buttons/flows,
- preserves compact single-panel UX.

## Recommendation rendering in case detail
Case detail now shows a compact advisory recommendation block:
- recommended action,
- next step,
- reply draft snippet,
- internal note draft snippet,
- clarification questions,
- escalation suggestion + rationale,
- confidence.

Block is explicitly marked advisory/non-autonomous.

## Use as reply draft flow
Added action: `Use AI reply draft`.
- Available only when valid recommendation exists for active case.
- Loads AI text into existing reply compose draft.
- Opens existing reply preview/confirm path.
- Sending still requires explicit manager confirm (`reply_confirm`).
- No autonomous send behavior was added.

## Use as internal note draft flow
Added action: `Use AI note draft`.
- Available only when valid recommendation exists for active case.
- Loads AI text into note compose draft.
- Presents explicit note preview controls (`Save note draft` / `Edit` / `Cancel`).
- Saving note still requires explicit manager action.
- No autonomous note save was added.

## Escalation recommendation surfacing
- AI recommendation block now surfaces escalation suggestion and short rationale when applicable.
- Existing explicit manual action (`Escalate to owner`) remains the only escalation executor.
- No AI escalation execution path exists.

## Clarification questions support
- Clarification questions from AI recommendations are rendered compactly in case detail.
- They are shown as suggestions only and can inform manager edits to draft reply.
- No auto-send behavior exists.

## AI state/session safety hardening
`ManagerSessionState` now stores recommendation snapshot separately from reader output:
- `ai_recommendation`
- `ai_recommendation_error`

Safety behavior:
- recommendation is tied to `ai_case_id`,
- stale/cross-case snapshots are suppressed,
- invalid stored snapshots fail safe with explicit re-run message,
- AI draft adoption helpers (`start_reply_from_ai`, `start_note_from_ai`) enforce selected-case match.

## Caching decision
- **Caching deferred in MB7b**.
- Reason: keep controlled recommender deterministic and simple; avoid cache invalidation complexity in this step.

## Failure/timeout behavior
- Recommender timeout => compact unavailable message.
- Provider failure => compact unavailable message.
- Invalid output/schema mismatch => safe invalid-output message.
- "Use AI draft" without valid case-bound recommendation => rejected with explicit alert.
- Disabled feature path => explicit disabled message.

## Migration/autonomy confirmations
- **No migration was created.**
- **No local AI tables were introduced.**
- **AI does not execute actions autonomously**:
  - no auto-send,
  - no auto-save note,
  - no auto-escalate,
  - no autonomous state-changing operations.

## Intentionally deferred to MB7c+
- policy/guardrail layers beyond current strict schema + prompt constraints,
- optional recommendation caching,
- richer multi-turn AI workflow controls.
