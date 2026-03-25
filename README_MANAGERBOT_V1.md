# ManagerBot V1 README

**Статус:** canonical bootstrap for manager-side layer  
**Дата:** 25 March 2026  
**Назначение:** этот документ фиксирует архитектурную доктрину, границы V1 и обязательные решения по ManagerBot как отдельному операционному контуру поверх TradeFlow.

---

## 1. Зачем нужен ManagerBot

TradeFlow уже умеет вести клиента по коммерческой цепочке:

```text
search -> SKU -> draft -> quote -> order -> reorder -> object/project
```

Но buyer-side сам по себе не решает операционную задачу компании:

- кто отвечает клиенту;
- кто владеет кейсом;
- кто видит новые обращения;
- кто держит SLA;
- кто подхватывает кейс, если менеджер offline;
- где лежит история внешней и внутренней коммуникации;
- как AI помогает менеджеру, не становясь лицом бренда.

ManagerBot нужен как **primary workspace** для операционной команды.

Его задача — дать компании рабочую поверхность для:

- inbox/queues;
- case ownership;
- manager replies;
- assignment/reassignment;
- presence and routing;
- internal notes;
- escalation;
- AI-assisted handling.

---

## 2. Главный продуктовый вывод

Manager-side layer должен быть:

- **human-first**;
- **manager-first**;
- **Telegram-native**;
- **DB-first**;
- **case-centric**;
- **SLA-aware**;
- **AI-assisted, but not AI-fronted**.

Это означает:

1. **Клиенту отвечает человек**, кроме узких safe-auto сценариев.
2. **AI усиливает менеджера**, но не подменяет его как лицо сервиса.
3. **Источник истины — БД**, а не Telegram group/topic.
4. **Каждое обращение живёт как case**, а не как хаотический чат.
5. **ManagerBot — основной интерфейс менеджера**.
6. **Group topics — вторичный слой**, а не источник истины.
7. **V1 строится вокруг текущего TradeFlow domain**, а не вокруг новой абстрактной платформы “на всё”.

---

## 3. Канонические решения для V1

Эта версия README прямо фиксирует решения, которые не надо оставлять “на потом”.

### 3.1. Роли V1

В V1 используются только существующие internal system roles:

- `OWNER`
- `MANAGER`

В V1 **не вводятся** отдельные system roles:

- `senior`
- `supervisor`

Если позже понадобятся lead/senior/supervisor сценарии, это должно появиться как отдельный manager-side overlay поверх assignment/routing/escalation, а не как поспешное распухание core access model.

### 3.2. Deployment assumption V1

V1 assumes:

- **single operator org per deployment**

Иными словами, один инстанс ManagerBot обслуживает одну операторскую команду вокруг данного развёртывания TradeFlow.

`tenant_id` в AI seam существует как future seam и технический контракт, но V1 не строится как полноценная multi-tenant operator platform.

### 3.3. Separate session state is mandatory

ManagerBot должен иметь:

- отдельный session state;
- отдельный state-store namespace / key prefix;
- отдельные panel/navigation contracts.

Нельзя смешивать manager session state с текущим customer shell state.  
Иначе дальнейшее расширение сломает навигацию, assistant snapshot flows и любые manager-side переходы. Люди часто так делают, а потом героически тушат пожар, который сами же и устроили.

### 3.4. Quote-case is the anchor for V1

V1 **не начинает** с новой “универсальной case platform”.

Первичный operational anchor V1:

- existing `core.quote_cases`

Manager-side слой должен на первом этапе строиться вокруг существующих quote-case сущностей и рядом лежащего ops/persistence слоя.

---

## 4. Что не надо делать

### 4.1. Не делать AI лицом сервиса

Нельзя строить модель, где клиент получает:

- уверенную чушь;
- шаблонные отписки;
- отсутствие реальной эскалации;
- имитацию “живого менеджера”, когда нужен живой человек.

### 4.2. Не делать Telegram group source of truth

