# 90_pr_plan_managerbot.md

# ManagerBot V1 PR Plan

**Статус:** canonical PR sequence for ManagerBot V1 after AI-layer readiness  
**Дата:** 25 March 2026  
**Назначение:** этот документ фиксирует правильный порядок сборки ManagerBot V1 поверх текущего состояния TradeFlow, чтобы не сломать baseline, не размазать manager-side persistence по случайным местам и не построить Telegram surface поверх недозрелой доменной модели.

---

## 1. Зачем нужен этот документ

К этому моменту уже зафиксированы:

- `README_MANAGERBOT_V1.md`
- `10_architecture_managerbot.md`
- `20_domain_model_manager_cases.md`
- `25_case_statuses_and_routing.md`
- `30_managerbot_panels_and_navigation.md`
- `35_manager_reply_flow.md`
- `60_data_model_postgres_managerbot.md`

Этого уже достаточно, чтобы начать писать код.

Но без PR-плана почти гарантированно произойдёт один из двух плохих сценариев:

1. команда слишком рано начнёт строить ManagerBot UI и потом будет переделывать persistence, queue logic и thread storage;
2. команда уйдёт в бесконечное “давайте ещё немного допилим baseline”, и менеджерский контур так и останется в документах.

Оба сценария плохие.

Нужен **третий путь**:

- сначала сделать **короткую, жёстко ограниченную baseline-foundation wave** внутри TradeFlow;
- потом сразу поднять **ManagerBot как отдельный Telegram surface**;
- дальше наращивать manager-side handling уже поверх правильных доменных и DB contracts.

Именно это и фиксирует данный документ.

---

## 2. Главный инженерный вывод по порядку работ

### Неправильный путь №1

Сначала пилить “настоящий ManagerBot”, а потом дружить его с TradeFlow.

Почему это ошибка:

- у ManagerBot не будет нормального source of truth;
- придётся читать customer thread из analytics/event ledger или из временных костылей;
- assignment/routing/SLA будут либо фальшивыми, либо дублированными;
- потом придётся ломать уже написанный Telegram surface.

Итог: красивый bot shell поверх сырой operational model.

---

### Неправильный путь №2

Сначала “полностью допилить baseline”, а ManagerBot делать когда-нибудь потом.

Почему это ошибка:

- baseline можно “допиливать” бесконечно;
- manager-side реальность не проверяется руками;
- queue/reply/delivery/assignment проблемы остаются теоретическими;
- продукт вроде бы становится богаче, но бизнес всё ещё не может нормально работать с клиентом.

Итог: бесконечная полировка without operations.

---

### Правильный путь

**Сначала короткая baseline wave именно под manager-domain, потом сразу ManagerBot surface.**

То есть порядок такой:

1. **baseline augmentations inside TradeFlow**  
   Только то, без чего manager-side слой нельзя строить правильно.

2. **ManagerBot bootstrap**  
   Как только persistence и read model уже нормальные.

3. **manager handling wave**  
   Reply flow, routing, delivery, SLA, AI copilot.

Ключевая формула:

```text
Do not build ManagerBot before the domain is ready.
Do not postpone ManagerBot until the end of civilization.
Build the minimum manager-grade domain first, then immediately expose it through ManagerBot.
```

---

## 3. Что считается baseline, а что считается manager-side wave

### 3.1. Baseline-required pieces

Это должно быть частью baseline TradeFlow, потому что без этого система не является полноценным B2B operational product:

- persistent `display_number` / `public_number` for quotes and orders;
- baseline-required `ops.*` schema;
- external thread persistence;
- internal notes persistence;
- quote-case operational state;
- manager presence/assignment/routing persistence;
- reply delivery tracking;
- customer-side quote detail read path, читающий правильный thread store, а не только analytics events.

### 3.2. ManagerBot-specific pieces

Это уже отдельный manager-side surface и workflow layer:

- отдельный Telegram bot / отдельный manager-facing entry surface;
- отдельный manager session state;
- queues;
- case detail manager view;
- take/release/escalate actions;
- compose reply / compose note UX;
- manager notifications;
- AI copilot;
- optional group-topics bridge.

### 3.3. Важное правило про baseline migration discipline

