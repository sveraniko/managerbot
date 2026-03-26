# 92_pr_plan_managerbot_ergonomics_v1.md

## Purpose

This document defines the **post-MB7 V1 ergonomics wave** for ManagerBot.

At this stage:
- the baseline manager workspace already exists;
- the operational backbone in TradeFlow already exists;
- ManagerBot already supports queue navigation, case detail, claim/take-in-work, reply flow, internal notes, delivery tracking, notifications, SLA cues, escalation, and AI copilot in reader + controlled recommender mode;
- the AI layer is considered **sufficient for V1** and is no longer the main launch bottleneck.

Therefore the next critical focus is not more AI depth and not group topics bridge, but **manager-side operational ergonomics**.

The goal is to turn ManagerBot from a technically functional operator console into a **comfortable, high-throughput daily workdesk** for real managers.

---

## Strategic decision

### Defer MB8

`MB8 — Optional group topics bridge and release hardening` is **deferred**.

Reason:
- group topics are not required for V1 launch;
- the current product bottleneck is not collaboration topology inside Telegram groups, but manager workflow convenience and speed;
- the most valuable next improvements are those that reduce friction in daily manager work.

### Freeze AI scope for V1

AI scope for V1 is considered **good enough** after MB7a/MB7b/MB7c:
- AI reader exists;
- controlled recommender exists;
- policy / guardrails exist;
- bounded context exists;
- no autonomous execution exists.

Further AI work is deferred until real production usage reveals concrete needs.

### New V1 track

The new implementation track is:

**ManagerBot Ergonomics V1**

This track is split into dedicated waves focused on:
- workdesk clarity;
- search/retrieval;
- archive hygiene;
- manual business prioritization;
- customer identity visibility;
- order actions;
- handoff ergonomics;
- release hardening.

---

## Core product principle

ManagerBot is not designed as a set of separate Telegram chats/threads per customer or per quote.

ManagerBot remains a **single internal operator workspace** inside one Telegram chat with the bot.

The manager interacts with:
- one active panel at a time;
- queue lists;
- case detail panels;
- compose modes;
- action blocks.

Cases live in the **database as operational entities**, not as Telegram-native conversation threads.

Therefore ergonomics work must improve the **console model**, not replace it with thread proliferation.

---

## V1 ergonomics goals

After the ergonomics wave, ManagerBot V1 should support the following operator reality well:

1. A manager can instantly see **what needs attention now**, not just queue counts.
2. A manager can quickly find a specific case/order/customer without scrolling forever.
3. Closed and old work does not pollute the active workspace.
4. A manager can manually prioritize an important customer or large order.
5. A manager can understand who the customer is and how to reach them directly when needed.
6. A manager can act on an order operationally, not just read about it.
7. A manager can hand off information to production / accountant / warehouse / team chat without manual copy-paste hell.
8. The bot remains compact, deterministic, and operator-first.

---

## Wave structure

The ergonomics track is split into five waves.

### ERG1 — Workdesk / hot tasks
Focus:
- upgrade Hub from queue-counter screen into a real workdesk;
- add a visible “needs attention now” layer;
- expose urgent operational blocks without forcing the manager to drill through multiple queues.

Primary source doc:
- `40_managerbot_workdesk_and_hot_tasks.md`

### ERG2 — Search / filters / archive / priority
Focus:
- targeted search across active and archived cases;
- practical filters;
- archive/history separation;
- manual priority and VIP handling.

Primary source doc:
- `42_managerbot_search_filters_archive_priority.md`

### ERG3 — Customer card and direct-contact ergonomics
Focus:
- customer identity block;
- direct contact affordances;
- quick visibility into who is behind the case;
- keeping direct communication usable without losing case truth.

Primary source doc:
- `44_managerbot_customer_card_and_order_actions.md`

### ERG4 — Order actions / PDF / share / handoff
Focus:
- order action block;
- PDF access;
- share/forward actions;
- production/accountant/warehouse handoff ergonomics.

Primary source doc:
- `44_managerbot_customer_card_and_order_actions.md`

### ERG5 — Release hardening V1
Focus:
- empty states;
- permission polish;
- navigation cleanup;
- action safety;
- regression cleanup;
- V1 release readiness.

This wave is the final polish and release discipline pass.

---

## Recommended execution order

Canonical order:

1. **ERG1 — Workdesk / hot tasks**
2. **ERG2 — Search / filters / archive / priority**
3. **ERG3 — Customer card and direct-contact ergonomics**
4. **ERG4 — Order actions / PDF / share / handoff**
5. **ERG5 — Release hardening V1**
6. **MB8 — Optional group topics bridge** (only after V1 ergonomics if still desired)

