# 42_managerbot_search_filters_archive_priority.md

## Purpose

This document defines the **search, filters, archive, and manual priority model** for ManagerBot V1.

Its goal is practical, not decorative:

- let a manager quickly find the needed case/order/customer;
- keep active work queues clean;
- move stale/closed work out of the primary work surface;
- allow manual business priority when operational reality matters more than chronological fairness.

This document extends:

- `40_managerbot_workdesk_and_hot_tasks.md`
- `30_managerbot_panels_and_navigation.md`
- `25_case_statuses_and_routing.md`
- `20_domain_model_manager_cases.md`

It is part of the **V1 ergonomics layer**.

---

## 1. Core product principle

ManagerBot is **not** a chat inbox with accidental scrolling.
It is a **work console**.

Therefore:

- queues are for **flow handling**;
- hot tasks are for **what needs attention now**;
- search is for **targeted retrieval**;
- archive is for **getting history out of the active work surface**;
- manual priority is for **business override** when the standard queue order is not enough.

The system must support both:

1. **flow navigation** — "show me what to work on next";
2. **targeted lookup** — "find that exact case/order/customer now".

A manager must not be forced to scroll through queue pages to find a specific case.

---

## 2. Search model

### 2.1 Search purpose

Search exists for **direct retrieval**, not as a substitute for queueing.

A manager should use search when they already know or partially know what they are looking for.

Examples:

- specific quote case;
- specific order;
- known customer;
- known Telegram username;
- known display number;
- specific active/escalated/VIP case.

### 2.2 Search entry points

V1 should support search from:

1. **Hub / Workdesk**
2. **Queue list screen**
3. optionally **Case detail back-navigation context** if returning to a search result list

Search must not require entering a deep submenu maze.

### 2.3 Search scope

V1 search should support the following lookup types:

#### A. By quote case display number
Examples:

- `Q-152`
- `152`
- `quote 152`

#### B. By order display number
Examples:

- `O-48`
- `48`
- `order 48`

#### C. By customer label
Examples:

- customer/company display label
- stored customer name if available

#### D. By Telegram identity
Examples:

- `@username`
- Telegram user id if shown/stored
- chat id only if explicitly available to internal users

#### E. By case text hint (optional V1-lite)
Only narrow and pragmatic.

Examples:

- one or two meaningful words from the customer thread
- product/order wording if already indexed or cheaply queryable

This should remain limited in V1.
Do not turn ManagerBot search into a second Meilisearch project.

### 2.4 Search output

Search results must render as a **compact result list**, not as giant full-detail cards.

Each result should show at minimum:

- case display number;
- linked order display number if present;
- customer/company label;
- operational status;
- waiting state;
- manual priority/VIP badge if present;
- archive/closed marker if relevant.

A manager taps the result to open the case detail screen.

### 2.5 Search behavior rules

- Search results must be deterministic.
- Exact identifier matches should rank first.
- Active/open cases should rank above archived/closed cases when relevance is otherwise similar.
- VIP / manually raised priority may influence ranking for ambiguous searches.
- Search must not silently exclude archived cases unless the manager explicitly uses the active-only filter.

---

## 3. Filters model

### 3.1 Filter purpose

Filters help refine a queue or search result set.
They are not a substitute for search.

### 3.2 V1 filter dimensions

ManagerBot V1 should support the following practical filters:

#### A. Lifecycle / visibility filters
- Active
- Closed / Resolved
- Archived
- All

#### B. Ownership filters
- Assigned to me
- Unassigned
- Assigned to other
- Any

#### C. Waiting-side filters
- Waiting for manager
- Waiting for customer
- Any

#### D. Priority filters
- Normal
- High
- Urgent
- VIP / business priority
- Any

#### E. Escalation filters
- Escalated
- Not escalated
- Any

#### F. Delivery issue filters
- Failed delivery
- No failed delivery
- Any

#### G. SLA filters
- Healthy
- Near breach
- Overdue
- Any

### 3.3 Filter UX rules

Filters must be:

- quick to apply;
- reversible;
- visible in current state;
- resettable in one action.

Manager should always understand:

- whether filters are active;
- which filters are active;
- how to clear them.

### 3.4 Saved filters

Saved/custom persistent filter presets are **out of scope for V1**.

V1 only needs:

- fast current filters;
- clear current filter state;
- one-tap reset.

---

## 4. Archive model

### 4.1 Why archive exists

Active work and historical work must not live in the same operational surface.

Without archive separation, queues become garbage heaps:

- old resolved cases pollute active screens;
- managers waste attention;
- search becomes noisy;
- hot tasks become less meaningful.

### 4.2 Archive principle

Archive is not deletion.
Archive is **operational removal from the primary work surface**.

Archived cases must still remain:

- searchable;
- readable;
- linkable;
- available for audit/history;
- available for customer/order context lookup.

### 4.3 What belongs in archive

A case should leave the primary active work surface when it is operationally done.

Typical candidates:

- closed case;
- resolved case with no active follow-up;
- completed order flow with no open action;
- stale finished communication.

### 4.4 What must stay out of archive

A case must **not** be archived if it still has meaningful pending work, such as:

- waiting for manager;
- failed delivery unresolved;
- escalated active issue;
- VIP/business-critical follow-up pending;
- unresolved operational dependency.

### 4.5 Archive access

Archive should be accessible through:

- a dedicated archive/history filter;
- search results;
- linked references from customer/order context.

Archive should **not** sit mixed into the main active queues by default.

### 4.6 Reopen behavior

If an archived closed/resolved case becomes active again because of legitimate new customer activity or explicit manager action:

- it should re-enter the active operational surface;
- archive marker/history must remain auditable;
- reopen behavior must follow canonical status rules from `25_case_statuses_and_routing.md`.

---

## 5. Manual priority and VIP model

### 5.1 Why manual priority is required

Chronology is not enough.
Business reality is uneven.

Examples:

- large order;
- strategic customer;
- recurring customer;
- production-sensitive order;
- owner-escalated case;
- urgent post-payment handling.

A manager must be able to explicitly raise a case in importance.

### 5.2 Priority layers

ManagerBot V1 should distinguish between:

#### A. Operational priority
Canonical queue-driving urgency, such as:

- normal
- high
- urgent

#### B. Business/VIP emphasis
A manual overlay that marks the case/customer as commercially important.

Examples:

- VIP
- key customer
- large order
- priority partner

This does **not** need a giant CRM taxonomy in V1.
It only needs to support the fact that some customers/cases must surface earlier.

### 5.3 Manual priority actions in V1

A manager (or owner) should be able to:

- raise priority;
- lower priority;
- mark a case/customer as VIP/business-priority;
- remove VIP/business-priority flag;
- optionally store a short reason.

### 5.4 Rendering rules

Manual priority/VIP state should be visible in:

- hot tasks;
- queue rows;
- case detail;
- search results.

It must be compact and obvious, not hidden in metadata.

### 5.5 Ordering impact

Manual priority must influence ordering in:

- hot task lists;
- queue lists;
- ambiguous search ranking where useful.

It must not break deterministic ordering.

The guiding rule:

- urgency first;
- then business-critical manual priority/VIP;
- then SLA/operational pressure;
- then time-based tie-breakers.

Exact queue ordering remains defined in queue/workdesk docs and implementation.

### 5.6 Abuse prevention

V1 does not need a bureaucratic permission system, but it should avoid silent chaos.

At minimum:

- priority changes should be explicit;
- current priority state should be visible;
- internal audit/history should remain possible through existing operational history/logs where available.

---

## 6. Search vs filters vs archive vs hot tasks

These concepts must stay distinct.

### Search
Use when manager knows what they need.

### Filters
Use when manager wants to narrow a visible list.

### Archive
Keeps finished work out of active operational space.

### Hot tasks
Show what deserves attention now.

A manager should not be forced to misuse one concept because another one is missing.

Example of correct usage:

- "What should I handle now?" → Hot tasks / Hub
- "Show only my urgent active cases" → Queue + filters
- "Find order 184" → Search
- "Check old resolved issue for this customer" → Search or Archive filter

---

## 7. Interaction with AI copilot

AI should help understand cases.
It must **not** own search/filter/archive/priority logic.

### Allowed AI assistance
- summarize found case;
- explain why a case looks risky;
- help draft message for a VIP/escalated case.

### Not allowed as primary control logic
- AI deciding what counts as archive by itself;
- AI silently changing priority;
- AI replacing deterministic filters/search;
- AI replacing explicit manager choice for VIP/business priority.

Search/filter/archive/priority must remain deterministic product features.

---

## 8. V1 implementation expectations

The following are considered V1-level expected capabilities:

### Must-have
- case search by display number;
- order search by display number;
- customer/Telegram-based lookup at practical level;
- filters for active/archived, ownership, waiting side, escalation, priority;
- archive separation from active work surface;
- manual priority / VIP marker;
- visible filter state and reset action.

### Good but still optional for first release wave
- fuzzy text search inside thread;
- saved filters;
- advanced combinations with persistent presets;
- large CRM-style tagging taxonomy.

---

## 9. UX acceptance criteria for V1

ManagerBot V1 passes this area when:

1. A manager can find a known case quickly without scrolling queues.
2. Closed/old work does not pollute the active workspace.
3. A manager can manually raise a case/customer in business importance.
4. Active filter state is obvious and reversible.
5. Search results and queue rows clearly show enough context to choose the correct case.
6. Archive remains accessible without cluttering normal work.
7. Search/filter/archive/priority behavior is deterministic and understandable.

---

## 10. Out of scope for this document

This document does not define:

- customer card details;
- direct contact actions;
- order action block;
- PDF/share/forward workflows;
- 1C/ERP handoff;
- group topics bridge.

These belong to subsequent ergonomics documents.

---

## 11. Summary

ManagerBot V1 must not rely on raw scrolling and memory.

It needs a pragmatic operational retrieval layer:

- **Search** to find the exact case;
- **Filters** to refine active work;
- **Archive** to keep dead work out of the main surface;
- **Manual priority/VIP** to reflect business reality.

Without this, the manager console will look functional in demos and become annoying in real use.
