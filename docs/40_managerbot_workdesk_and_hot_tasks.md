# 40_managerbot_workdesk_and_hot_tasks.md

## Purpose

This document defines the **ManagerBot workdesk** model for V1 and the concept of **hot tasks**.

The goal is to make the manager's home screen a real operational workspace rather than a decorative dashboard with counters.

ManagerBot is not a customer chat bot and not a CRM clone inside Telegram. It is an **operator console** inside one Telegram conversation with the bot, backed by DB truth.

This document defines:
- what the manager sees first
- what counts as a hot task
- how hot tasks are grouped and ordered
- how hub counters relate to actionable workload
- how notifications map into workdesk surfaces
- what belongs to V1 and what is intentionally deferred

---

## Core principles

### 1. One manager workspace, not many Telegram chats

ManagerBot runs as a **single internal workspace** inside one Telegram chat with the bot.

The manager does **not** handle work by jumping across separate customer threads.
Instead, the manager works through:
- **Hub / Workdesk**
- **Queue lists**
- **Case detail**
- **Compose flows**
- **AI advisory blocks**

The source of truth remains in the database. Telegram is only the surface.

### 2. The hub must answer "what needs my attention now?"

The workdesk is not there to display beautiful counts.
Its primary job is to answer:
- what is urgent now
- what requires my response now
- what is broken now
- what new business appeared now
- what can wait

If the first screen does not reduce manager uncertainty, it failed.

### 3. Hot tasks are not the same as queues

Queues are structural.
Hot tasks are operational.

Examples:
- `Waiting for me` is a queue
- `3 urgent overdue cases with new customer messages` is a hot-task view

The workdesk must surface **prioritized work**, not just storage categories.

### 4. The workdesk must stay compact

This is Telegram, not a BI cockpit.
The manager must be able to understand the current operational situation within seconds.

The hub must favor:
- concise labels
- clear counts
- top actionable slices
- direct navigation

It must avoid:
- long reports
- giant walls of text
- too many categories at once
- duplicate summaries of the same problem

---

## Workdesk structure

The V1 workdesk is the **Hub** screen shown after successful entry into ManagerBot.

The Hub contains four conceptual layers:

1. **Identity / presence strip**
2. **Hot tasks block**
3. **Core queue summary**
4. **Operational shortcuts**

---

## 1. Identity / presence strip

The top of the Hub should show:
- manager display name
- role (`MANAGER` or `OWNER`)
- current presence state
- quick action to toggle/change presence

Purpose:
- remind the operator of their current work mode
- make presence explicit, not implicit
- make routing/notification behavior understandable

This strip must stay small.

Example shape:
- `Юрий · MANAGER`
- `Presence: online`
- buttons: `Presence`, `Refresh`

---

## 2. Hot tasks block

### Purpose

The hot tasks block is the most important operational area of the Hub.
It must surface what needs immediate attention.

This is not a replacement for queues.
It is a **prioritized entry point** into current work.

### V1 hot-task categories

The following hot-task buckets should exist in V1.

#### A. Needs reply now

Cases where the next meaningful action belongs to the manager and there is recent customer activity.

Typical signals:
- `waiting_state = waiting_for_manager`
- recent inbound customer message
- case not closed
- not archived

This is the core "someone is waiting for us" bucket.

#### B. New business

Freshly created quote cases or newly visible unassigned cases.

Purpose:
- prevent new opportunities from disappearing inside a large queue

Typical signals:
- newly created case
- unassigned
- still active/new

#### C. SLA at risk

Cases that are near breach or overdue.

Typical signals:
- `sla_due_at` near current time
- `sla_due_at` already passed

This bucket may be split visually into:
- `Near breach`
- `Overdue`

If space is limited, it may remain one bucket with badges/counters.

#### D. Urgent / VIP / escalated

Cases that must jump ahead of normal flow.

Typical signals:
- priority = urgent
- manual VIP/high-priority marker
- escalated to owner
- special business handling required

This bucket exists to override plain FIFO behavior.

#### E. Failed delivery / communication issues

Cases where outbound manager communication failed or customer continuity is broken.

Typical signals:
- failed delivery attempt
- unresolved customer contact issue
- case should be revisited manually

This bucket prevents silent delivery failures from dying inside detail screens.

---

## Hot-task bucket design rules

### 1. Buckets must be actionable

Each hot-task bucket must support direct navigation.
Pressing the bucket must open:
- either a filtered queue
- or a compact task list for that bucket

No decorative counters without a path to action.

### 2. Buckets must be deduplicated conceptually

The same case may technically belong to multiple categories.
That is acceptable.
But the UI must avoid confusion.

Example:
- one case may be `urgent`, `waiting_for_manager`, and `overdue`

The hub should present category counts as **work lenses**, not as mutually exclusive truth statements.

### 3. Buckets must stay limited

Do not create 12 hot-task buckets.
V1 should keep the set tight and obvious.

Recommended V1 visible buckets:
- Needs reply now
- New business
- SLA at risk
- Urgent / VIP / escalated
- Failed delivery

That is enough for first-line management.

---

## 3. Core queue summary

Below the hot tasks block, the Hub should still show the canonical queue structure.

