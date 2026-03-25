# 20_domain_model_manager_cases.md

# ManagerBot Domain Model V1

**Статус:** canonical domain model contract for ManagerBot V1  
**Дата:** 25 March 2026  
**Назначение:** этот документ фиксирует доменные сущности manager-side слоя, их границы, связи и инварианты. Это не SQL-спека и не UI-док. Это модель предметной области, от которой потом строятся Postgres tables, сервисы, read models и бот-панели.

---

## 1. Зачем нужен этот документ

README и architecture уже зафиксировали главное:

- ManagerBot = primary workspace для внутренних операторов;
- V1 опирается на existing `core.quote_cases`;
- source of truth живёт в БД;
- manager operational state не смешивается с commercial lifecycle;
- внешний thread и internal notes не смешиваются;
- роли V1 = только `OWNER` и `MANAGER`;
- V1 assumes single operator org per deployment.

Этот документ отвечает на более приземлённый вопрос:

**какие именно сущности существуют в manager-side домене, что они значат, чем владеют и чего делать нельзя.**

Иначе на этапе кодинга кто-нибудь обязательно решит, что:

- analytics events и есть thread;
- quote status может хранить waiting-state;
- assignment можно держать просто в памяти панели;
- internal note можно писать в тот же поток, что и customer reply.

А потом все будут очень удивляться, почему система ведёт себя как смесь CRM, чата и травмы детства.

---

## 2. Executive summary

Manager-side V1 строится вокруг **existing `quote_case` как primary operational anchor**.

Это означает:

1. **Нет отдельной универсальной сущности `manager_case` в V1.**
2. **Каждый manager-visible case в V1 = один existing `core.quote_cases` record.**
3. **Менеджерская операционка живёт рядом с quote-case**, а не внутри `quote_cases.status`.
4. **Коммуникация с клиентом хранится в отдельном external thread store.**
5. **Внутренняя коммуникация хранится в отдельном internal notes store.**
6. **Assignment, presence, routing и SLA хранятся отдельными manager-side сущностями.**
7. **AI copilot читает manager-side контекст, но не является владельцем case.**

Базовая формула доменной модели V1:

```text
QuoteCase (existing core aggregate)
    + QuoteCaseOpsState
    + QuoteCaseExternalThreadEntry[*]
    + QuoteCaseInternalNote[*]
    + QuoteCaseAssignmentEvent[*]
    + QuoteCaseRoutingDecision[*]
    + ReplyDeliveryAttempt[*]

ManagerActor
    + ManagerPresenceState
```

---

## 3. Доменные границы

### 3.1. Что входит в manager-side domain V1

В manager-side домен входят:

- operational handling quote-case;
- queues;
- assignment/reassignment;
- waiting-state;
- priority;
- escalation;
- manager presence;
- customer-visible communication;
- internal-only notes;
- routing decisions;
- delivery state исходящих сообщений;
- AI-assisted context preparation для менеджера.

### 3.2. Что не входит в manager-side domain V1

Не входят:

- generic universal case platform;
- полноценный multi-tenant operator SaaS layer;
- full-blown omnichannel communication hub;
- autonomous AI service agent;
- Telegram group topics как source of truth;
- redesign customer quote/order lifecycle.

### 3.3. Граница с customer commerce domain

Customer domain отвечает на вопросы:

- кто создал quote;
- откуда он произошёл (`draft`, `project`, `reorder`);
- какие есть revisions;
- какой revision current;
- из какого quote создан order;
- какие есть line items и totals.

Manager domain отвечает на другие вопросы:

- кто сейчас владеет кейсом;
- кто должен ответить;
- кто кого ждёт;
- есть ли новый клиентский сигнал;
- есть ли просрочка по SLA;
- что менеджер написал клиенту;
- что команда написала внутренне;
- почему кейс попал именно в эту очередь.

Эти вопросы нельзя смешивать в одной сущности просто потому, что кому-то лень завести нормальный adjunct model.

