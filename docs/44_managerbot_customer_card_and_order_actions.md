# 44_managerbot_customer_card_and_order_actions.md

## Purpose

This document defines the V1 contract for two critical ManagerBot work areas:

1. **Customer Card** — the compact manager-facing identity and contact block for the customer behind the active case.
2. **Order Action Block** — the manager-facing operational block for linked orders and downstream actions.

The goal is not to turn ManagerBot into a generic CRM. The goal is to make case handling operationally usable in real business conditions:
- the manager must immediately understand **who the customer is**,
- must have a clean path to **direct contact** when needed,
- and must have practical actions for **order handling / forwarding / PDF / team handoff**.

This document is part of the V1 ergonomics layer and sits on top of the already defined:
- workdesk / hot tasks,
- queues,
- search / filters / archive / priority,
- case detail,
- manager reply flow,
- AI copilot.

---

## 1. Design position

ManagerBot is **case-centered**, not chat-centered.

That means:
- the customer thread is only **one block** of the case,
- the manager must not be forced to treat the whole workflow as a chaotic Telegram conversation,
- operational handling must be built around:
  - identity,
  - status,
  - order,
  - next action,
  - handoff,
  - documentation,
  - communication.

The customer card and order actions exist specifically to stop the case detail from degenerating into “just another chat”.

---

## 2. Scope

This document covers:
- what the manager must see about the customer,
- what direct-contact actions must exist,
- what must be shown when a quote becomes an order,
- how order-related files and handoff actions should work,
- how team forwarding/share actions should be designed in V1.

This document does **not** define:
- ERP / 1C integration protocol,
- warehouse management,
- accounting workflows,
- logistics routing,
- full CRM profile system,
- customer marketing automation.

Those may come later. V1 only defines the operator-side contract needed to work sanely.

---

## 3. Customer Card: role and intent

### 3.1 Why Customer Card exists

The manager needs a compact answer to four questions:

1. **Who is this person/company?**
2. **How do I contact them directly if needed?**
3. **How trustworthy / important / known are they in business terms?**
4. **What context matters before I reply or escalate?**

Without this block the manager is forced to infer identity from thread fragments, which is slow, error-prone, and irritating.

### 3.2 Customer Card is not a full CRM profile

Customer Card is deliberately small.

It should not try to become:
- a giant editable dossier,
- a social profile,
- a data-entry swamp,
- a substitute for future CRM.

The job of the card is operational clarity.

---

## 4. Customer Card: V1 required fields

The following fields are V1-required where available from backbone truth.

### 4.1 Identity block
- customer display name / person label
- company label / buyer organization label
- linked actor id (internal technical identity, manager-visible only when needed)
- customer role label if applicable (retail / wholesale / B2B / repeat)

### 4.2 Telegram contact block
- Telegram username (if present)
- customer-facing Telegram chat binding availability
- technical indication that outbound messaging is possible

### 4.3 Contact block
- phone number if available
- additional contact label if available
- contact availability note if already known

### 4.4 Business context block
- repeat customer marker
- VIP / manual priority marker
- recent order count / order existence signal if cheaply available
- notable operational markers:
  - escalated history,
  - failed delivery history,
  - large order / strategic account marker if manually set later

### 4.5 Risk/context block
- unresolved delivery issue marker
- missing contact details marker
- direct-contact recommended marker if current thread is inefficient

Not all fields must always exist. Missing fields must render cleanly, not as garbage placeholders.

---

## 5. Customer Card: V1 actions

The customer card must support practical actions.

### 5.1 Required actions

#### A. Write directly
A manager action that opens a direct-contact path where architecture allows it.

Purpose:
- leave case-centered thread mode when needed,
- resolve ambiguity faster,
- avoid endless quote-thread ping-pong.

Important:
- this is not a replacement for the case thread,
- this is an explicit exception path for real-life handling.

#### B. Copy contact / username
The manager must be able to copy:
- Telegram username,
- phone number,
- relevant compact customer identifier.