До live launch система всё ещё живёт в режиме **canonical baseline**.

Это означает:

- manager-side baseline tables не оформляются как “вечная цепочка feature migrations ради истории”; 
- они вносятся в canonical baseline schema как часть текущей истины системы;
- PR sequence существует для инженерной дисциплины и проверки кода, а не для накопления доисторических миграций.

Иначе будет не migration discipline, а музей страданий.

---

## 4. Current repository reality before ManagerBot wave

На момент старта ManagerBot wave у репозитория уже есть:

- buyer-core search/draft/quote/order/project flows;
- list-first Telegram UX;
- AI assistant layer;
- voice search/order input path;
- owner/reporting seams;
- existing `core.quote_cases` как V1 anchor;
- `MANAGER` и `OWNER` роли в access model;
- panel discipline и session-driven Telegram shell.

При этом ещё отсутствует полноценный manager-grade operational contour:

- customer quote messages всё ещё исторически опираются на analytics events;
- нет dedicated `ops.quote_case_thread_entries`;
- нет dedicated `ops.quote_case_internal_notes`;
- нет `ops.quote_case_ops_states` как канонического operational truth;
- нет manager presence state;
- нет assignment/routing persistence;
- нет delivery-attempt model;
- нет отдельного ManagerBot session state и Telegram surface.

Отсюда и правильный порядок wave: сначала foundation, потом surface.

---

## 5. Canonical wave structure

### Wave A — Baseline manager-domain foundation
Сделать минимальный manager-grade operational domain внутри baseline TradeFlow.

### Wave B — ManagerBot bootstrap surface
Поднять отдельный manager-facing Telegram surface на уже правильных read/write contracts.

### Wave C — Manager handling completion
Довести case work, reply flow, delivery, routing и SLA до реальной эксплуатации.

### Wave D — AI copilot and optional collaboration extensions
Добавить AI-assisted handling и optional group bridge без смешивания их с source of truth.

---

## 6. Canonical PR sequence overview

| PR | Title | Wave | Goal |
|---|---|---|---|
| MB0 | Docs freeze and canonical contract alignment | A | Зафиксировать final docs package как источник истины перед кодом |
| MB1 | Baseline ops schema and stable public identifiers | A | Ввести `ops.*` foundation и persistent numbering |
| MB2 | Thread/store refit and customer-side continuity | A | Перевести quote thread на нормальный store и сохранить continuity buyer-side |
| MB3 | Manager operational state, assignment, presence, and routing read model | A | Завести operational truth, очереди и routing contracts |
| MB4 | ManagerBot bootstrap surface and separate session state | B | Поднять отдельный manager-facing Telegram surface |
| MB5 | Case handling actions, reply compose, notes, and delivery tracking | C | Довести реальный workflow менеджера по кейсу |
| MB6 | Notifications, SLA, escalation, and queue hardening | C | Сделать контур устойчивым для реальной работы команды |
| MB7 | AI copilot for managers | D | Подключить AI как помощника менеджера, а не как лицо бренда |
| MB8 | Optional group topics bridge and release hardening | D | Добавить optional collaboration shell и провести финальную стабилизацию |

---

## 7. PR-by-PR detailed plan

## MB0 — Docs freeze and canonical contract alignment

### Purpose
Закрыть фазу архитектурных догадок.

### Scope
- финализировать и положить в repo актуальные manager-side docs;
- убедиться, что `README_MANAGERBOT_V1.md` больше не содержит V1-ролей beyond `OWNER` / `MANAGER`;
- зафиксировать single operator org per deployment;
- зафиксировать separate manager session state;
- зафиксировать `core.quote_cases` как V1 anchor;
- зафиксировать `ops.*` как baseline-required schema layer.

### Must produce
- единый docs package без противоречий;
- больше нет двусмысленности по:
  - ролям,
  - source of truth,
  - baseline/optional границе,
  - queue derivation,
  - reply flow ownership.

### Exit criteria
- docs можно отдавать в кодинг без постоянных “а что тут имелось в виду”.

**Примечание:** по факту этот этап уже выполнен текущей документной волной. В code PR stream он нужен только как reference checkpoint.

