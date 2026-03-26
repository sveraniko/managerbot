# MB7c AI Hardening, Policy, and Guardrails Report

## Scope delivered
MB7c hardens the existing AI copilot layer from MB7a/MB7b for safer operational use while keeping AI advisory and human-controlled.

## Policy/config controls added
Added explicit settings controls in `pydantic-settings`:
- `ai_enabled`
- `ai_reader_enabled`
- `ai_recommender_enabled`
- `ai_include_internal_notes`
- `ai_max_thread_entries`
- `ai_max_internal_notes`
- `ai_max_input_chars`
- `ai_cache_ttl_seconds`
- `ai_min_confidence_for_draft_adoption_warning`
- `ai_model`
- `ai_reader_prompt_version`
- `ai_recommender_prompt_version`

## Context minimization and token budgeting
`CaseAIPacketBuilder` now enforces bounded, deterministic context shaping:
- bounded latest thread entries and notes by explicit policy caps,
- optional internal-note inclusion only when policy allows,
- lightweight redaction for email/phone-like strings,
- deterministic trimming order under size pressure:
  1) drop oldest thread entries,
  2) drop oldest notes,
  3) shrink long lines.

## Caching / cost control
Added lightweight in-memory TTL cache (`InMemoryAICache`) for reader/recommender outputs:
- case-scoped hash key from packet + model + prompt version,
- explicit TTL,
- cache-hit metadata surfaced to render,
- malformed cache payload fails safe and is evicted,
- regenerate behavior bypasses cache when manager re-runs AI on already-analyzed case.

No DB cache table was added.

## Confidence handling and rendering
Recommendation confidence is now operationally visible:
- low-confidence recommendations are labeled with warning text,
- draft action buttons show warning marker when confidence is below configured threshold,
- draft adoption remains available but visibly cautionary,
- no autonomous execution path was introduced.

## Prompt/version discipline
Prompt/version discipline is explicit:
- reader and recommender prompts include explicit version identifiers,
- result metadata carries model + prompt version + cache source,
- these fields are shown in compact case-detail AI blocks.

## Observability/audit logging
AI logs were expanded with safe operational metadata:
- feature (`reader`/`recommender`) start/success/failure,
- case id/display,
- model,
- prompt version,
- timeout/provider/parse failures,
- force-refresh/cache-hit behavior.

Prompt/body dumps are not logged.

## Failure-mode hardening
Improved safe behavior for:
- disabled feature flags,
- provider timeout/errors,
- malformed model JSON/schema mismatch,
- malformed cached payload,
- stale AI state isolation by case id,
- case-switch clears stale AI snapshot.

## Migration/autonomy confirmations
- No migration created.
- No AI DB table created.
- AI remains non-autonomous:
  - no auto-send,
  - no auto-save note,
  - no auto-escalate,
  - no auto-assignment,
  - no auto-close.

## Intentionally deferred
- Redis-backed AI cache (current implementation is lightweight in-memory TTL).
- Richer policy tiers/advanced governance.
- Multi-turn AI workflow orchestration.