Group topics могут быть полезны для командной работы, но:

- история не должна жить только в Telegram;
- удаление topic/message не должно ломать бизнес;
- все важные thread entries должны жить в БД.

### 4.3. Не делать V1 через новый universal case engine

На первом этапе нельзя перепрыгивать в “универсальную платформу кейсов для всего на свете”.

Сначала нужен рабочий manager-side слой вокруг:

- `quote_cases`
- linked `orders`
- linked `drafts`
- linked `objects/projects`

### 4.4. Не смешивать внешний и внутренний thread

Внешний thread видит клиент.  
Внутренний thread видит только команда.

Это должны быть **разные доменные сущности/каналы**, а не одна лента с надеждой, что никто не ошибётся кнопкой.

### 4.5. Не делать runtime-computed numbering как канон

В customer shell сейчас часть публичной нумерации фактически вычисляется на лету из списка.

Для manager-side V1 это уже недостаточно.

`Quote #N` и `Order #N` должны получить **persistent display/public number**, а не UI-эвристику.

---

## 5. Правильная целевая архитектура

```text
Customer TradeFlow Bot
        |
        v
TradeFlow Domain / DB
        |
        +--> ManagerBot (primary workspace)
        |
        +--> Optional Manager Group Topics (secondary collaboration layer)
        |
        +--> AI Copilot / Routing Layer
```

### Источник истины

Всегда в доменной БД должны жить:

- quote cases;
- manager ops state;
- assignments;
- thread entries;
- internal notes;
- statuses;
- SLA markers;
- routing decisions;
- delivery states;
- AI suggestions / logs.

---

## 6. Роли и доступ V1

### 6.1. Customer

Использует TradeFlow customer bot:

- ищет товары;
- собирает draft;
- отправляет запрос;
- получает quote/order updates;
- пишет во внешний case thread;
- может явно запросить человека.

### 6.2. Manager (`MANAGER`)

Использует ManagerBot:

- видит очереди;
- берёт кейс в работу;
- отвечает клиенту;
- меняет waiting-state;
- оставляет internal note;
- передаёт кейс;
- эскалирует кейс Owner'у;
- использует AI draft/summary;
- открывает связанные quote/order/draft/object.

### 6.3. Owner (`OWNER`)

Использует ManagerBot как пользователь с полным внутренним доступом:

- видит все кейсы;
- видит все очереди;
- подхватывает любые кейсы;
- может переприсваивать и эскалировать;
- видит системную картину и проблемные кейсы.

### 6.4. System

Создаёт:

- system events;
- safe auto acknowledgments;
- routing decisions;
- presence-based notifications;
- escalation markers.

### 6.5. AI Copilot

Не отвечает как лицо бренда по умолчанию.

Его функции:

- summarize;
- classify;
- suggest reply;
- retrieve context;
- detect missing fields;
- flag risk;
- propose next action.

---

## 7. Domain anchor и обязательные persistence-правила

### 7.1. Что является primary commercial entity

В V1 primary commercial entity для manager-side:

- `core.quote_cases`

ManagerBot не переписывает quote domain.  
Он добавляет рядом manager-side operational слой.

### 7.2. Разделение commercial status и operational status

`quote_cases.status` остаётся коммерческим lifecycle поля quote domain.

Manager-side operational lifecycle не должен насильно втискиваться в `quote_case_status`.

Иными словами:

- `quote_cases.status` = коммерческая сущность;
- `quote_case_ops_state.status` = operational manager status.

Это надо держать раздельно. Иначе через пару PR кто-то обязательно засунет `waiting_customer` в quote enum, потому что очень захотелось жить красиво.

### 7.3. Thread storage не может жить только в analytics

Analytics events нужны для метрик и истории событий, но **не являются** manager/customer chat store.

В V1 должен существовать отдельный persistent thread store для:

- customer-visible external thread;
- internal notes;
- delivery state;
- timeline render.

### 7.4. Public/display number должен быть persistent