---

## MB1 — Baseline ops schema and stable public identifiers

### Purpose
Подготовить baseline persistence, без которого ManagerBot нельзя строить всерьёз.

### Scope

#### A. Core additions
- добавить `core.quote_cases.display_number`;
- добавить `core.orders.display_number`;
- закрепить unique/index contracts для display numbers.

#### B. Baseline-required `ops.*`
Добавить канонические таблицы из `60_data_model_postgres_managerbot.md`:

- `ops.quote_case_ops_states`
- `ops.quote_case_thread_entries`
- `ops.quote_case_internal_notes`
- `ops.quote_case_assignment_events`
- `ops.manager_presence_states`
- `ops.quote_case_routing_decisions`
- `ops.reply_delivery_attempts`

#### C. Infrastructure alignment
- models;
- repositories;
- seed/reset compatibility;
- canonical baseline DDL update;
- enum registration and naming discipline.

### Must not include
- ManagerBot handlers;
- queue UI;
- reply compose UX;
- AI copilot.

### Exit criteria
- baseline schema уже умеет хранить manager-side truth;
- display numbers persistent;
- no temporary storage excuses remain.

### Why this goes first
Потому что без этого ManagerBot будет читать и писать в полусуществующую реальность.

---

## MB2 — Thread/store refit and customer-side continuity

### Purpose
Убрать самое опасное расхождение: quote-thread как operational surface не должен жить в analytics-ledger логике.

### Scope

#### A. Thread write refit
- customer quote reply/revision/replacement path пишет в `ops.quote_case_thread_entries`;
- analytics event emission сохраняется, но становится secondary/audit concern;
- initial quote/system timeline entries формируются в canonical thread store.

#### B. Thread read refit
- quote detail timeline customer-side читается из thread store;
- thread pagination/read model больше не зависят от ad-hoc event stitching;
- system entries и customer entries собираются в одну нормальную chronology.

#### C. Internal notes separation
- internal notes не попадают в customer detail path;
- customer shell вообще не знает о `ops.quote_case_internal_notes`.

#### D. Continuity protection
- текущий buyer-core quote UX не ломается;
- draft -> quote -> order continuity сохраняется;
- старые seed/demo сценарии обновлены.

### Must include
- migration/refit of quote shell read path;
- compatibility with existing quote creation and revision flows;
- analytics dual-write or event-after-write semantics.

### Must not include
- manager queues;
- manager presence UI;
- SLA dashboards.

### Exit criteria
- quote thread уже живёт там, где должен жить;
- customer-facing quote detail продолжает работать;
- ManagerBot теперь можно строить на реальном source of truth.

### Why this goes before ManagerBot bootstrap
Потому что иначе Telegram manager UI будет спроектирован поверх неправильного thread model и потом получит forced rewrite.

---

## MB3 — Manager operational state, assignment, presence, and routing read model

### Purpose
Сделать очередь и manager workload вычислимыми не “из воздуха”, а из нормальной operational truth.

### Scope

#### A. Ops-state services
- create/update `ops.quote_case_ops_states`;
- reopen/resolve/close transitions;
- waiting-state updates;
- human_requested handling;
- priority/escalation updates.

#### B. Assignment model
- assign / reassign / unassign;
- assignment event persistence;
- current assignee derivation rules.

#### C. Presence model
- online / busy / away / offline;
- last_seen_at / presence_changed_at semantics;
- single-operator org assumptions kept explicit.

#### D. Routing layer
- inbound customer message impact;
- routing decisions persistence;
- new/unassigned/escalated workload classification;
- SLA due derivation.

#### E. Queue read model services
Queue contracts for:
- `new`
- `mine`
- `unassigned`
- `waiting_customer`
- `waiting_team`
- `urgent`
- `escalated`
- `resolved_recent`

### Must not include
- Telegram panel implementation;
- compose UX;
- AI suggestions.

### Exit criteria
- queues можно получать сервисом, а не ручной магией;
- status/waiting/assignment/presence/routing начинают работать вместе;
- source of truth для ManagerBot уже существует.

### Why this still belongs before bot surface
Потому что queue-first ManagerBot бессмысленен без реальных queues.

---

