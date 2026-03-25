# 10_architecture_managerbot.md

# ManagerBot Architecture V1

**Статус:** canonical architecture contract for ManagerBot V1  
**Дата:** 25 March 2026  
**Назначение:** этот документ фиксирует техническую архитектуру manager-side контура поверх TradeFlow, его место в текущей кодовой базе, жёсткие решения для V1 и границы будущего расширения.

---

## 1. Зачем нужен этот документ

README по ManagerBot фиксирует продуктовую доктрину.
Этот документ отвечает на другой вопрос:

**Как именно ManagerBot должен быть встроен в текущий TradeFlow так, чтобы V1 можно было быстро реализовать, а V2 потом не пришлось собирать из обломков?**

Документ нужен, чтобы заранее зафиксировать:

- где проходит граница между customer-side и manager-side;
- что является source of truth;
- какие сущности уже можно использовать из текущего ядра;
- какие manager-side сущности должны жить рядом, а не внутри customer shell;
- где AI действительно подключается, а где он пока только seam;
- как избежать ложного старта в сторону giant case engine, topic-first архитектуры и хаоса в state.

Этот файл является **архитектурным контрактом для разработки**, а не общим рассуждением.
Если later PR противоречит этому документу, значит PR нужно править, а не документ задним числом подгонять под случайный код.

---

## 2. Executive summary

ManagerBot V1 строится как **отдельный manager-side operational surface** внутри того же TradeFlow codebase.

Ключевые решения V1:

1. **ManagerBot = отдельный Telegram surface**, а не ещё один hub внутри customer shell.
2. **Источник истины = PostgreSQL domain data**, а не Telegram group/topics и не analytics ledger.
3. **V1 опирается на existing `core.quote_cases`**, а не на новую универсальную `manager_cases` сущность.
4. **Manager operational state живёт рядом с quote lifecycle, но не смешивается с ним.**
5. **Роли V1 = только `OWNER` и `MANAGER`.**
6. **V1 assumes single operator org per deployment.**
7. **Manager session state должен быть отдельным от `ShellSessionState`.**
8. **AI в V1 = copilot seam, не autonomous front.**
9. **Group topics = optional secondary bridge, не primary workflow.**

Это означает простую архитектурную формулу:

```text
Customer TradeFlow Bot
        |
        v
TradeFlow Domain / PostgreSQL
        |
        +--> ManagerBot (primary manager workspace)
        |
        +--> AI Copilot Seam (manager assist only)
        |
        +--> Optional Group Topics Bridge (secondary)
```

---

## 3. Жёсткие архитектурные решения V1

### 3.1. Не строить generic case engine в первом шаге

В V1 primary operational object для менеджера = existing `quote_case`.

То есть в первом этапе:

- менеджер работает вокруг `core.quote_cases`;
- customer-side обращения по quote-case становятся manager-visible workload;
- operational routing, assignment, waiting-state, SLA и notes добавляются **рядом**, а не вместо текущего коммерческого ядра.

Почему так:

- `quote_cases` уже существуют в домене;
- вокруг них уже есть lifecycle, revisions, orders, documents и customer UI;
- попытка с первого PR построить новый абстрактный `manager_case` создаст дублирование и спровоцирует расхождение между business truth и operational truth.

### 3.2. Не смешивать commercial status и manager operational status

`quote_cases.status` остаётся частью коммерческого lifecycle.

Менеджерские статусы должны жить отдельно.

Нельзя делать так, чтобы в `quote_case_status` внезапно появились:

- `waiting_customer`
- `assigned`
- `urgent`
- `escalated`

Это не quote lifecycle, это operational handling state.

Правильная модель:

- **commercial status** отвечает на вопрос: что происходит с quote как коммерческим объектом;
- **manager ops state** отвечает на вопрос: кто сейчас владеет кейсом, кто ждёт кого, что горит по SLA и нужен ли человек.

### 3.3. Не использовать analytics events как primary thread store

Текущий customer-side quote message path частично опирается на analytics events.
Для V1 это уже недостаточно.

Manager architecture требует отдельного persistent thread layer, потому что нужны:

- внешние сообщения клиенту;
- сообщения от клиента;
- delivery state;
- manager replies;
- internal notes;
- строгая сортировка timeline;
- отсутствие эвристик при сборке истории.

Analytics events остаются полезными для:

- метрик;
- audit/event feed;
- funnel analytics;
- reporting.

Но analytics **не являются chat store**.

### 3.4. Отдельный manager session state обязателен

Нельзя расширять текущий `app.bot.contracts.ShellSessionState` так, чтобы туда допихнуть ещё полноценную manager-side операционку.

