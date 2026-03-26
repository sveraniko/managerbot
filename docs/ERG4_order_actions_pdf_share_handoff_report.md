# ERG4 Order Actions / PDF / Share / Handoff Report

## Scope delivered
ERG4 adds a lightweight **Order Action Block** and operational order handoff surface inside ManagerBot case flow, without schema changes, migrations, or ERP integration.

## Order-block fields surfaced
Case detail now renders an explicit order block when `linked_order_display_number` exists:
- linked order display number
- optional linked order status (if backbone provides it)
- optional linked order compact cue/summary (if backbone provides it)
- PDF/document availability indicator
- explicit action hint to open order summary/handoff panel

If no linked order exists, order block is not shown.

## Order summary view/action implemented
Added a dedicated **Order summary / handoff** panel reachable from case detail.

Panel is compact and operational:
- order + quote stable identifiers
- customer label
- operational and priority/escalation cues
- optional order status/cue
- PDF availability + document reference if present
- target configuration visibility (production/warehouse/accountant configured vs not configured)

Navigation remains deterministic: back returns to case detail.

## PDF / document actions implemented
Implemented honest, data-driven PDF/document behavior:
- `Send PDF/document ref here` action appears only when `linked_order_pdf_url` is present
- action sends document reference into manager chat (no fake generation)
- when absent, button is hidden and callbacks return explicit “not available” alert if invoked manually

Current SQL backbone query path in this repo does not expose canonical order document URL yet; repository returns `null` placeholders and UI reflects absence honestly.

## Compact share / forward payload
Added compact order payload builder used for local share and handoff:
- order display number
- case display number
- customer label
- priority/escalation
- operational status/waiting cue
- optional order status/cue
- handoff target label (when applicable)
- PDF/document reference or explicit absence note

## Internal handoff actions implemented
Added lightweight handoff actions in order summary panel:
- Send to production
- Send to warehouse
- Send to accountant

Actions are only rendered when corresponding target chat is configured.
No giant workflow engine added.

## Traceability / logging pattern
After successful handoff send, bot writes an internal note using existing note flow:
- target label + target chat id
- linked order number

This preserves operational traceability without introducing new subsystem/tables.

## Recipient configuration / safety
Added minimal explicit config fields:
- `MANAGERBOT_HANDOFF_PRODUCTION_CHAT_ID`
- `MANAGERBOT_HANDOFF_WAREHOUSE_CHAT_ID`
- `MANAGERBOT_HANDOFF_ACCOUNTANT_CHAT_ID`

Safety behavior:
- no hardcoded target chats
- missing target => action hidden in keyboard
- if callback called without config, clear failure alert shown
- no silent send-to-nowhere

## Rendering/navigation updates
- case detail includes operational order block (when applicable)
- case keyboard includes `Order summary / handoff` entry only when linked order exists
- order panel has compact actions and explicit back/home navigation
- single-panel behavior preserved via existing navigation state

## Honest absence handling
ERG4 explicitly handles missing data/config:
- no linked order => no order block/button
- no PDF URL => no PDF send button
- no configured handoff target => no target button and graceful error on direct callback
- no fake success messages for absent data

## Backbone contract gaps discovered
In current standalone repo SQL path, order read includes only `display_number` via `core.orders` join.
Canonical fields for order document URL/path/status/summary are not currently surfaced by this path.
ERG4 keeps these as optional fields and renders absence honestly.

## Migration discipline confirmation
- No migration created.
- No schema changes.
- No local order/handoff table added.

## Intentionally deferred to ERG5+
- richer UI polish for order/handoff wording consistency
- optional retry UX for failed internal handoff deliveries
- any ERP/1C/system-to-system handoff integration
- MB8 group topics bridge