## MB4 — ManagerBot bootstrap surface and separate session state

### Purpose
Поднять отдельный manager-facing Telegram surface, но уже на правильной operational model.

### Scope

#### A. App/module structure
- `app/manager_bot/...` или эквивалентная manager-facing surface structure;
- bootstrap wiring;
- callback namespace isolation;
- dedicated entry router.

#### B. Separate state
- dedicated `ManagerSessionState`;
- отдельный state storage key-space;
- queue context, case context, compose context;
- никакого засовывания manager state в current customer shell session.

#### C. Basic surfaces
- home / hub;
- presence panel;
- queue list;
- queue paging/load more;
- case open;
- deterministic back/home/refresh.

#### D. Access and operator guardrails
- только `OWNER` и `MANAGER`;
- manager-only routes;
- safe fallback on unauthorized access.

### Must not include
- full reply lifecycle;
- advanced SLA handling;
- AI copilot;
- optional group bridge.

### Exit criteria
- менеджер может открыть ManagerBot и увидеть workload;
- queue-first UX уже работает;
- navigation and panel discipline стабильны;
- customer shell не тронут лишним мусором.

### Why this is the first real bot PR
Потому что теперь bot surface не придётся строить на фальшивой модели данных.

---

## MB5 — Case handling actions, reply compose, notes, and delivery tracking

### Purpose
Сделать ManagerBot не просто viewer, а рабочим инструментом обработки кейса.

### Scope

#### A. Case actions
- take case;
- release case;
- set waiting state;
- mark resolved;
- reopen;
- set priority;
- flag human required.

#### B. Compose flows
- compose customer reply;
- compose internal note;
- explicit separation of external vs internal action;
- armed input / cancel / confirm patterns.

#### C. Delivery tracking
- write outbound reply into thread store;
- perform Telegram delivery to customer;
- persist delivery attempts and statuses;
- expose delivery failure / retry visibility.

#### D. Case detail improvements
- manager thread timeline;
- internal notes lane;
- linked artifacts: latest quote revision, source draft, related orders, project/object context.

### Must include
- reliable reply persistence before delivery;
- failure-safe flow;
- notes never leak to customer.

### Must not include
- AI draft suggestion;
- full supervisor dashboards;
- topic bridge.

### Exit criteria
- менеджер может реально вести кейс end-to-end;
- customer reply delivery observable;
- internal note flow безопасен;
- operational state обновляется вместе с reply logic.

### Why this is separate from MB4
Потому что bootstrap surface и real reply lifecycle — это разные уровни риска. Их нельзя склеивать в один жирный PR.

---

## MB6 — Notifications, SLA, escalation, and queue hardening

### Purpose
Довести manager-side contour до эксплуатации несколькими людьми без ручной магии.

### Scope

#### A. Notifications
- new case notification;
- new inbound customer message notification;
- assigned-to-me notification;
- retry/failure notification on delivery.

#### B. SLA
- SLA due calculation policies;
- overdue visibility;
- near-breach signals;
- queue sorting with SLA awareness.

#### C. Escalation
- escalate to owner;
- reopen from resolved/closed according to policy;
- urgent path handling;
- offline/busy manager fallback.

#### D. Queue hardening
- stable ordering rules;
- dedupe protections;
- no phantom cases in queues;
- correct transitions under concurrent updates.

### Must not include
- AI-generated replies sent automatically;
- external supervisor web tooling;
- group topics as source of truth.

### Exit criteria
- manager-side loop становится operationally credible;
- кейсы не теряются молча;
- SLA и escalation больше не являются “потом как-нибудь”.

---

## MB7 — AI copilot for managers

### Purpose
Подключить уже существующий AI layer туда, где он реально приносит value: внутрь manager workflow, а не вместо него.

### Scope
- case summary;
- suggested reply draft;
- missing context detection;
- risk flags;
- retrieval of linked quote/order/project context;
- suggestion-only mode;
- explicit manager review before send.

### Must include
- no autonomous send;
- no open-domain drift;
- AI works only through manager-approved actions.

### Must not include
- AI as primary customer-facing persona;
- silent mutation of quote/order state;
- bypass of deterministic services.