Сейчас `ShellSessionState` уже включает:

- customer hubs;
- search context;
- draft/quote/order/project state;
- ownerbot state;
- assistant state;
- catalog ops state;
- sku media state.

Добавлять поверх этого manager queue, assignment, note drafting, reply drafting, SLA filters и internal case navigation было бы архитектурной ошибкой.

Нужен отдельный manager state contract, например:

- `ManagerSessionState`
- отдельный key prefix в Redis
- отдельный lifecycle сохранения/восстановления
- отдельный набор panel families

### 3.5. В V1 используются только роли `OWNER` и `MANAGER`

Никаких `senior`, `supervisor`, `lead_manager` в core role model для V1.

Причины:

- в текущем access model уже есть `SystemRole.OWNER` и `SystemRole.MANAGER`;
- это достаточно для запуска;
- дополнительные ранги можно ввести позже overlay-моделью внутри manager module, не ломая существующий access layer.

### 3.6. Single operator org per deployment

ManagerBot V1 не проектируется как полноценно multi-tenant manager SaaS layer.

Прямое допущение V1:

- один deployment обслуживает одну операторскую организацию;
- внутренние менеджеры и owner принадлежат этой организации;
- `tenant_id` из AI seam пока не означает реализованный multi-tenant manager domain.

Это сильно упрощает:

- routing;
- manager inbox;
- operator notifications;
- ownership logic;
- bootstrap и права доступа.

---

## 4. Место ManagerBot в текущем TradeFlow

Текущий TradeFlow уже содержит:

- customer Telegram bot (`app/bot`);
- shared commerce core (`app/modules/*`, `app/db/models/core/*`);
- OwnerBot operator surface;
- AI assistant layer и voice ordering path;
- access model с `OWNER` и `MANAGER`;
- `CommercialReadAccessService`, который уже допускает внутренние роли к коммерческим ресурсам вне company-scope ограничения.

Это даёт правильную отправную точку.

ManagerBot не должен переписывать ядро системы.
Он должен **садиться поверх существующего домена** и добавлять manager-side operational handling.

### 4.1. Что уже есть и считается опорой

Опорные существующие элементы:

- `core.quote_cases`
- `core.quote_revisions`
- `core.orders`
- `core.procurement_drafts`
- `core.projects / objects / batches`
- document layer
- access roles `OWNER` / `MANAGER`
- `CommercialReadAccessService`
- `PanelManager` pattern
- AI manager seam (`ManagerAssistantContext`, `ManagerAssistantSeam`, `NullManagerAssistantSeam`)

### 4.2. Что уже есть, но не годится как final manager foundation

Не использовать как primary architecture:

- customer-side `ShellSessionState`
- quote thread, собранный из analytics событий
- runtime-computed quote numbering вида “пятый quote в списке”
- ownerbot modules как готовый manager framework
- `manager_integration` feature flag как будто это уже real manager feature set

`manager_integration` в текущем коде пока только seam marker для AI layer, а не готовая operational integration.

---

## 5. High-level system context

```text
[ Customer ]
    |
    v
[ Customer TradeFlow Bot ]
    |
    |   creates quote cases / sends customer messages / reads revisions / receives replies
    v
[ TradeFlow Domain Services ]
    |
    +--> [ PostgreSQL Core + Manager-side tables ]
    |
    +--> [ ManagerBot ]
    |
    +--> [ AI Copilot Seam ]
    |
    +--> [ Optional Group Topics Bridge ]
```

### Primary truth lives in DB

В БД должны жить:

- quote case identity;
- persistent public/display numbers;
- customer-visible thread entries;
- internal notes;
- assignment;
- manager ops state;
- presence;
- routing decisions;
- SLA markers;
- reply delivery state;
- AI suggestion logs / traces where needed.

Telegram нужен как surface доставки и интерфейс.
Но Telegram не должен становиться единственным местом жизни критичных данных.

---

## 6. Границы между слоями

### 6.1. Customer bot layer

Отвечает за:

- поиск;
- draft;
- quote browsing;
- order browsing;
- customer actions внутри TradeFlow;
- запросы клиента по quote-case;
- получение ответов менеджера.

Customer bot **не** отвечает за manager inbox, assignment, SLA, internal notes и manager collaboration.

### 6.2. Shared commerce core

Остаётся общим для:

- customer bot;
- ManagerBot;
- OwnerBot;
- AI assistant;
- future integrations.

Именно ядро должно хранить canonical commercial objects.

### 6.3. ManagerBot layer

Новый primary workspace для внутренних операторов.

Отвечает за:

- queue/inbox;
- case ownership;
- reply drafting;
- internal note capture;
- waiting-state updates;
- escalation;
- presence handling;
- linked artifact navigation;
- AI-assisted reply preparation.

### 6.4. AI copilot layer

Не является самостоятельным product surface для клиента.

Он должен усиливать ManagerBot через:

- summary;
- reply suggestion;
- missing-fields hints;
- risk flags;
- retrieval of linked context;
- safe acknowledgement templates where allowed.

### 6.5. Optional group topics bridge

Это secondary collaboration shell.

Он может понадобиться для:

- командной видимости;
- сложных escalations;
- peer discussion;
- owner visibility.

Но он не должен определять архитектуру V1.

---

## 7. V1 domain anchor and future extraction path

### 7.1. V1 anchor

В V1 manager-side workload anchored to:

- `core.quote_cases`
- связанные `quote_revisions`
- связанные `orders`
- связанные `documents`
- связанные `drafts`
- связанные `projects/objects`

Это означает:

- customer message about quote case создаёт/обновляет workload для менеджера;
- manager queue агрегирует именно эти кейсы;
- case detail открывается вокруг quote-case и связанных артефактов.

### 7.2. Future extraction path

Если потом появятся отдельные non-quote conversations, warranty flows, onboarding flows или service tickets, тогда можно выделить generic `manager_case` abstraction.

Но это **не цель V1**.

V1 должен стабилизировать manager operations на одном реальном объекте, а не строить преждевременную супер-иерархию.

---

## 8. Persistence architecture

## 8.1. Existing core tables reused as-is

ManagerBot V1 переиспользует существующие core-сущности:

- `core.quote_cases`
- `core.quote_revisions`
- `core.quote_revision_lines`
- `core.orders`
- `core.documents`
- project/object related tables

### 8.2. New manager-side persistence required

Для V1 нужны отдельные manager-side таблицы или эквивалентные persistent сущности.

Минимально необходимы:

1. **Case ops state**
   - текущий operational status;
   - waiting-state;
   - priority;
   - human requested flag;
   - escalation level;
   - timestamps for last activity;
   - SLA due markers.

2. **Assignment history**
   - кто взял кейс;
   - кто переназначил;
   - когда;
   - по какой причине.

3. **External thread entries**
   - сообщение клиента;
   - ответ менеджера;
   - направление сообщения;
   - delivery state;
   - visibility = customer-visible.

4. **Internal notes**
   - только для команды;
   - не показываются клиенту;
   - не участвуют в customer timeline.

5. **Presence state**
   - manager available / busy / offline;
   - optional reason;
   - updated_at.

6. **Routing / notification records**
   - why case was assigned/escalated/notified;
   - operator-facing observability.

### 8.3. Persistent public numbering required

Для `quote_cases` и `orders` нужен persistent display/public number.

Нельзя оставлять numbering как производное от текущей выдачи списка в UI, потому что manager-side требует:

- стабильную ссылку в коммуникации;
- повторяемый case label;
- searchability;
- понятную ссылку в topic/title/уведомлениях;
- нормальную human navigation.

### 8.4. External thread and internal notes must be separate

Customer-visible thread entries и internal notes не должны лежать в одной сущности с флагом “maybe hidden”.

Правильнее:

- отдельная таблица для external thread;
- отдельная таблица для internal notes.

Причина очевидна: меньше риск утечки внутренней заметки клиенту и чище read models.

---

## 9. Runtime architecture

## 9.1. Separate bot surface

ManagerBot V1 должен быть отдельным Telegram bot surface.

Практически это означает:

- отдельный bot token рекомендуется как baseline;
- отдельный router/handlers package;
- отдельная навигационная модель;
- отдельное state storage пространство;
- shared application bootstrap и shared domain services.

Не надо встраивать ManagerBot как ещё один hub внутрь customer bot home.

Причины:

- другая аудитория;
- другой UX;
- другая нагрузка на state;
- другие security expectations;
- меньше риск сломать customer experience.

## 9.2. Shared application/runtime

Несмотря на отдельный surface, ManagerBot V1 остаётся частью одного codebase и одного modular monolith runtime.

Общее:

- DB models;
- repositories;
- services;
- analytics emitter;
- access layer;
- AI seam;
- infra bootstrap patterns.

Это даёт:

- меньше duplication;
- reuse existing business services;
- единый deploy pipeline;
- простую локальную разработку.

## 9.3. Suggested package layout

Рекомендуемая структура V1:

```text
app/
  manager_bot/
    contracts.py
    runtime.py
    panels.py
    keyboards.py
    state_store.py
    handlers/
      home.py
      queue.py
      case_detail.py
      reply.py
      notes.py
      presence.py
  modules/
    manager_cases/
      domain.py
      enums.py
      service.py
      repository.py
      telegram.py
      validation.py
    manager_presence/
      service.py
      repository.py
    manager_threads/
      service.py
      repository.py
    manager_notifications/
      service.py
      repository.py
```

Важно:

- bot surface и domain modules разделены;
- handlers не тащат business logic внутрь себя;
- manager domain не размазывается по existing customer shell files.

## 9.4. Bootstrap placement

В bootstrap должны появиться:

- manager bot config;
- manager routers;
- manager state store;
- manager services;
- wiring to existing quote/order/document/project services;
- wiring to AI manager seam.

Но customer bootstrap и manager bootstrap должны оставаться различимыми, а не слитыми в один giant init block.

---

## 10. Session and state architecture

## 10.1. Separate ManagerSessionState

ManagerBot должен иметь свой state contract.

Примерный состав:

- `telegram_user_id`
- `active_panel_key`
- `back_panel_key`
- `selected_queue`
- `queue_filters`
- `loaded_limit`
- `selected_quote_case_id`
- `reply_draft`
- `internal_note_draft`
- `presence_mode`
- `last_opened_artifact`
- `ai_assist_context`

### 10.2. State isolation goals

Изоляция нужна не ради красоты, а чтобы:

- customer shell не ломался от manager features;
- manager navigation была deterministic;
- разные callback families не путались;
- можно было independently тестировать manager flows;
- future multi-surface evolution не превращалась в боль.

### 10.3. Panel architecture

Можно переиспользовать паттерн `PanelManager`, но не reuse existing customer panel keys один к одному.

У ManagerBot должны быть собственные panel families:

- `manager_home`
- `manager_queue:<name>`
- `manager_case:<id>`
- `manager_reply`
- `manager_note`
- `manager_presence`
- `manager_ai_assist`

---

## 11. Access architecture

## 11.1. Existing access model is sufficient for V1

V1 intentionally uses only:

- `SystemRole.OWNER`
- `SystemRole.MANAGER`

Этого достаточно, потому что:

- internal roles already exist;
- `CommercialReadAccessService` already bypasses company-scope restriction for internal roles;
- owner can see all manager data in deployment;
- manager can work with commercial resources without fake company user simulation.

## 11.2. No new core roles in V1

Не вводить:

- `senior`
- `supervisor`
- `lead_manager`

в current `SystemRole` enum на этапе V1.

Если later понадобится hierarchy, она должна жить overlay-слоем в manager domain, а не ломать access core раньше времени.

## 11.3. Owner access model

В V1 owner считается internal super-user for manager-side workflow.

Практически это означает:

- owner может читать очереди;
- owner может заходить в кейсы;
- owner может видеть escalation;
- owner может подхватывать или переназначать кейсы.

Никакой отдельной owner-only manager архитектуры не требуется.

---

## 12. Interaction architecture

## 12.1. Inbound customer message path

Высокоуровневый поток:

```text
Customer writes in quote context
-> customer bot validates access
-> thread entry persisted in DB
-> analytics event emitted
-> manager ops state updated
-> queue counters/read models updated
-> assigned manager or owner notified
```

Ключевое правило:

**Сначала persistence, потом notification.**

Не наоборот.

## 12.2. Manager reply path

Высокоуровневый поток:

```text
Manager opens case
-> drafts reply / uses AI suggestion
-> reply persisted as external thread entry
-> delivery attempt to customer
-> delivery state updated
-> customer timeline becomes readable from DB truth
-> analytics event emitted
```

Ключевое правило:

**Reply is not considered successful merely because button was pressed.**
Нужна явная фиксация delivery attempt/result.

## 12.3. Internal note path

```text
Manager opens case
-> adds internal note
-> internal note persisted separately
-> note visible only in manager surfaces
-> optional owner visibility / escalation visibility
```

Internal note не должна:

- попадать в customer timeline;
- трактоваться как reply;
- попадать в AI auto-send.

## 12.4. Assignment and routing path

```text
new customer activity
-> routing rules evaluate
-> case stays assigned / becomes unassigned / escalates
-> queue membership updated
-> notification policy applied
```

Routing logic должна быть deterministic и observable.
Нельзя делать чёрный ящик “система так решила”.

---

## 13. AI placement in architecture

## 13.1. Current starting point

В текущем коде уже существует manager AI seam:

- `ManagerAssistantContext`
- `ManagerAssistantSeam`
- `NullManagerAssistantSeam`

Это правильный integration boundary, но пока не готовый manager product.