Для manager-side и linked artifact opens нужны:

- `quote_cases.display_number` или `public_number`
- `orders.display_number` или `public_number`

Это обязательная основа для стабильного UX и операционной коммуникации.

---

## 8. Основные сущности V1

### 8.1. QuoteCase

Коммерческий anchor-case. Уже существует в core и остаётся primary entity для V1 manager-side.

### 8.2. QuoteCaseOpsState

Отдельное operational состояние поверх quote-case.

Минимальные поля:

- `quote_case_id`
- `assigned_manager_actor_id`
- `status`
- `waiting_state`
- `priority`
- `human_requested`
- `escalation_level`
- `sla_due_at`
- `last_customer_message_at`
- `last_manager_message_at`
- `last_routing_reason`
- `created_at`
- `updated_at`

### 8.3. ExternalThreadEntry

Customer-visible timeline entry.

Поля:

- `id`
- `quote_case_id`
- `entry_type`
- `author_role`
- `author_actor_id`
- `body`
- `source_channel`
- `delivery_state`
- `telegram_chat_id`
- `telegram_message_id`
- `created_at`

### 8.4. InternalNote

Внутренний комментарий команды, не видимый клиенту.

Минимальные поля:

- `id`
- `quote_case_id`
- `author_actor_id`
- `body`
- `note_kind`
- `created_at`

### 8.5. AssignmentHistory

История назначения/переназначения кейса.

### 8.6. PresenceState

Для каждого internal manager actor:

- `online`
- `busy`
- `away`
- `offline`

### 8.7. RoutingDecision

Фиксация причины, по которой кейс был:

- auto-acked;
- assigned;
- left unassigned;
- marked human-required;
- escalated to owner.

---

## 9. Основные состояния V1

### 9.1. Manager operational status

Примерный набор:

- `new`
- `active`
- `waiting_customer`
- `waiting_manager`
- `escalated`
- `resolved`
- `closed`

### 9.2. Waiting state

Отдельно от общего manager status:

- `waiting_manager`
- `manager_answered`
- `waiting_customer`
- `no_action`

### 9.3. Priority

- `low`
- `normal`
- `high`
- `urgent`
- `vip`

---

## 10. Presence и availability

Presence обязателен уже в V1.

### Статусы менеджера

- `online`
- `busy`
- `away`
- `offline`

### Presence влияет на

- routing;
- safe auto behavior;
- queue visibility;
- assignment logic;
- SLA warnings;
- честность обещаний клиенту.

### Минимальные actions

- `Я online`
- `Я busy`
- `Я away`
- `Я offline`

Позже можно добавить:

- heartbeat;
- inactivity timeout;
- shift schedule.

---

## 11. Очереди

### ManagerBot должен иметь базовые queue surfaces

- `New`
- `Assigned to me`
- `Unassigned`
- `Waiting for me`
- `Waiting for customer`
- `Urgent`
- `Escalated`
- `Closed recently`

Дополнительно позже:

- `VIP`
- `Over SLA`
- `AI draft available`

Queue surfaces должны быть:

- compact;
- list-first;
- mobile-friendly;
- deterministic;
- быстрыми для одной руки и одного большого пальца, потому что у людей внезапно только один экран.

---

## 12. Панели ManagerBot

### 12.1. Home

Содержит:

- current presence;
- queue shortcuts;
- counts;
- quick actions.

### 12.2. Queue list

Каждая строка показывает:

- case number;
- customer/company;
- object if any;
- operational status;
- waiting side;
- priority;
- SLA risk marker;
- assignee marker.

### 12.3. Case detail

Содержит:

- header;
- latest message;
- external timeline;
- internal notes summary;
- linked artifacts;
- AI summary;
- actions.

### 12.4. Internal notes view

Отдельно от customer-visible thread.

### 12.5. Assignment / escalation panel

- assign to me;
- reassign;
- escalate to owner;
- mark waiting state.