Purpose:
- quick handoff to voice call,
- quick forwarding to colleague,
- quick use in external messenger or phone.

#### C. Open direct-contact summary
If full direct messaging is not yet supported, the manager must still be able to see a compact contact summary block that is easy to use manually.

### 5.2 Optional actions for later
- open external CRM profile
- view full account history
- start voice call integration
- create customer label/tag from ManagerBot

Not required in V1.

---

## 6. Direct-contact policy

### 6.1 Principle

ManagerBot remains the primary workspace.

Direct contact is allowed when it improves resolution.

Examples:
- thread drifts into inefficient back-and-forth,
- customer needs quick clarification,
- order needs urgent voice confirmation,
- delivery/payment confusion is easier to resolve verbally.

### 6.2 What direct contact must not do

Direct contact must not destroy case coherence.

That means:
- the case remains the source of operational truth,
- the manager is still responsible for recording the outcome,
- important results of the direct conversation must be reflected back into:
  - case reply,
  - internal note,
  - status/action change.

Direct contact is a shortcut for communication, not a replacement for case state.

### 6.3 Recommended V1 rule

If a manager resolves something outside the thread, the manager should add either:
- a short internal note, or
- a clarifying customer-visible reply,
so the case does not become opaque to the rest of the team.

---

## 7. Order Action Block: role and intent

### 7.1 Why this block exists

When quote turns into order, the manager must stop thinking only in terms of “conversation”.

At this point the workflow becomes operational:
- production,
- warehouse,
- accountant,
- fulfillment,
- documents,
- handoff.

Therefore case detail must expose an **Order Action Block**, not just a linked order number.

### 7.2 Job of Order Action Block

The block answers:
- is there an order already,
- what order is it,
- what quote/thread led to it,
- what document can I get,
- what can I forward/share right now,
- what downstream handoff can I perform.

---

## 8. Order Action Block: V1 required data

When the case has a linked order, ManagerBot must show:

### 8.1 Order identity
- stable order display number
- linked quote display number
- order creation timestamp
- current commercial/order status if available

### 8.2 Order summary
- customer/company label
- short order summary
- amount / total if available and already in backbone truth
- delivery/payment note if available and cheap to surface

### 8.3 Document availability
- PDF availability indicator
- invoice / commercial document availability indicator if relevant
- compact indication whether the order is “ready to hand off”

The block must remain compact. It is an action surface, not a detailed ERP card.

---

## 9. Order Action Block: V1 required actions

### 9.1 Open order
Open the linked order detail/summary view.

Purpose:
- view operational order summary,
- confirm what exactly was created,
- avoid guessing from thread text.

### 9.2 Get PDF
The manager must be able to obtain the order/quote PDF that is already part of the broader TradeFlow commercial flow.

Purpose:
- share with customer,
- share internally,
- attach manually to accounting/production workflows.

### 9.3 Send PDF to customer
Where architecture supports it, the manager should be able to send the document to the customer through the correct customer-facing bot/channel.

This must use the same discipline as outbound replies:
- correct delivery identity,
- honest delivery result,
- visible result in case detail.

### 9.4 Share / forward internally
The manager must be able to forward a compact order package internally.

At minimum V1 should support one or more of:
- share order summary to team chat,
- forward PDF to internal chat,
- copy compact order summary text.

### 9.5 Handoff actions
The manager must be able to perform explicit downstream handoff actions such as:
- Send to production
- Send to warehouse
- Send to accountant

In V1 these can be lightweight actions that package and forward the relevant information.

They do **not** need to be full workflow engines.

---

## 10. Team handoff model

### 10.1 Why this matters

In real business the manager is often not the final executor.

A typical sequence is:
- manager receives case,
- customer confirms,
- order is created,
- manager forwards it to production / warehouse / accountant.

If ManagerBot cannot support this handoff, the manager falls back to chaotic manual copying.

### 10.2 V1 handoff principle