## 13.2. V1 AI role

AI в V1 должен работать только как copilot for manager-side handling:

- summarize case;
- collect linked commercial context;
- suggest reply draft;
- suggest next action;
- detect missing fields;
- raise risk hints;
- propose acknowledgement in safe lanes.

## 13.3. What AI must not do in V1

AI не должен:

- самостоятельно вести клиента как default face of service;
- слать autonomous complex replies;
- принимать discount/commercial negotiation decisions;
- invent operational routing without human-visible trace;
- подменять human-required lanes.

## 13.4. AI invocation model

Manager AI should be invoked from ManagerBot context, not from generic customer assistant path.

То есть архитектурно правильно:

- customer bot uses customer assistant flows;
- ManagerBot uses manager-specific AI assist entrypoints;
- shared underlying AI infra may stay common, but context contract differs.

---

## 14. Optional group topics bridge

Group topics не являются частью primary architecture.

Если они добавляются позже, то only as mirror/collaboration bridge.

### 14.1. Allowed use

Topics могут использоваться для:

- visibility;
- escalation room;
- team discussion;
- owner monitoring.

### 14.2. Forbidden use

Topics не должны быть единственным местом, где существует:

- история кейса;
- assignment truth;
- internal notes;
- customer reply state;
- SLA status.

### 14.3. Design principle

```text
DB -> ManagerBot -> optional Topic mirror
```

а не:

```text
Telegram topic -> maybe DB later
```

---

## 15. Deployment model

## 15.1. One deployment, one operator org

V1 deployment model intentionally simple:

- один customer-side TradeFlow deployment;
- один manager-side operator organization;
- owner + managers работают внутри этого deployment;
- no cross-tenant manager workspace.

## 15.2. Shared database, shared infra

ManagerBot V1 использует:

- ту же PostgreSQL базу;
- тот же Redis class of infra;
- тот же logging / analytics backbone;
- тот же modular monolith deploy.

Это важно, потому что цель V1 не в создании distributed zoo, а в запуске рабочего manager workflow.

## 15.3. Extraction path later

Если later потребуется выделение manager-side в отдельный сервис, это станет возможным только потому, что уже на V1:

- state isolated;
- bot surface isolated;
- persistence contracts explicit;
- modules separated.

---

## 16. Scalability and change tolerance

Архитектура V1 должна выдержать:

- рост очередей;
- несколько менеджеров;
- owner visibility;
- AI assist expansion;
- optional group topic collaboration;
- переход к richer routing rules;
- future overlay hierarchy.

Она не должна требовать полной переделки при появлении:

- SLA dashboards;
- manager performance analytics;
- canned replies;
- VIP routing;
- warranty/service flows.

Но это достигается не “умной абстракцией на бумаге”, а чётким separation of concerns на старте.

---

## 17. Non-goals for this architecture

Этот документ **не** предполагает, что V1 должен сразу включать:

- generic service desk engine;
- multi-tenant operator SaaS;
- web-admin for manager handling;
- autonomous AI customer support;
- topic-first collaboration architecture;
- complex role hierarchy;
- giant universal state object.

Если кто-то начнёт кодить именно это, он кодит не V1, а личную фантазию.

---

## 18. Architecture implications for next docs

После этого документа следующие документы должны раскрыть конкретику, а не спорить с ним:

1. `20_domain_model_manager_cases.md`
   - какие сущности и таблицы нужны;
   - как разделяются external thread, internal notes, ops state, assignment.

2. `25_case_statuses_and_routing.md`
   - operational statuses;
   - waiting states;
   - priority;
   - escalation logic;
   - routing rules.

3. `30_managerbot_panels_and_navigation.md`
   - home;
   - queues;
   - case detail;
   - reply;
   - notes;
   - presence;
   - deterministic back behavior.

4. `35_manager_reply_flow.md`
   - message persistence;
   - delivery path;
   - failure handling;
   - visibility rules.

Без этих документов Codex начнёт достраивать недостающие куски по своему вкусу, а вкусы у машин, как известно, не всегда совместимы с жизнью.

---

## 19. Final architecture statement

ManagerBot V1 должен быть построен как:

- **separate Telegram manager surface**,
- **shared-codebase modular monolith extension**,
- **DB-first operational layer over existing quote cases**,
- **state-isolated from customer shell**,
- **role-simple (`OWNER` / `MANAGER`)**,
- **single-operator per deployment**,
- **AI-assisted but human-led**,
- **topic-optional, not topic-dependent**.

Любое решение, которое нарушает один из этих пунктов, должно считаться архитектурным отклонением и требовать отдельного обоснования.
