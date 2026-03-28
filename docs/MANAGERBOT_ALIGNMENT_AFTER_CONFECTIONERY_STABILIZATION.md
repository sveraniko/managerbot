# MANAGERBOT ALIGNMENT AFTER CONFECTIONERY STABILIZATION (D7)

## 1. Executive summary

D1–D6 stabilized TradeFlow’s confectionery/product-search-AI chain from source ingestion to assistant-facing language.

What changed materially:
- Confectionery structured fields were repaired and propagated as first-class attributes instead of weak text blobs.
- Search document/read-model continuity was hardened so repaired attributes survive indexing/hydration/card mapping.
- SKU card/detail semantics were polished around practical commercial language (`Min order`, `Increment`, packaging context, shelf life, origin).
- Confectionery search relevance and Meili filterability were aligned with packaging/unit/weight/shelf-life intent.
- AI/voice result and confirmation semantics were updated to match the repaired commercial/search contract.

Why this matters for ManagerBot:
- ManagerBot can no longer be designed as if product truth is thin or unstable.
- Manager-facing case/item review must reflect the same stabilized catalog/commercial semantics as buyer UI and AI assistant.
- Old assumptions (“generic unitless item card”, “fallback descriptor truth”, “AI uses technical internal wording”) are now obsolete.

This document defines how ManagerBot follow-up work must align with that stabilized reality without turning D7 into a broad implementation wave.

---

## 2. New source of truth for ManagerBot

ManagerBot follow-up PRs should now treat the following as trustworthy system contracts.

### 2.1 Repaired confectionery structured fields are reliable input

Manager-facing item context may rely on stabilized structured attributes when present:
- `weight`
- `piece_weight`
- `shelf_life`
- `country_of_origin`
- `description`
- `dimensions`
- `gross_weight`
- packaging quantity hints (`box_quantity` / `in_box` / `units_per_box`) where available

Implication: manager surfaces should prefer structured fields over synthetic descriptor generation.

### 2.2 Read-model/card field continuity is no longer best-effort

The D3 stabilization hardened search-document merge and Meili hit hydration fallbacks.

Implication: ManagerBot case/item detail can assume that card-visible structured fields survive:
- projection merge,
- index serialization,
- hit hydration,
- response mapping.

### 2.3 Packaging and selling-unit semantics are now part of operational truth

D4–D6 aligned user-facing language around:
- selling unit,
- min order,
- increment,
- packaging context (e.g., in-box/in-selling-unit quantities).

Implication: ManagerBot confirmation/reply views should not regress to legacy generic wording (`MOQ/step/pack`-style internal shorthand for customer-visible copy).

### 2.4 Search/Meili confectionery alignment is now intentional and queryable

D5 added confectionery-specific semantic aliases/concepts and explicit filterable attributes for repaired fields.

Implication: manager search handoff and recommendation paths should trust that packaging/shelf-life/weight/origin intents are first-class and not accidental.

### 2.5 AI/voice contract language was refreshed

D6 updated assistant result/confirmation formatting and quantity/packaging interpretation for confectionery.

Implication: ManagerBot AI-assisted actions must consume/emit language compatible with current assistant contract (commercially readable, packaging-aware, no stale generic phrasing).

---

## 3. ManagerBot impact map

D1–D6 affects the following ManagerBot zones directly.

### 3.1 Case/item review surfaces
- Case detail item blocks must expose stabilized commercial/product essentials (unit, min order, increment, packaging context, shelf life, origin).
- “Thin card” assumptions should be removed from manager-side detail templates.

### 3.2 Manager-facing item details and linked artifacts
- When managers inspect SKU context before replying/revising, detail payload should reuse stabilized item contract (same field semantics as buyer detail).
- Avoid manager-only field naming drift that reintroduces ambiguity.

### 3.3 Reply and confirmation language
- Manager confirmations to customer should align with current buyer/assistant vocabulary (`Min order`, `Increment`, selling unit context).
- Avoid backend/operator slang leaking into customer-visible thread entries.