---

## 4. Aggregate root V1

## 4.1. `QuoteCase` remains the primary anchor

В V1 **existing `core.quote_cases` остаётся primary aggregate root** для manager-visible work.

Текущая доменная сущность уже содержит важную коммерческую идентичность:

- `id`
- `company_account_id`
- `runtime_mode`
- `status`
- `origin_kind`
- `source_draft_id`
- `created_by_actor_id`
- `current_revision_number`
- timestamps

### Почему это важно

Потому что всё manager-side handling в V1 должно быть прикреплено к уже существующей коммерческой сущности.

Не надо в первом же PR создавать второй мир, где:

- один `quote_case` живёт в commerce core;
- второй “manager case” живёт рядом и якобы описывает то же самое;
- синхронизация между ними становится новой религией проекта.

### 4.2. What `QuoteCase` does **not** own in V1

`QuoteCase` **не владеет напрямую** следующими manager-side concept'ами:

- active assignee;
- waiting-state;
- queue placement;
- SLA due;
- internal notes;
- external thread entries;
- routing decisions;
- reply delivery attempts;
- manager presence.

Они принадлежат manager-side adjunct entities.

---

## 5. Identity model

## 5.1. Internal identity

Canonical internal identity case в V1:

- `quote_case_id` (`UUID`)

Во всех manager-side сущностях именно он является primary foreign reference.

### 5.2. Public/display identity

Для человека в интерфейсе нужен стабильный публичный номер.

Поэтому доменная модель V1 требует:

- persistent `display_number` или `public_number` для `quote_case`
- persistent `display_number` или `public_number` для `order`

Это отдельная доменная потребность, а не косметика UI.

Почему:

- менеджер не должен видеть “Quote #5”, который завтра станет “Quote #6”, потому что кто-то отсортировал список иначе;
- ссылки в обсуждении, инструкции и скриншоты должны быть стабильны;
- клиентская и менеджерская поверхности должны ссылаться на один и тот же узнаваемый номер.

### 5.3. Conversation identity

В V1 отдельная сущность `conversation` не вводится.

Manager-visible conversation identity для quote-case:

- `conversation_id = quote_case_id`

То есть:

- для thread store conversation anchored by `quote_case_id`;
- для AI `ManagerAssistantContext.conversation_id` может совпадать с `quote_case_id`;
- для panel navigation case detail anchored by `quote_case_id`.

Это достаточно для V1 и не плодит лишние сущности без практической пользы.

---

## 6. Core manager-side entities

Ниже перечислены canonical domain entities V1.

Важно: названия в этом документе фиксируют **доменную модель**. В `60_data_model_postgres_managerbot.md` можно будет уточнить точные table names, индексы и физические колонки, но смысл сущностей менять уже нельзя.

---

## 6.1. `QuoteCaseOpsState`

### Смысл

Это **текущая operational summary-сущность** по одному `quote_case`.

Она отвечает на вопрос:

**в каком менеджерском состоянии сейчас находится кейс и кто им владеет.**

Это не event log и не audit trail.
Это current snapshot.

### Один или много?

- Ровно **один active ops-state** на один `quote_case`.

### Что хранит концептуально

Обязательные концепты:

- `quote_case_id`
- `assigned_manager_actor_id` (nullable)
- `operational_status`
- `waiting_state`
- `priority`
- `human_requested`
- `escalation_level`
- `sla_due_at` (nullable)
- `last_customer_message_at` (nullable)
- `last_manager_message_at` (nullable)
- `last_routing_reason` (nullable)
- `last_assignment_at` (nullable)
- `last_state_changed_at`
- `last_seen_in_queue_at` / optional operational telemetry
- timestamps

### Чего здесь быть не должно

Нельзя хранить здесь:

- полный thread;
- internal notes body;
- delivery attempt payloads;
- AI prompts/results;
- revision lines/orders payload;
- Telegram message bodies.