Reasoning:
- ERG1 improves immediate visibility and daily usefulness;
- ERG2 solves retrieval and workspace hygiene;
- ERG3 makes the case screen manager-realistic;
- ERG4 turns orders into actionable operational objects;
- ERG5 hardens the whole surface for release.

---

## Detailed wave definitions

---

## ERG1 — Workdesk / hot tasks

### Goal
Make the home screen a true operational desk.

### Why this wave comes first
Right now the manager can navigate queues, but the bot still behaves more like a queue browser than a daily dispatch console.

Managers need a first screen that answers:
- what is burning now;
- what requires immediate reply;
- what just became an order;
- what failed to deliver;
- what is urgent or escalated.

### Scope
Implement:
- a visible **Hot Tasks** section on Hub;
- explicit urgent buckets such as:
  - needs reply now;
  - new business;
  - SLA at risk;
  - urgent / VIP / escalated;
  - failed delivery;
- compact preview rows for top urgent cases;
- direct open-case actions from those rows;
- improved Hub ordering so high-value/high-risk work is surfaced first.

### Out of scope
- global search;
- archive/history;
- customer card;
- order forwarding;
- broad UI redesign beyond workdesk behavior.

### Exit criteria
ERG1 is done when:
- Hub clearly shows what needs attention now;
- a manager can open the most urgent cases directly from Hub;
- the workdesk no longer behaves like a decorative dashboard.

---

## ERG2 — Search / filters / archive / priority

### Goal
Make the system navigable under load.

### Why this wave is second
Once Hub becomes a real workdesk, the next pain point is retrieval.

As case volume grows, queue browsing alone becomes insufficient.
Managers must be able to:
- find one specific case quickly;
- narrow the active workspace;
- hide old closed noise;
- override business priority when necessary.

### Scope
Implement:
- search entry point from Hub and/or queue screens;
- targeted search by:
  - case display number;
  - order display number;
  - customer label;
  - Telegram username if available;
  - optionally text snippet if justified;
- filter controls for:
  - queue/status;
  - assignment;
  - priority;
  - archive state;
- archive/history separation:
  - active cases vs archived/closed/resolved;
- manual priority controls:
  - normal / high / urgent;
  - VIP/business-important marker if supported by current model.

### Out of scope
- direct contact actions;
- PDF/share/handoff;
- ERP/1C integration;
- AI scope changes.

### Exit criteria
ERG2 is done when:
- a manager can find a specific case/order quickly;
- active workspace is not polluted by closed history;
- manual business priority override is visible and operational.

---

## ERG3 — Customer card and direct-contact ergonomics

### Goal
Make the case screen human-realistic.

### Why this wave matters
A manager does not work only with statuses and threads.
They need to understand:
- who the customer is;
- how to contact them;
- when to continue in-case vs move to direct contact.

### Scope
Implement:
- a **Customer Card** block in case detail;
- visible customer identity fields such as:
  - display name;
  - Telegram username;
  - technical Telegram binding where appropriate;
  - company/customer label;
  - phone/contact fields if present;
- direct-contact affordances such as:
  - open direct Telegram chat if feasible;
  - copy username/handle;
  - copy phone if present;
- compact policy cues in UI that direct contact does not replace case truth.

### Out of scope
- full CRM profile;
- customer segmentation engine;
- 1C integration;
- bulk contact operations.

### Exit criteria
ERG3 is done when:
- the manager can clearly identify who is behind the case;
- direct contact becomes easy when needed;
- the case screen feels like a customer operation screen, not only a thread viewer.

---

## ERG4 — Order actions / PDF / share / handoff

### Goal
Make created orders operationally actionable.

### Why this wave matters
A quote that becomes an order creates real work:
- forwarding to production;
- forwarding to warehouse;
- forwarding to accountant;
- sending PDF;
- sharing the order with the team.

Without this, ManagerBot remains only a communication console.

### Scope
Implement:
- **Order Action Block** in case detail for linked orders;
- view linked order summary;
- retrieve/open PDF if available through current backbone contract;
- share/forward compact order summary;
- send/forward to:
  - team chat;
  - production chat;
  - accountant;
  - warehouse/stock operator;
  depending on what current integration surface supports;
- compact handoff actions that reduce manual copy-paste.

### Out of scope
- direct 1C push;
- ERP integration;
- warehouse workflow engine;
- manufacturing planning system.