### 12.6. AI assist panel

- generate summary;
- suggest reply;
- propose clarification;
- propose replacement response;
- explain risk.

---

## 13. Основные действия менеджера

### Case-level actions

- `Взять в работу`
- `Ответить`
- `AI draft`
- `Запросить уточнение`
- `Предложить замену`
- `Открыть quote`
- `Открыть order`
- `Открыть draft`
- `Открыть object`
- `Internal note`
- `Передать`
- `Эскалировать Owner`
- `Waiting customer`
- `Waiting manager`
- `Закрыть`

### Queue-level actions

- `Refresh`
- `Filter`
- `My cases`
- `Unassigned`
- `Urgent`
- `Back`
- `Home`

---

## 14. Разделение внешнего и внутреннего thread

### 14.1. Внешний thread

Виден клиенту и синхронизируется с customer-side:

- customer messages;
- manager replies;
- safe system events;
- delivery-visible events.

### 14.2. Внутренний слой

Виден только OWNER/MANAGER:

- internal notes;
- routing remarks;
- escalation remarks;
- AI summaries;
- risk remarks.

### 14.3. Жёсткое правило

Нельзя смешивать внешний и внутренний каналы в одну ленту и надеяться, что никто не промахнётся кнопкой.

---

## 15. Роль AI в ManagerBot

AI = **copilot**, не frontline persona.

### 15.1. Что AI делает

- суммаризирует кейс;
- собирает контекст из TradeFlow;
- предлагает ответ;
- выявляет missing fields;
- ставит risk flags;
- помогает быстро открыть нужный коммерческий контекст.

### 15.2. Что AI может отправить без человека

Только bounded safe responses:

- acknowledgment;
- “мы получили запрос”;
- “уточните артикул / количество / объект / сроки”;
- status replay;
- data replay.

### 15.3. Что AI не должен делать сам

- обещать скидки;
- обещать сроки;
- принимать спорное решение;
- выбирать нестандартный товар на ответственность компании;
- закрывать конфликт;
- притворяться человеком, если клиент запросил человека;
- отправлять автономные manager replies.

### 15.4. Статус manager AI seam

AI manager seam уже существует как подготовленный handoff boundary, но **не является** готовым ManagerBot продуктом.

Это значит:

- seam сохраняем;
- full manager AI откладываем до отдельной волны;
- V1 ManagerBot строится сначала как реальный human workflow.

---

## 16. Group Topics: место в архитектуре

Group topics полезны, но **не как primary manager UI**.

### Их место

- team collaboration;
- visibility;
- war-room по сложным кейсам;
- optional operational mirror.

### Они не должны быть

- единственным inbox;
- местом хранения истины;
- единственным способом ответить клиенту.

### Правильная модель

```text
DB thread (truth)
-> optional mirror into group topic
<- optional team discussion/events
```

Но primary manager action происходит в **ManagerBot**.

---

## 17. Integration with TradeFlow core

ManagerBot не живёт отдельно от TradeFlow domain.

Он использует те же доменные сущности:

- draft;
- quote;
- order;
- object/project;
- customer/company context.

### Базовые интеграционные возможности

- открыть связанный quote;
- открыть order;
- открыть draft;
- открыть object;
- увидеть recent artifacts;
- увидеть customer-visible timeline;
- увидеть internal notes;
- увидеть current ops state.

---

## 18. Ошибки, edge-cases, реальность

Система должна учитывать:

- blackout / менеджер offline;
- delayed replies;
- stale assignee;
- case без object;
- case без source draft;
- conflicting customer replies;
- delivery failure в customer Telegram;
- повторные сообщения клиента, пока менеджер away.

### Минимально обязательные правила

- кейс не должен потеряться;
- клиент должен получить acknowledgment;
- если клиент запросил человека, safe auto должен быть ограничен;
- при offline менеджера кейс должен идти в очередь;
- manager-side должен честно показывать waiting side;
- timeline должен читаться из persistent store, а не “примерно из событий”.