### 3.4 Ops panels referencing commercial semantics
- Queue/detail/panel actions that show “what to do next” must account for repaired packaging and quantity constraints.
- Escalation/review prompts should be aware that data quality for confectionery fields is now materially improved.

### 3.5 Recommendation/search handoff
- Manager-triggered “find alternatives / suggest options” flows should leverage stabilized confectionery intent handling rather than old generic fallback assumptions.

### 3.6 AI-assisted manager actions
- If manager-side AI assist is used for draft/reply preparation, it must align with D6 payload/wording conventions and D5 search semantics.

---

## 4. Gaps that still exist

Even after D1–D6, ManagerBot remains only partially aligned.

### 4.1 Manager surfaces are not yet explicitly bound to stabilized item-detail contract
Current manager ops/domain layers exist, but there is no dedicated manager-facing item presentation contract that guarantees reuse of D4-ready semantics.

### 4.2 Manager reply flows may still contain stale wording risk
Manager architecture docs are strong on flow separation and persistence, but wording-level alignment with D4/D6 language (commercial readability + packaging semantics) is not yet codified as an implementation contract.

### 4.3 Packaging/min/increment visibility in manager case workflows is not yet guaranteed end-to-end
While buyer/AI paths now expose these clearly, manager case-detail and compose-review surfaces still need explicit follow-up requirements/tests to prevent regressions.

### 4.4 AI-to-manager handoff semantics are not yet concretely frozen
D6 improved assistant-side payloads, but manager-side adoption rules (what fields are shown, how confirmations are phrased, which values are mandatory) still need explicit follow-up PR scope.

### 4.5 Documentation input gap noted for this D7 step
`docs/MANAGERBOT_LAUNCH_ALIGNMENT_GAP_REPORT.md` was requested but is currently absent in the repository. Alignment conclusions here are therefore grounded in available D1–D6 and ManagerBot canonical docs, with this missing artifact treated as a documentation risk to close.

---

## 5. Explicit non-goals for launch/V1 (for this alignment wave)

This D7 alignment step and immediate follow-up PRs must **not** do the following:

- No ManagerBot architecture redesign.
- No broad ops schema redesign or reopening baseline drift work without a concrete newly discovered mismatch.
- No “V2 dream scope” (omnichannel expansion, full generic case engine, new cross-product abstraction wave).
- No unrelated customer UI refactor bundled into manager alignment PRs.
- No replacing source-of-truth principles already fixed (ops persistence remains canonical for manager operational truth).

---

## 6. Recommended PR sequence for ManagerBot follow-up work

Below is the recommended post-D7 implementation sequence.

## MB-A — Manager item-detail contract alignment

### Goal
Define and implement a manager-facing item detail contract that reuses stabilized D3/D4 field semantics (commercial + packaging + essentials) consistently.

### Scope
- Add/align manager-side item detail presenter/DTO(s) with repaired structured fields.
- Ensure manager case detail uses canonical labels/ordering for key commercial data.
- Reuse existing stabilized field names and fallback rules; avoid manager-specific semantic forks.

### Non-goals
- No queue architecture changes.
- No AI orchestration changes beyond consuming stable payload fields.
- No broad formatter redesign outside manager-facing surfaces.

### Exit criteria
- Manager case item details show reliable: selling unit, min order, increment, packaging context, shelf life, origin (when available).
- No synthetic descriptor fallback for fields that now exist structurally.
- Tests prove parity with stabilized search/card payload semantics.

## MB-B — Manager reply and confirmation wording alignment

### Goal
Align manager compose/confirm customer-visible language with D4/D6 commercial vocabulary and packaging-aware phrasing.

### Scope
- Update manager reply-preview/confirm text templates.
- Normalize terms across manager UI and outbound thread entries.
- Add explicit guardrails preventing legacy technical wording leakage in customer-visible copy.

### Non-goals
- No delivery transport redesign.
- No policy/state-machine redesign.