### Exit criteria
ERG4 is done when:
- an order is no longer just visible, but actionable;
- a manager can get/order-send/share handoff artifacts quickly;
- remote/home manager workflow becomes realistic.

---

## ERG5 — Release hardening V1

### Goal
Turn the whole ManagerBot V1 into a launchable surface.

### Scope
Implement/finalize:
- navigation cleanup;
- stale-state cleanup;
- empty-state polish;
- permission and safety checks;
- callback/state hardening;
- message/update hygiene;
- regression cleanup across MB4-MB7 and ERG1-ERG4;
- release checklist and smoke scenarios.

### Release-hardening concerns
This wave should explicitly verify:
- no navigation dead ends;
- no unsafe stale compose state;
- no unsafe AI draft reuse across cases;
- no notification spam regression;
- no archive/search/priority collisions;
- no broken handoff/PDF actions;
- no accidental behavior drift for reply/note flows.

### Exit criteria
ERG5 is done when:
- the product feels operationally coherent end-to-end;
- there are no obvious workflow holes for a real manager;
- the V1 release candidate is ready.

---

## UX rules that remain constant across all ERG waves

The following rules remain fixed:

1. **Single-panel discipline**
   - no panel spam;
   - one active working surface.

2. **Clean-chat behavior**
   - edit/update where possible;
   - no junk accumulation.

3. **Deterministic navigation**
   - Back / Home / Refresh must remain safe and predictable.

4. **Operator-first wording**
   - no decorative language;
   - no customer-facing marketing tone.

5. **DB truth first**
   - case/order state comes from operational truth, not from Telegram chat artifacts.

6. **Stable display numbers only**
   - never recompute fake numbering in UI.

7. **Case-centered workflow**
   - the case is the working object;
   - thread is only one block of that object.

---

## Dependencies between ergonomics waves and existing features

### Depends on MB4-MB6
ERG waves assume that the ManagerBot already has:
- Home / Hub;
- queue lists;
- case detail;
- claim/take-in-work;
- notifications;
- SLA visibility;
- escalation;
- reply and notes.

### Uses MB7 AI, but does not depend on more AI work
ERG waves may use the existing AI layer to improve manager convenience, but they do not require deeper AI development.

Examples:
- hot tasks may surface cases already flagged by SLA/escalation, not by new AI logic;
- search/filter/priority does not depend on AI;
- customer card/order actions do not depend on AI.

### Defers MB8
Group topics bridge is intentionally not a dependency for ergonomics.

---

## Testing expectations for ergonomics track

Every ERG wave must include real behavior-level tests.

### ERG1 tests
- hub hot-task ordering;
- hot-task visibility;
- direct case open from hub;
- no panel spam.

### ERG2 tests
- search accuracy for target entities;
- filters combination behavior;
- archive separation;
- manual priority visibility/order effects.

### ERG3 tests
- customer card rendering;
- direct-contact action safety;
- no confusion between direct contact and case thread.

### ERG4 tests
- order block rendering;
- PDF/share/forward action behavior;
- handoff routing behavior;
- safe failure states when artifact/channel unavailable.

### ERG5 tests
- end-to-end regression across all prior waves;
- navigation stability;
- stale-state safety;
- release smoke scripts.

---

## Release philosophy for this track

This ergonomics track should follow the same discipline already established in the project:
- solve the next real operational bottleneck;
- do not overbuild speculative infrastructure;
- do not add optional collaboration layers before core workflow is comfortable;
- do not add AI magic where straightforward manager ergonomics gives more value.

In short:

**First make ManagerBot comfortable and operationally sharp.**
**Only after that consider optional collaboration bridge features such as group topics.**

---

## Final execution recommendation

Recommended next implementation step:

**Start with ERG1 — Workdesk / hot tasks**

Reason:
- highest visible value;
- improves the first screen managers live in;
- creates immediate sense of operational control;
- complements MB6 notifications well;
- does not require new architectural bets.

After ERG1, continue strictly in order:
- ERG2
- ERG3
- ERG4
- ERG5

Only after that reconsider MB8.

---

## Summary

The ManagerBot V1 roadmap is now split into two completed/mostly completed domains and one new active domain:

### Completed enough for V1
- baseline manager workspace;
- communication loop;
- notifications/SLA/escalation;
- AI copilot for reader + controlled recommendation.

### Deferred
- group topics bridge;
- deeper automation;
- ERP/1C integration.

### Active next domain
- **V1 ergonomics**

This document is the canonical PR-order plan for that ergonomics track.
