# ERG3 Customer Card / Direct Contact Report

## Scope delivered
ERG3 adds a real **Customer Card** and practical direct-contact ergonomics in standalone ManagerBot case detail, without schema changes or new subsystems.

## Customer-card fields surfaced
Implemented `CustomerCard` view model and case-detail rendering with explicit presence/absence handling for:
- customer label (`core.quote_cases.customer_label`)
- customer actor id (`core.quote_cases.customer_actor_id`)
- Telegram chat id (`core.quote_cases.customer_telegram_chat_id`)
- Telegram user id fallback via actor binding (`core.actor_telegram_bindings.telegram_user_id`)
- Telegram username (placeholder field in view model; not filled by current backbone contract path)
- phone number (placeholder field in view model; not filled by current backbone contract path)

If data is missing, UI prints `Unavailable` explicitly.

## Case-detail UX updates
- Customer card is now rendered near the top of case detail, before thread/note blocks.
- Case detail includes compact direct-contact policy cue:
  - direct channel can be used for fast clarification,
  - case truth must still be preserved via internal note/reply.

## Direct-contact actions implemented
Added a dedicated **Contact actions** panel from case detail with data-driven actions:
- Open Telegram direct link (only if username or positive user/chat id is available)
- Show @username (if available)
- Show chat ID (if available)
- Show user ID (if available)
- Show phone (if available)

No fake/dead actions are shown when data is missing.

## Lightweight “log contact outcome” pattern
Implemented `Log contact outcome note` action in contact panel.
It reuses the existing compose/internal-note flow by preloading a note template:

`Direct contact outcome: / Channel / Summary / Next step`

No new persistence subsystem or table was introduced.

## Search / customer card consistency
Search result view model now carries optional customer actor/chat identifiers.
Rendering keeps customer label as primary cue, and falls back to actor/chat identity hint only when label is missing.
This aligns search identity cues with what manager sees in Customer Card.

## Backbone contract gaps discovered
Current repo query contracts do not expose canonical customer Telegram username or phone in case/search read paths.
ERG3 does not fabricate these fields; they remain explicitly unavailable unless backbone provides them.

## Migration discipline confirmation
- No migration created.
- No schema changes.
- No local customer shadow table.

## Intentionally deferred (ERG4+)
- Order action block and handoff actions (ERG4 scope)
- Group topics bridge (deferred MB8 scope)
- CRM profile/history subsystem