`QuoteCaseOpsState` должен быть компактным и пригодным для queue queries.

### Главный инвариант

`QuoteCaseOpsState` **никогда не подменяет** `quote_cases.status`.

---

## 6.2. `QuoteCaseExternalThreadEntry`

### Смысл

Это единица **customer-visible коммуникации** по кейсу.

Она покрывает:

- inbound customer message;
- outbound manager reply;
- safe system acknowledgment;
- optional system-generated operational notices, если они реально должны быть видны клиенту.

### Почему это отдельная сущность

Потому что current сборка thread из analytics events для manager-side уже недостаточна.

Нужны:

- строгая история;
- направление сообщения;
- роль автора;
- delivery state;
- source marker;
- гарантированная реконструкция timeline.

### Один или много?

- Один `quote_case` -> много external thread entries.

### Концептуальные поля

- `id`
- `quote_case_id`
- `entry_kind`
- `direction` (`inbound` / `outbound`)
- `author_actor_id` (nullable for system)
- `author_role` (`customer`, `manager`, `owner`, `system`)
- `body_text`
- `body_format` / plain-text-first
- `visible_to_customer = true`
- `customer_message_kind` / `manager_message_kind` / optional semantic marker
- `telegram_chat_id` / nullable transport metadata
- `telegram_message_id` / nullable transport metadata
- `sent_at` / `occurred_at`
- `created_at`

### Допустимые `entry_kind` на уровне доменной идеи

Примеры:

- `customer_message`
- `customer_revision_request`
- `customer_alternative_request`
- `manager_reply`
- `system_acknowledgement`
- `system_notice`

Финальный enum фиксируется в `25_case_statuses_and_routing.md` и `60_data_model_postgres_managerbot.md`.

### Инварианты

- entry в external thread **всегда** customer-visible по смыслу;
- internal note никогда не хранится как external thread entry;
- analytics event может быть сгенерирован из entry, но entry не восстанавливается из analytics как source of truth.

---

## 6.3. `QuoteCaseInternalNote`

### Смысл

Это единица **внутренней коммуникации** команды по кейсу.

Она отвечает на вопрос:

- что менеджер хотел зафиксировать для команды;
- что owner оставил как внутреннее указание;
- почему кейс был эскалирован;
- какие контекстные детали нельзя показывать клиенту.

### Один или много?

- Один `quote_case` -> много internal notes.

### Концептуальные поля

- `id`
- `quote_case_id`
- `author_actor_id`
- `author_role`
- `body_text`
- `note_kind` (free/internal/escalation/handoff/context)
- `visibility_scope` = internal-only
- `created_at`
- `edited_at` (nullable)

### Инварианты

- internal note никогда не попадает в customer-visible thread;
- internal note не влияет напрямую на `quote_cases.status`;
- internal note может влиять на routing/assignment только через явное действие или policy, а не “магически”.

---

## 6.4. `QuoteCaseAssignmentEvent`

### Смысл

Это append-only история присвоения ответственности за кейс.

Она нужна, потому что current assignee в `QuoteCaseOpsState` показывает настоящее, но не показывает:

- кто владел кейсом до этого;
- кто передал кейс;
- почему он был переприсвоен;
- был ли self-claim, owner override, auto-unassign или escalation handoff.

### Один или много?

- Один `quote_case` -> много assignment events.

### Концептуальные поля

- `id`
- `quote_case_id`
- `event_kind`
- `from_actor_id` (nullable)
- `to_actor_id` (nullable)
- `changed_by_actor_id`
- `reason_code`
- `reason_text` (nullable)
- `created_at`

### Типовые event kinds

- `claimed`
- `assigned`
- `reassigned`
- `released`
- `owner_override`
- `auto_unassigned`
- `escalated_to_owner`

### Инварианты

