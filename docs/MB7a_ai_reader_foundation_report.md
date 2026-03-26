# MB7a AI Reader Foundation Report

## Scope delivered
MB7a introduces the first **reader-only AI copilot** layer for ManagerBot case detail.
The implementation is advisory and bounded; it does not execute operational actions.

## AI configuration/service added
- Extended `pydantic-settings` with AI reader controls:
  - `ai_reader_enabled`
  - `ai_api_key`
  - `ai_base_url`
  - `ai_model`
  - `ai_timeout_seconds`
  - `ai_max_input_chars`
  - `ai_max_output_tokens`
  - `ai_include_internal_notes`
- Added dedicated AI service module (`app/services/ai_reader.py`) with:
  - isolated OpenAI chat-completions client,
  - strict JSON-schema output contract,
  - packet builder,
  - timeout/provider/parse-failure handling,
  - structured logging without dumping full prompt/context.

## Case packet structure
MB7a uses a compact, explicit `AIReaderPacket` with bounded case-scoped fields:
- case identity/display number,
- customer label,
- commercial/operational status,
- waiting state,
- priority/escalation,
- assignment label,
- linked quote/order display numbers,
- SLA state,
- delivery status summary,
- recent customer-visible thread lines,
- recent internal notes (feature-gated).

The packet builder trims content to configured input size caps.

## Structured output schema
MB7a defines strict typed schema `AIReaderAnalysis`:
- `summary`
- `customer_intent`
- `risk_flags`
- `missing_information`
- `recommended_next_step`
- `confidence`
- optional compact fields (`timeline_brief`, `tone_guidance`)

Model output is validated; invalid JSON/schema mismatch is rejected with safe fallback.

## Triggering AI from case detail
- Added case-detail action: **AI Analyze / Refresh**.
- AI result is rendered in a dedicated block in case detail:
  - explicitly labeled **advisory only**,
  - compact and separate from operational truth fields,
  - supports refresh/regenerate on-demand.
- Failure renders a clean unavailable line in the AI block.

## Safe state handling
- Extended `ManagerSessionState` with AI snapshot fields tied to `ai_case_id`.
- Added helper logic to:
  - bind AI output to exact case,
  - suppress AI output for other cases,
  - clear stale AI snapshot on case switch and home navigation.

This prevents cross-case AI bleed.

## Caching decision
- **Caching explicitly deferred in MB7a.**
- Rationale: keep first AI seam simple and deterministic; avoid introducing cache invalidation complexity before MB7b.

## Failure/timeout behavior
- Timeout => compact user-facing unavailable message.
- Provider/API failure => compact unavailable message.
- Invalid model output => compact invalid-analysis message.
- Logs include case id/model/status for observability.

## Migration discipline and guardrails confirmation
- No migration created.
- No local AI DB tables introduced.
- No autonomous actions added.
- No customer messages are sent by AI.
- AI remains strictly reader/advisory only.

## Deferred intentionally to MB7b+
- draft reply suggestions,
- note drafting assistance,
- actionable proposal workflows with explicit approval UX,
- any AI-assisted action execution layer.