### Exit criteria
- Customer-visible manager confirmations use aligned terminology (`Min order`, `Increment`, selling unit/packaging context).
- Regression tests cover wording and structured constraint rendering.

## MB-C — AI/assistant-to-manager handoff semantics alignment

### Goal
Standardize how AI-assisted manager actions carry resolved item/commercial/search semantics into manager review and decision flows.

### Scope
- Define handoff payload contract for manager-side consumption of D6 outputs.
- Ensure ambiguity/alternatives and constraint summaries are rendered consistently in manager context.
- Wire deterministic mapping from AI payload to manager compose/review surfaces.

### Non-goals
- No new autonomous AI behaviors.
- No expansion to non-confectionery orchestration redesign.

### Exit criteria
- Manager can review AI-proposed item/action with complete commercial constraints and packaging context.
- Ambiguous/not-found/alternative states are manager-readable and action-safe.

## MB-D — Case detail and queue presentation polish (stabilized semantics)

### Goal
Apply final manager UX polish so case/queue surfaces reflect stabilized product/commercial truth without overhauling architecture.

### Scope
- Update case detail snippets and queue metadata labels where needed.
- Ensure manager action prompts are consistent with repaired search/commercial semantics.
- Small navigation/copy consistency adjustments only.

### Non-goals
- No new panel families.
- No unrelated global Telegram shell redesign.

### Exit criteria
- Manager-facing case/queue screens no longer show stale generic product semantics.
- UX text and action prompts are consistent with MB-A/B/C contracts.

---

## 7. Testing implications

When implementation starts after D7, tests should be updated in a focused way.

### 7.1 Contract tests (manager item detail)
- Validate manager item-detail DTO/presenter field continuity from search/read-model payloads.
- Assert presence/absence rules for repaired structured fields.

### 7.2 Reply wording regression tests
- Assert customer-visible manager confirmation text uses aligned commercial terminology.
- Assert packaging/min/increment visibility in manager compose review.

### 7.3 AI handoff tests
- Validate manager rendering for resolved/ambiguous/not_found/alternatives outcomes.
- Validate constraint summary parity with D6 assistant outputs.

### 7.4 Integration tests across quote-thread + ops state
- Ensure manager replies still persist correctly in ops thread entries and state transitions remain valid.
- Ensure wording/presentation alignment changes do not break reply delivery tracking behavior.

### 7.5 Smoke scenarios to add to manager wave
- “Manager reviews confectionery item with packaging context before reply.”
- “AI suggests alternatives; manager sees commercial constraints and confirms safely.”
- “Manager customer confirmation reflects stabilized min/increment/selling-unit semantics.”

---

## 8. Risk notes

### 8.1 Semantic split risk
If manager surfaces invent parallel field semantics, TradeFlow will re-fragment between buyer, AI, and manager views.

### 8.2 Wording regression risk
If manager templates keep legacy internal wording, customer thread clarity regresses despite D4/D6 improvements.

### 8.3 Hidden fallback risk
If manager code reintroduces descriptor/blob fallback where structured fields exist, case handling quality will silently degrade.

### 8.4 Handoff ambiguity risk
If AI-to-manager payload contract is not explicit, operators may act on incomplete or differently interpreted constraints.

### 8.5 Scope-creep risk
If MB follow-ups pull in architecture/schema/UI megachanges, delivery discipline from D1–D6 will be lost and manager wave predictability will drop.

### 8.6 Documentation completeness risk
Missing requested gap-report artifact should be closed or replaced to keep alignment package auditable and reduce interpretation drift in subsequent PRs.

---

## Final D7 alignment statement

ManagerBot follow-up implementation must now align to a stabilized TradeFlow truth where confectionery structured data, search/card continuity, packaging/commercial semantics, and AI language are materially improved and trustworthy.

The next step is disciplined MB-A → MB-B → MB-C → MB-D execution, each with explicit boundaries and tests, rather than a broad undifferentiated ManagerBot implementation PR.