- latest effective assignment должен совпадать с `QuoteCaseOpsState.assigned_manager_actor_id`;
- assignment history append-only;
- нельзя терять историю handoff'ов.

---

## 6.5. `ManagerPresenceState`

### Смысл

Это текущая доступность внутреннего оператора для маршрутизации и очередей.

### Кто имеет presence

Только internal actors с ролями:

- `MANAGER`
- `OWNER`

### Один или много?

- Один manager actor -> один current presence state.

### Концептуальные поля

- `actor_id`
- `presence_status`
- `is_accepting_new_cases`
- `max_active_cases` (nullable or optional)
- `last_changed_at`
- `status_note` (nullable)
- transport availability hints / optional
- timestamps

### Типовые presence states

На уровне доменной идеи:

- `online`
- `busy`
- `away`
- `offline`

Финальные enum-значения фиксируются позже, но модель presence как отдельной сущности уже обязательна.

### Инварианты

- presence не должен жить только в памяти Telegram session;
- routing logic должен читать persistent presence state;
- offline manager не должен оставаться default target для новых кейсов просто потому, что так вышло исторически.

---

## 6.6. `QuoteCaseRoutingDecision`

### Смысл

Это зафиксированное решение маршрутизации, принятое системой или человеком.

Нужно, чтобы было видно:

- почему кейс попал в конкретную очередь;
- почему был assigned конкретному менеджеру;
- почему сработал fallback;
- почему был включён safe auto-ack;
- почему кейс ушёл на owner.

### Один или много?

- Один `quote_case` -> много routing decisions.

### Концептуальные поля

- `id`
- `quote_case_id`
- `decision_kind`
- `decided_by_actor_id` (nullable for system)
- `decider_type` (`system` / `manager` / `owner`)
- `reason_code`
- `reason_text` (nullable)
- `metadata` / structured payload
- `created_at`

### Зачем это не просто analytics

Потому что routing decision — это operational record, от которого зависит обработка кейса, queue placement и иногда SLA.

Analytics может получить копию события.
Но manager domain должен хранить routing decision как first-class entity.

---

## 6.7. `ReplyDeliveryAttempt`

### Смысл

Это попытка доставки **outbound customer-visible message** из ManagerBot в customer surface.

Нужна, потому что “мы сохранили reply в базе” и “клиент реально увидел reply” — это не одно и то же. Удивительно, знаю.

### Один или много?

- Один outbound external thread entry -> ноль или много delivery attempts.

### Концептуальные поля

- `id`
- `thread_entry_id`
- `quote_case_id`
- `transport_kind` (`telegram_bot_message` initially)
- `attempt_number`
- `delivery_state`
- `failure_code` (nullable)
- `failure_text` (nullable)
- `provider_message_id` / nullable
- `attempted_at`
- `completed_at` (nullable)

### Инварианты

- входящее customer message не требует delivery attempts;
- только outbound external entries могут иметь delivery attempts;
- failure доставки не удаляет сам thread entry;
- customer-visible thread и delivery state — связанные, но не одна и та же сущность.

---

## 7. Linked domain entities from existing core

Manager-side V1 не существует в вакууме. Он должен уметь открывать и использовать связанные коммерческие сущности.

## 7.1. `QuoteRevision`

Связь:

- один `QuoteCase` -> много `QuoteRevision`
- `QuoteCase.current_revision_number` указывает на текущий revision

Менеджерский смысл:

- понимать, что именно было предложено клиенту;
- видеть, был ли ответ менеджера выражен через новую revision;
- различать customer request vs manager-issued revision.

Но `QuoteRevision` **не заменяет external thread**.
Revision — это коммерческая версия предложения, а не сообщение в чате.

## 7.2. `Order`

Связь:

- один `Order` ссылается на `source_quote_case_id`
- у одного `QuoteCase` может быть ноль или много orders по историческим причинам проекта

Менеджерский смысл:

- видеть, закрыт ли кейс конверсией в order;
- открывать order detail из case detail;
- использовать order creation как один из operational closure signals.

Но order creation сам по себе не отменяет необходимость нормальной операционки вокруг кейса.

## 7.3. `ProcurementDraft`

Связь:

- `QuoteCase.source_draft_id` может указывать на draft

Менеджерский смысл:

- понять источник коммерческого кейса;
- видеть исходную корзину/подбор;
- быстро возвращаться к customer intent.

## 7.4. `Project` / `Object`

Связь косвенная, через draft lines / order context / project-aware procurement.

Менеджерский смысл:

- понимать, относится ли кейс к конкретному объекту или проекту;
- учитывать это при коммуникации, приоритизации и handoff.

## 7.5. Documents

Quote PDFs, order docs и сопутствующие документы являются linked artifacts.

Они не являются частью manager operational state, но должны быть доступны из manager case detail.

---

## 8. Canonical relationships

Ниже доменная схема отношений в V1.

```text
QuoteCase (1)
  ├─ QuoteRevision (many)
  ├─ Order (0..many)
  ├─ QuoteCaseOpsState (1)
  ├─ QuoteCaseExternalThreadEntry (many)
  ├─ QuoteCaseInternalNote (many)
  ├─ QuoteCaseAssignmentEvent (many)
  ├─ QuoteCaseRoutingDecision (many)
  └─ Linked artifacts / documents / project context

QuoteCaseExternalThreadEntry (1 outbound entry)
  └─ ReplyDeliveryAttempt (0..many)

Manager Actor (1)
  └─ ManagerPresenceState (1)
```

---

## 9. Domain invariants

Это самые важные правила модели. Их надо соблюдать и в сервисах, и в SQL, и в UI flows.

## 9.1. `QuoteCase` remains the operational anchor in V1

Нельзя создавать параллельную canonical identity типа `manager_case_id` и потом пытаться синхронизировать её с `quote_case_id`.

## 9.2. Commercial status and operational status are separate

- `quote_cases.status` остаётся коммерческим;
- `QuoteCaseOpsState.operational_status` остаётся менеджерским.

Смешивать их нельзя.

## 9.3. External thread and internal notes are separate domains

- customer-visible entry != internal note;
- internal note никогда не должен accidentally стать customer reply;
- UI и persistence обязаны поддерживать это разделение.

## 9.4. One current ops-state per case

На один active `quote_case` должен существовать один current `QuoteCaseOpsState`.

## 9.5. Assignment snapshot and assignment history must agree

- current assignee живёт в `QuoteCaseOpsState`;
- история присвоений живёт в `QuoteCaseAssignmentEvent`;
- latest effective event должен быть согласован с snapshot state.

## 9.6. Presence is persistent

Presence менеджера не может зависеть только от того, открыт ли у него Telegram прямо сейчас.

## 9.7. Analytics is not source of truth for communication

Analytics может получать события из manager domain, но не восстанавливать его.

## 9.8. Delivery state is explicit

Outbound reply не считается “доставленным” просто потому, что запись появилась в базе.

## 9.9. AI never becomes the owner of case

AI может:

- summarise;
- suggest;
- flag risk;
- identify missing fields.

AI не может:

- стать assignee;
- быть author of record for manager decisions;
- silently own SLA.

---

## 10. Domain language for V1

Чтобы дальше не плодить синонимы, фиксируем канонические термины.

### `case`
В V1 это quote-case как manager-visible workload unit.

### `commercial status`
Состояние quote как коммерческого объекта.

### `operational status`
Состояние кейса как workload unit для команды.

### `waiting state`
Кто сейчас должен сделать следующий ход: команда или клиент.

### `assignee`
Текущий ответственный внутренний оператор.

### `external thread`
Customer-visible communication timeline.

### `internal note`
Internal-only запись по кейсу.

### `routing decision`
Явное решение, почему кейс попал в ту или иную operational lane.