### Exit criteria
- AI saves manager time;
- AI does not become operational liability;
- manager remains accountable actor.

### Why this is not earlier
Потому что AI поверх сырого manager workflow только ускоряет хаос.

---

## MB8 — Optional group topics bridge and release hardening

### Purpose
Добавить optional collaboration shell и закрыть release-level хвосты после того, как primary workflow уже работает.

### Scope

#### A. Optional group bridge
- mirror selected cases into manager group topics;
- post event summaries into topics;
- allow team visibility/escalation discussion;
- no source-of-truth drift to Telegram topics.

#### B. Hardening
- concurrency pass;
- regression suite;
- queue correctness tests;
- delivery retry tests;
- smoke scenarios;
- docs/repo sync.

### Must include
- ability to disable group bridge without breaking manager-side core;
- DB remains primary truth;
- topics are disposable collaboration shell.

### Exit criteria
- collaboration extras do not compromise the architecture;
- ManagerBot wave is releasable.

---

## 8. Recommended implementation order in plain language

Если убрать красивую упаковку, порядок должен быть такой:

1. **Сначала не Telegram manager UI, а data truth.**  
   Иначе потом переделывать всё.

2. **Но это не означает “месяц шлифовать baseline”.**  
   Foundation wave должна быть короткой и строго ограниченной MB1–MB3.

3. **Сразу после этого поднимать ManagerBot surface.**  
   То есть MB4 не откладывать.

4. **Reply flow выделять отдельным PR после bootstrap.**  
   Это самый рискованный кусок, он не должен ехать в одном PR с queue/home/navigation.

5. **AI включать только после реального manager workflow.**  
   Иначе получится умная обёртка над сырой операционкой.

Итого:

```text
MB1 -> MB2 -> MB3 -> MB4 -> MB5 -> MB6 -> MB7 -> MB8
```

Это и есть правильный баланс между:

- “сначала domain truth”,
- “не затягивать до бесконечности”,
- “не строить bot surface на костылях”.

---

## 9. What must not be done during this wave

### 9.1. Не делать отдельную физическую БД под ManagerBot

Нужны общие транзакции, FK и прямые связи с `core.quote_cases`.

### 9.2. Не делать ManagerBot сначала как UI-only слой

Если сначала построить меню, очереди и кейсы без правильной domain truth, потом придётся переписывать и сервисы, и UX.

### 9.3. Не пытаться “завершить весь baseline мира” перед ManagerBot

Нужна только **bounded baseline foundation for manager-domain**, не бесконечная шлифовка всего продукта.

### 9.4. Не смешивать internal notes и customer replies

Это ошибка не только UX, но и trust model.

### 9.5. Не класть manager state в current customer session state

Нужен отдельный `ManagerSessionState`.

### 9.6. Не тянуть AI вперёд operational truth

AI should amplify a working workflow, not compensate for its absence.

---

## 10. Definition of success for the ManagerBot wave

Wave считается успешной, если после MB8:

1. customer thread живёт в нормальном store, а не собирается из полуслучайных источников;
2. manager-side queues вычисляются из canonical ops state, assignment, presence и routing;
3. ManagerBot имеет отдельный Telegram surface и отдельный session state;
4. менеджер может взять кейс, ответить клиенту, оставить internal note, сменить waiting-state и увидеть delivery result;
5. кейсы не теряются в очередях;
6. AI помогает менеджеру, но не становится лицом сервиса;
7. optional group bridge не ломает source-of-truth модель;
8. baseline остаётся чистым и расширяемым, а не превращается в свалку случайных manager-хаков.

---

## 11. Final decision

**Что делаем первым?**

Не “сначала весь baseline”, и не “сначала весь ManagerBot”.

Делаем так:

- **сначала MB1–MB3 как bounded baseline foundation inside TradeFlow**;
- **сразу затем MB4–MB6 как real ManagerBot operational wave**;
- **затем MB7–MB8 как augmentation and hardening wave**.

Это минимизирует риск:

- архитектурного рассинхрона,
- переделки Telegram surface,
- раздувания baseline без результата,
- хаоса с thread/routing/delivery.

Именно этот порядок является canonical для ManagerBot V1.