V1 handoff should be explicit and lightweight.

Each handoff action should package:
- order identifier,
- customer label,
- short order summary,
- linked PDF if available,
- short manager note if needed.

The target may be:
- internal Telegram chat,
- internal responsible user,
- copyable payload for manual forwarding.

### 10.3 What V1 handoff is not

V1 handoff is **not**:
- ERP integration,
- warehouse stock reservation,
- accounting approval engine,
- logistics orchestration.

Those are future layers.

---

## 11. Recommended V1 structure inside Case Detail

When rendered in case detail, the manager workspace should conceptually contain these blocks in this rough order:

1. Case identity / status block
2. Hot indicators / SLA / escalation / priority
3. Customer Card
4. Customer-visible thread
5. Internal notes
6. AI block
7. Order Action Block (if linked order exists)
8. Case actions / handoff actions

This order is intentional.

Reason:
- first understand the case,
- then understand the customer,
- then see communication/history,
- then see order and downstream actions.

Not every case will have an order block yet. Quote-only cases should still render cleanly.

---

## 12. Relationship to search / archive / priority

Customer Card and Order Action Block do not replace the previously defined ergonomics layers.

They complement them:
- **search** helps find the case,
- **filters** reduce working noise,
- **archive** removes completed noise,
- **priority/VIP** ensures the right case rises,
- **customer card** helps decide how to contact,
- **order block** helps execute the business action.

This is why case detail must be treated as a real workspace, not merely a conversation transcript.

---

## 13. Relationship to AI copilot

The AI assistant is useful here, but secondary.

### 13.1 AI may help
AI may help with:
- summarizing the case,
- proposing reply text,
- proposing internal notes,
- highlighting missing information,
- suggesting escalation.

### 13.2 AI must not replace customer/order operational blocks
AI should not be used as a substitute for:
- customer identity visibility,
- contact availability,
- order existence,
- PDF access,
- handoff actions.

Those must remain explicit UI blocks.

Otherwise the interface becomes “ask the AI what to do”, which is lazy and wrong.

---

## 14. V1 acceptance criteria

This area is considered V1-ready when all of the following are true:

### 14.1 Customer Card
- manager can immediately identify the customer/company behind the case,
- manager can see direct-contact options where available,
- manager can copy/use the necessary contact data quickly,
- manager is not forced to infer identity from thread text.

### 14.2 Order Action Block
- manager can immediately see whether a linked order exists,
- manager can open the order summary,
- manager can obtain/share the PDF,
- manager can forward/share the order internally,
- manager can perform lightweight handoff to production / warehouse / accountant.

### 14.3 Operational usability
- case detail does not devolve into a chat-only screen,
- customer contact and order execution are both accessible from the same manager workspace,
- closed/completed cases can still be found later but do not pollute active operational handling.

---

## 15. Explicit non-goals for V1

The following are intentionally **out of scope** for this document’s V1 implementation:
- full CRM profile editing,
- voice call integration inside the bot,
- 1C integration,
- ERP sync,
- warehouse workflow engine,
- accounting approval flow,
- automatic external system posting,
- customer segmentation platform.

These are future expansions.
V1 only defines the manager-side contract required to work efficiently in real business conditions.

---

## 16. Implementation direction for later PR planning

This document should drive one or more ergonomics PR waves after the AI scope is frozen for V1.

Recommended implementation sequence:

1. Customer Card block
2. Direct-contact quick actions
3. Order Action Block
4. PDF/share/forward actions
5. Lightweight handoff actions
6. Optional future external system hooks (deferred)

This sequence keeps V1 grounded in actual operator usefulness instead of jumping prematurely into external-system complexity.

---

## 17. Final principle

ManagerBot must not become:
- a chat dump,
- a toy CRM,
- or a fake ERP.

Its job is simpler and more important:

> give the manager one operational console where they can understand the case, identify the customer, act on the order, and move the business forward with minimal friction.

Customer Card and Order Action Block are core parts of that promise.