Recommended V1 queue entries:
- New / Unassigned
- Assigned to me
- Waiting for me
- Waiting for customer
- Urgent
- Escalated
- Archive / Closed (may be added once archive flow exists)

### Purpose of queue summary

The queue block answers:
- where cases live structurally
- how much work exists per operational lane
- where to drill down when hot-task views are not enough

### Difference between queue summary and hot tasks

Queue summary is stable and structural.
Hot tasks are dynamic and priority-oriented.

Example:
- `Assigned to me = 17`
- `Needs reply now = 4`

That tells the manager that not all assigned work requires immediate action.

---

## 4. Operational shortcuts

The Hub should include a small set of direct actions that reduce friction.

V1 candidates:
- `Refresh`
- `Presence`
- `Search` (once implemented)
- `Open urgent`
- `Open failed delivery`

This area must stay small.
It is not an admin menu.

---

## Hot task ordering policy

Within a hot-task list, cases must be shown in deterministic operational order.

### Recommended order for V1

1. urgent/VIP first
2. overdue before near-breach
3. escalated before non-escalated within same urgency band
4. fresher customer message before stale one where manager response is needed
5. older SLA deadline before later SLA deadline
6. stable display number as a final tie-breaker

This ordering is meant to support action, not historical browsing.

### Important

No accidental DB ordering.
No lexical sorting of business priority values.
No "whatever order came back" behavior.

---

## Notification → workdesk mapping

Notifications must not exist in isolation.
They must map into the workdesk.

### Rule

Every meaningful notification class should correspond to a visible operational landing point.

Examples:
- new customer message notification → `Needs reply now`
- new case notification → `New business`
- failed delivery notification → `Failed delivery`
- escalation notification → `Urgent / VIP / escalated`

This keeps the system coherent:
- notification attracts attention
- workdesk organizes attention
- case detail supports action

Without this mapping, notifications become noise.

---

## Workdesk vs case detail

The workdesk is for **triage and prioritization**.
Case detail is for **actual handling**.

### Workdesk responsibilities

- surface current workload
- show what is hot
- let manager enter the correct work lane
- reduce uncertainty

### Case detail responsibilities

- show full context for one case
- show thread/history
- show status, SLA, priority, escalation
- let manager take actions

The workdesk should not try to replace case detail.
It should only get the manager into the right case fast.

---

## V1 hub layout concept

A compact conceptual layout for V1:

### Header
- manager name / role
- presence state
- refresh

### Hot tasks
- Needs reply now
- New business
- SLA at risk
- Urgent / VIP / escalated
- Failed delivery

### Core queues
- New / Unassigned
- Assigned to me
- Waiting for me
- Waiting for customer
- Urgent
- Escalated

### Shortcuts
- Search (when added)
- Archive / History (when added)

This layout must remain compact enough for phone use.

---

## Empty-state behavior

The workdesk must behave cleanly when there is no urgent workload.

Examples:
- `Needs reply now: 0`
- `Failed delivery: 0`
- `Urgent: 0`

The manager should still see:
- stable queue entry points
- presence strip
- refresh action

No dramatic empty-state theater needed.
Just clean operational calm.

---

## Multi-manager implications

Even in V1, the workdesk must support more than one manager logically.

This does **not** mean a multi-tenant operator architecture.
It simply means:
- one manager sees `Assigned to me`
- owner may see broader cross-team visibility
- notification and hot-task surfacing can differ by role/presence/assignment

The hub should not pretend every manager owns every case.

---

## Relationship with AI copilot

AI does not replace the workdesk.
AI enriches case understanding once a case is opened.

### Workdesk remains rule-driven

The hot tasks block should remain grounded in:
- ops state
- priority
- SLA
- delivery failures
- assignment/presence

### AI may later enhance, but not govern

Possible future uses:
- AI-generated short reason label for why a case is hot
- AI-generated triage hint inside case detail

Not for V1 hub logic:
- AI does not decide queue placement
- AI does not decide hot-task eligibility
- AI does not reorder the operational workdesk autonomously

The workdesk must remain predictable.

---

## What is intentionally out of scope for this document

This document does **not** define in detail:
- search/filter mechanics
- archive/history mechanics
- VIP/manual priority controls
- customer card design
- order action block
- team handoff actions

These belong to follow-up ergonomics documents.

This document only defines the **workdesk/home screen** and **hot-task concept**.

---

## V1 acceptance criteria

The ManagerBot workdesk may be considered implemented correctly when:

1. Hub shows manager identity and presence
2. Hub surfaces explicit hot-task buckets
3. Hot-task buckets are actionable
4. Core queues remain accessible from Hub
5. Counts are useful, not decorative
6. Ordering of hot-task lists is deterministic
7. Notification classes map coherently to workdesk entry points
8. Hub stays compact enough for phone use
9. Workdesk supports triage rather than forcing managers to browse blindly
10. Hub does not attempt to become a full analytics dashboard

---

## Practical design conclusion

For V1, the workdesk should behave like a **dispatcher board**, not a CRM homepage.

Its job is simple:
- show what matters now
- let the manager enter the right work lane
- keep the first screen calm, compact, and actionable

Anything that does not help with those three outcomes should stay out of the Hub.