---

## 19. MVP-границы ManagerBot V1

### Входит в V1

- manager identity через existing roles;
- presence;
- inbox/queues;
- case list;
- case detail;
- manager reply;
- internal note;
- assignment/reassignment;
- waiting-state control;
- linked artifact opens;
- basic AI summary + suggested reply;
- safe auto acknowledgment rules;
- notification routing;
- persistent display numbers;
- dedicated manager session state;
- dedicated thread persistence.

### Не входит в V1

- новый universal case engine;
- новая расширенная system role hierarchy;
- полноценная web-admin;
- сложная supervisor analytics;
- enterprise canned-replies library;
- сложный workforce balancing;
- omnichannel outside Telegram;
- full AI autopilot;
- full operator multi-tenancy.

---

## 20. Архитектурная позиция по модулям

### Предлагаемый контур

```text
Shared Commerce Core
├─ TradeFlow customer bot
├─ ManagerBot
├─ Optional Manager Group Bridge
└─ OwnerBot (owner analytics layer)
```

### Внутри ManagerBot

```text
app/manager_bot/
  handlers/
  keyboards/
  panels/
  formatters/
  state/

app/modules/manager_cases/
app/modules/manager_presence/
app/modules/manager_routing/
app/modules/manager_notes/
app/modules/manager_notifications/
app/modules/manager_ai_assist/
```

Не обязательно буквально так, но разделение ответственности должно быть именно таким.

---

## 21. PR roadmap (manager-side)

### MPR0 — docs freeze and canonical contract

Нужно зафиксировать:

- `OWNER` / `MANAGER` only for V1;
- single operator org per deployment;
- separate manager session state;
- quote-case as V1 anchor;
- persistent display numbers;
- dedicated external/internal persistence;
- operational state separate from quote commercial status.

### MPR1 — thread foundation and stable identifiers

- persistent `display_number` / `public_number`
- dedicated external thread store
- internal notes store
- delivery state persistence
- refactor timeline reads away from analytics-only approach

### MPR2 — manager operational state and queues

- `quote_case_ops_state`
- assignment history
- presence state
- queue read models
- SLA fields
- routing reasons

### MPR3 — ManagerBot bootstrap surface

- manager auth/access
- separate state store
- Home
- Queue list
- Case detail
- presence actions
- take/reassign basics

### MPR4 — reply flow, delivery, internal notes

- manager reply -> customer delivery
- delivery success/failure states
- internal notes flow
- waiting state transitions
- reopen / repeated customer message handling

### MPR5 — AI copilot assist

- AI summary
- suggested reply
- missing fields prompt
- risk flags
- no autonomous send

### MPR6 — optional group bridge and operations polish

- optional group topic mirror
- overdue markers
- escalation polish
- owner-focused operational visibility

---

## 22. Что считать canonical source

Если будущие документы по ManagerBot противоречат этому README по вопросам:

- ManagerBot as primary workspace;
- DB as source of truth;
- `OWNER/MANAGER only` for V1;
- single operator org assumption;
- separate manager session state;
- quote-case as V1 anchor;
- separation of commercial status vs operational status;
- separation of external thread vs internal notes;
- AI as copilot, not frontline;
- role of group topics,

то приоритет у этого README до тех пор, пока новая версия не будет явно утверждена как canonical.

---

## 23. Главный вывод

Manager-side layer надо строить не как:

- группу вместо системы;
- AI вместо менеджера;
- универсальный case engine ради абстрактной красоты;
- shared state кашу между customer shell и manager shell.

А как:

```text
existing quote-case domain
+ dedicated manager ops persistence
+ ManagerBot as primary workspace
+ optional group topics as collaboration shell
+ AI copilot for speed and quality
```

Это даёт:

- управляемость;
- персональную ответственность;
- живой человеческий сервис;
- устойчивость к offline/blackout сценариям;
- масштабируемый маршрут без архитектурного позора.