### `delivery attempt`
Попытка доставить outbound customer-visible сообщение.

### `presence`
Current availability менеджера для маршрутизации и новых кейсов.

---

## 11. Read model implications

Хотя этот документ не про UI, доменная модель уже диктует read models.

Из неё следуют минимум такие read views:

### 11.1. Queue item view

Собирается из:

- `QuoteCase`
- `QuoteCaseOpsState`
- latest external inbound/outbound markers
- current revision summary
- linked order existence

Нужен для:

- inbox;
- assigned/unassigned queues;
- urgent/SLA queues.

### 11.2. Case detail view

Собирается из:

- `QuoteCase`
- revisions
- linked orders
- external thread
- internal notes
- assignment history
- routing decisions
- delivery state
- linked artifacts

### 11.3. Manager workload view

Собирается из:

- `ManagerPresenceState`
- current assignments from `QuoteCaseOpsState`
- SLA and overdue markers

Эти read models не обязаны совпадать 1:1 с таблицами. Но они обязаны опираться на canonical entities выше.

---

## 12. AI seam implications for domain model

В текущем коде уже существует `ManagerAssistantContext` со следующими полями:

- `manager_id`
- `conversation_id`
- `tenant_id`
- `case_summary`
- `metadata`

Domain model V1 задаёт для него практический смысл:

- `manager_id` = actor id текущего внутреннего оператора;
- `conversation_id` = `quote_case_id`;
- `tenant_id` = deployment-level operator context seam, без полноценной multi-tenant семантики в V1;
- `case_summary` = derived summary из `QuoteCase` + `QuoteCaseOpsState` + latest thread/revision context;
- `metadata` = structured manager-side adjunct data.

То есть AI читает доменную модель, а не выдумывает свою.

---

## 13. Out of scope for this document

Здесь специально **не фиксируются окончательно**:

- точные SQL table names;
- конкретные column types;
- индексы;
- exact enums and transitions;
- panel layouts;
- delivery retry policy;
- test matrix.

Это будет раскрыто в следующих документах:

- `25_case_statuses_and_routing.md`
- `30_managerbot_panels_and_navigation.md`
- `35_manager_reply_flow.md`
- `40_presence_sla_and_assignment.md`
- `60_data_model_postgres_managerbot.md`
- `75_testing_strategy_managerbot.md`

Но всё это уже обязано уважать модель из текущего файла.

---

## 14. Concrete V1 decisions captured by this model

Для снятия двусмысленности ещё раз фиксируем итоговые решения:

1. V1 uses only `OWNER` and `MANAGER`.
2. V1 assumes single operator org per deployment.
3. `QuoteCase` is the primary manager-visible case anchor.
4. No generic `manager_case` entity in V1.
5. `QuoteCaseOpsState` stores current operational snapshot.
6. `QuoteCaseExternalThreadEntry` stores customer-visible communication.
7. `QuoteCaseInternalNote` stores internal-only communication.
8. `QuoteCaseAssignmentEvent` stores assignment history.
9. `ManagerPresenceState` stores current operator availability.
10. `QuoteCaseRoutingDecision` stores explicit routing rationale.
11. `ReplyDeliveryAttempt` stores outbound delivery execution state.
12. Analytics is downstream, not source of truth.
13. AI is a copilot reader of the domain, not a case owner.

---

## 15. What this unlocks next

После фиксации этой domain model можно без архитектурного вранья писать:

- `25_case_statuses_and_routing.md`
- `30_managerbot_panels_and_navigation.md`
- `35_manager_reply_flow.md`
- `60_data_model_postgres_managerbot.md`

И уже потом делать PR wave:

- thread foundation;
- ops-state + queues;
- ManagerBot bootstrap;
- reply delivery;
- AI copilot.

Без этого документа кодинг manager-side быстро скатывается в “ну давайте временно вот сюда положим ещё одно поле”, а потом временное живёт дольше империй.

