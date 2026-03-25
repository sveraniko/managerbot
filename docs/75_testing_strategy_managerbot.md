# 75_testing_strategy_managerbot.md

# ManagerBot V1 Testing Strategy

**Статус:** canonical testing strategy for ManagerBot V1  
**Дата:** 25 March 2026  
**Назначение:** этот документ фиксирует, как именно должен тестироваться manager-side контур TradeFlow V1: какие уровни тестов обязательны, что проверяется до Telegram UI, что проверяется через интеграционные сценарии, какие smoke-сценарии обязательны перед merge и что считается достаточным качеством для боевого запуска.

---

## 1. Зачем нужен этот документ

К этому моменту для ManagerBot уже зафиксированы:

- архитектура;
- доменная модель;
- статусы и routing;
- панели и навигация;
- reply flow;
- PostgreSQL persistence contract;
- PR sequence.

Этого достаточно, чтобы писать код.
Этого **недостаточно**, чтобы писать код безопасно.

ManagerBot V1 затрагивает сразу несколько зон риска:

- baseline database migrations;
- queue/routing/assignment logic;
- separate session state;
- Telegram panel navigation;
- customer-visible reply delivery;
- audit/analytics side effects;
- взаимодействие ManagerBot с existing TradeFlow customer-side flows.

Если testing strategy не зафиксировать заранее, почти гарантированно произойдёт следующее:

1. разработчик проверит только happy-path;
2. Telegram UI будет тестироваться руками, но без системной матрицы;
3. baseline migrations пройдут локально, но развалят совместимость на следующем шаге;
4. queue и routing logic станут зависеть от случайного UI поведения;
5. customer continuity сломается тихо, потому что ManagerBot в первую очередь проверяли "на самом менеджере", а не на полном цикле customer -> manager -> customer.

Этот документ нужен, чтобы тестирование не превращалось в ритуал вида "ну я покликал, вроде живо".

---

## 2. Executive summary

ManagerBot V1 тестируется по четырём слоям:

1. **Domain/service tests**  
   Проверяют инварианты, routing, transitions, assignment, waiting-state, reply lifecycle.

2. **Persistence/integration tests**  
   Проверяют Postgres schema, migrations, repository behavior, FK, enum contracts, read/write consistency.

3. **Telegram application tests**  
   Проверяют panel navigation, callback handling, armed input, session state, permission gating.

4. **Scenario/smoke tests**  
   Проверяют живые end-to-end цепочки на уровне реального бизнес-потока.

Главный принцип V1:

> Максимум логики должно быть проверяемо **без Telegram UI**.

Отсюда следуют жёсткие выводы:

- queue logic не должна жить в handlers;
- routing decision не должен рождаться в callback function;
- reply lifecycle не должен быть размазан по UI и side effects;
- Telegram tests не заменяют domain tests;
- ручной smoke нужен всегда, но не вместо автоматических тестов.

---

## 3. Главные testing goals

Testing strategy должна гарантировать следующее.

### 3.1. Baseline integrity

После добавления manager-side слоя:

- baseline TradeFlow поднимается без optional modules;
- `ops.*` schema создаётся штатно;
- existing customer-side flows не ломаются;
- AI layer может быть выключен без влияния на manager baseline;
- vertical modules остаются независимыми.

### 3.2. Manager operational correctness

Должно быть гарантировано, что:

- кейс корректно попадает в queue;
- assignment, waiting-state и priority работают детерминированно;
- routing не создаёт дубликаты и не теряет кейс;
- internal notes никогда не утекут в customer-visible thread;
- manager reply не смешивается с audit-only event stream.

### 3.3. Customer continuity

Нужно гарантировать, что customer-side experience не распадается после manager refit:

- customer видит свою переписку по quote-case;
- manager reply действительно доходит и сохраняется;
- customer comment продолжает появляться в thread/timeline;
- quote detail не зависит от analytics ledger как primary source.

### 3.4. Telegram surface stability

Нужно гарантировать, что:

- single-panel discipline не ломается;
- `Back` ведёт туда, куда ожидается;
- armed text input не захватывает чужие сообщения;
- stale callbacks не ломают session;
- queue refresh и load-more не размножают state хаос.

### 3.5. Recovery and failure visibility

Нужно гарантировать, что:

- failed delivery видна;
- manager не теряет draft/reply context;
- case не исчезает из operational queues при delivery failure;
- routing и presence не делают кейс orphaned.

---

## 4. Test pyramid for ManagerBot V1

Рекомендуемое распределение усилий:

### 4.1. Unit/domain tests — основной слой

На этот слой должен приходиться основной объём тестирования.

Почему:

- бизнес-логика manager-side в первую очередь живёт в services/use-cases;
- это самый быстрый и дешёвый слой;
- именно здесь ловятся неправильные transitions, assignment collisions, leaking notes и broken routing rules.

Что должно быть покрыто здесь:

- status transitions;
- waiting-state transitions;
- assignment rules;
- presence-aware routing;
- case escalation rules;
- reply lifecycle state machine;
- internal note invariants;
- display number behavior, если логика распределения реализована в приложении;
- idempotency/replay safety для critical operations.

### 4.2. Integration tests with Postgres — обязательный слой

Это второй по важности слой.

Потому что для ManagerBot V1 schema и FK столь же критичны, как и доменная логика.

Что должно проверяться здесь:

- migrations apply cleanly from baseline;
- enum contracts соответствуют документам;
- FK не позволяют битых ссылок;
- delete/update behavior совпадает с контрактом;
- thread entries, notes, ops state и assignment history сохраняются и читаются согласованно;
- `core.quote_cases` и `ops.*` работают как единый контур.

### 4.3. Application/Telegram tests — выборочный, но обязательный слой

Здесь не нужно пытаться покрыть все кнопки мира.
Но этот слой нужен, чтобы проверить:

- panel routing;
- callback namespace;
- state handoff между panels;
- armed input behavior;
- role/permission gating;
- stale callback safety;
- safe refresh/back/home semantics.

### 4.4. Manual smoke scenarios — обязательны перед merge в manager wave

Никакие тесты не отменяют реальный walkthrough.

Причина проста:

- Telegram UX слишком легко формально проходит тесты и одновременно раздражает живого оператора;
- многие баги рождаются не в domain logic, а в стыке state + panel + delivery + race timing.

---

## 5. Scope by test layer

### 5.1. Что должно тестироваться unit/domain tests

#### A. Case status transitions

Нужно проверить:

- `new -> assigned`
- `new -> waiting_customer`
- `assigned -> waiting_customer`
- `assigned -> escalated`
- `waiting_customer -> assigned`
- `assigned -> resolved`
- `resolved -> closed`
- invalid transitions reject

Отдельно:

- direct `new -> closed` без explicit policy должен быть запрещён;
- `closed` case не должен принимать manager reply без reopen/restate policy;
- `resolved` и `closed` не должны смешиваться.

#### B. Waiting state rules

Нужно проверить:

- `waiting_manager`
- `waiting_customer`
- `waiting_internal`
- `none`

Их смена должна происходить детерминированно от событий:

- customer message;
- manager reply;
- internal note;
- assignment;
- escalation;
- manual state change.

#### C. Assignment behavior

Нужно проверить:

- assign unassigned case;
- reassign assigned case;
- owner can reassign;
- manager cannot steal case, если policy запрещает;
- idempotent reassign to same assignee;
- unassign flow;
- assignment history append correctness.

#### D. Presence-aware routing

Нужно проверить:

- manager available;
- manager busy;
- manager offline;
- no available manager;
- owner fallback;
- unchanged routing when event is duplicate;
- routing priority for human-requested case.

#### E. Thread and note invariants

Нужно проверить:

- external thread entry always customer-visible by contract;
- internal note never leaks into external thread read model;
- note creation does not alter delivery state;
- manager reply creates delivery attempt;
- customer inbound message never becomes internal note.

#### F. Reply lifecycle

Нужно проверить:

- draft created;
- draft confirmed;
- thread entry persisted;
- delivery attempt created;
- delivery marked sent/failed;
- retry path;
- no duplicate send on repeated callback;
- aborted compose flow leaves no half-persisted entry.

#### G. Queue projection logic

Нужно проверить:

- `New`
- `Assigned to me`
- `Unassigned`
- `Waiting for me`
- `Waiting for customer`
- `Urgent`
- `Escalated`

И отдельно:

- case appears only in logically valid queues;
- queue counts reflect persisted state;
- stale projection refreshes cleanly.

### 5.2. Что должно тестироваться integration tests

#### A. Migration integrity

Проверить:

- baseline DB -> apply manager migrations;
- no dependency on optional vertical migration;
- repeatable local bootstrap;
- clean downgrade policy, если она в проекте используется;
- schema creation order valid.

#### B. Repository correctness

Проверить:

- create/read/update `ops.quote_case_ops_states`;
- append/read `ops.quote_case_thread_entries`;
- append/read `ops.quote_case_internal_notes`;
- append/read `ops.quote_case_assignment_events`;
- upsert/read `ops.manager_presence_states`;
- append/read `ops.quote_case_routing_decisions`;
- append/update `ops.reply_delivery_attempts`.

#### C. Cross-schema consistency

Проверить:

- `ops.*` rows always link to existing `core.quote_cases`;
- assignment actor ids resolve to allowed system actors;
- deleting quote-case policy behaves as designed;
- order linkage and quote linkage remain coherent.

#### D. Read model continuity

Проверить:

- customer quote detail thread builds from new storage;
- manager case detail timeline builds from same truth plus internal notes;
- analytics emission may lag, but read model remains correct;
- no dependency on `audit.analytics_events` for main timeline.

### 5.3. Что должно тестироваться Telegram application tests

#### A. Access control

Проверить:

- `MANAGER` can enter ManagerBot;
- `OWNER` can enter ManagerBot;
- non-manager roles rejected;
- company-scoped customer user cannot access manager panels.

#### B. Navigation

Проверить:

- Home -> Queue -> Case -> Reply -> Confirm -> Case;
- Home -> Queue -> Case -> Note -> Case;
- Back semantics from every compose/confirm panel;
- Refresh does not duplicate panel stack;
- Home resets queue context safely.

#### C. Armed input behavior

Проверить:

- armed reply captures next valid text;
- random text outside armed state ignored safely;
- stale armed state expires or is safely cancelled;
- file/media input handling follows defined policy;
- wrong input type produces deterministic response.

#### D. Callback robustness

Проверить:

- stale callback after session reset;
- repeated callback click;
- callback for case not visible anymore;
- callback after reassignment;
- callback on already closed/resolved case.

---

## 6. Scenario-based smoke matrix

Ниже минимальный набор сценариев, который должен проходить перед merge крупных manager PR и перед пилотным запуском.

### 6.1. Scenario S1 — customer asks, case appears, manager replies

1. Customer creates/updates quote-case.
2. Customer sends comment/question.
3. Thread entry persists.
4. Ops state updates to waiting for manager.
5. Queue count changes.
6. Manager opens queue and case.
7. Manager writes reply.
8. Reply persists.
9. Delivery attempt created and marked sent.
10. Customer sees reply in quote detail.

### 6.2. Scenario S2 — manager writes internal note

1. Manager opens case.
2. Manager adds internal note.
3. Note persists.
4. Note appears in manager timeline.
5. Note does not appear in customer thread.
6. No customer delivery attempt created.

### 6.3. Scenario S3 — assignment and reassignment

1. New case appears unassigned.
2. Manager A takes case.
3. Assignment history created.
4. Owner reassigns case to Manager B.
5. Queue membership updates.
6. Old manager no longer sees case in `Assigned to me`.
7. New manager sees correct case state.

### 6.4. Scenario S4 — delivery failure and retry

1. Manager composes reply.
2. Thread entry persists.
3. Delivery attempt fails.
4. Case remains visible.
5. Manager sees failure status.
6. Retry succeeds or creates explicit second attempt.
7. No duplicate customer-visible thread corruption occurs.

### 6.5. Scenario S5 — presence-aware routing

1. Multiple managers exist.
2. One offline, one busy, one available.
3. New customer message enters.
4. Routing selects valid target.
5. Routing decision logged.
6. Queue placement matches routing result.

### 6.6. Scenario S6 — stale callback safety

1. Manager opens case.
2. Case is reassigned or closed elsewhere.
3. Manager clicks old button.
4. Bot rejects action safely.
5. Session remains healthy.
6. Fresh panel can be loaded.

### 6.7. Scenario S7 — customer continuity after refit

1. Existing customer quote-case data present.
2. Customer opens quote detail after manager migrations.
3. Timeline renders correctly.
4. New manager reply appears.
5. New customer message appears.
6. No reliance on old analytics-only thread path.

---

## 7. Baseline regression strategy

Поскольку manager-side является baseline-required, testing strategy должна отдельно защищать baseline.

### 7.1. Что считается baseline regression

Любая из следующих проблем считается блокирующей:

- приложение не поднимается без optional modules;
- migrations требуют vertical module order;
- existing customer quote flow ломается;
- existing order flow ломается;
- AI-off mode перестаёт работать;
- baseline bot startup зависит от manager Telegram surface readiness.

### 7.2. Обязательные regression checks

После каждого manager baseline PR должны проходить:

- bootstrap app from baseline;
- customer quote create/open/update flow;
- customer comment persistence;
- quote detail render;
- order creation path, если связан с quote-case;
- startup with AI layer disabled.

---

## 8. Data correctness and observability checks

Тестирование ManagerBot V1 не ограничивается только "работает/не работает".
Нужно проверять ещё и наблюдаемость.

### 8.1. Что должно быть наблюдаемо

- case created / updated;
- customer message persisted;
- assignment changed;
- routing decided;
- manager reply persisted;
- delivery attempt sent/failed;
- note added;
- presence changed.

### 8.2. Что нужно проверять в тестах

- audit events пишутся без влияния на primary flow;
- correlation ids сохраняются, если такая модель есть в коде;
- failed side effects не ломают primary transaction, если policy требует decoupling;
- logs позволяют понять, почему case попал в queue.

Главное правило:

> audit и analytics проверяются как secondary observability layer, а не как primary business truth.

---

## 9. Non-functional testing focus

Для ManagerBot V1 не нужен enterprise performance theater.
Но некоторые non-functional проверки обязательны.

### 9.1. Concurrency / race conditions

Нужно проверить хотя бы на базовом уровне:

- два менеджера пытаются взять один кейс;
- двойной клик по кнопке `Send`;
- повторное нажатие `Assign to me`;
- customer sends message while manager is in compose flow;
- reassignment происходит одновременно с reply confirm.

### 9.2. Pagination / list stability

Нужно проверить:

- queue list page 1 -> load more -> open case -> back;
- queue refresh после появления новых кейсов;
- сохранение/сброс queue filters по контракту session state;
- отсутствие дублей после refresh.

### 9.3. Data volume sanity

Не нужен экстремальный load-test, но нужен sanity test:

- десятки/сотни кейсов в queues;
- длинные timelines;
- repeated assignment history;
- multiple delivery attempts.

Цель не в benchmark-рекордах, а в том, чтобы UI и query model не схлопнулись при первой же живой эксплуатации.

---

## 10. Test environments

### 10.1. Локальная developer среда

Нужна для:

- unit tests;
- integration tests against local Postgres;
- basic Telegram interaction checks.

### 10.2. Dedicated pre-merge environment

Желательно иметь среду, где можно:

- накатывать baseline + manager migrations;
- проверять реальный bot token / test chat behavior;
- прогонять smoke matrix без риска для prod-like данных.

### 10.3. Pilot environment

Перед реальным боевым использованием нужен хотя бы ограниченный пилотный контур:

- 1 owner;
- 1-2 managers;
- test customer accounts;
- реальные quote-case сценарии;
- проверка delivery, routing и navigation на живых руках.

---

## 11. Merge gates by PR wave

### 11.1. Для MB1-MB3 (baseline foundation wave)

Merge запрещён, если не прошли:

- migrations integration tests;
- domain tests по transitions/routing/assignment;
- customer continuity regression;
- baseline bootstrap checks.

### 11.2. Для MB4-MB5 (ManagerBot surface wave)

Merge запрещён, если не прошли:

- Telegram navigation tests;
- armed input tests;
- reply flow scenario tests;
- stale callback safety checks;
- smoke scenarios S1-S4.

### 11.3. Для MB6-MB8 (hardening/AI/optional bridge)

Merge запрещён, если не прошли:

- SLA/escalation tests;
- AI copilot non-autonomy checks;
- optional bridge isolation checks;
- full smoke matrix.

---

## 12. Что не надо делать

### 12.1. Не заменять domain tests ручным кликаньем

Telegram smoke нужен, но он не должен быть единственным способом понять, жива ли логика.

### 12.2. Не тестировать thread через analytics как source of truth

Если timeline отрисовывается из `audit.analytics_events`, тесты будут подтверждать неправильную архитектуру.

### 12.3. Не прятать критичную manager logic в handlers

Если логика сидит в Telegram handlers, она хуже тестируется и быстрее разлагается.

### 12.4. Не откладывать regression baseline checks "на потом"

ManagerBot baseline-required. Значит baseline regressions должны ловиться сразу.

### 12.5. Не считать AI tests достаточными для manager correctness

AI copilot — это assist layer.
Primary correctness — это routing, state, persistence, delivery.

---

## 13. Recommended initial test pack for first implementation wave

Минимум, который должен быть написан уже в первых PR:

1. **Domain tests**
   - transitions
   - assignment
   - routing
   - waiting-state
   - reply lifecycle

2. **Integration tests**
   - migrations baseline -> manager
   - repository CRUD for all `ops.*` tables
   - customer thread continuity via new storage

3. **Telegram tests**
   - access gating
   - Home/Queue/Case navigation
   - reply compose/confirm flow
   - stale callback rejection

4. **Smoke checklist**
   - S1
   - S2
   - S3
   - S4
   - S7

Если этого пакета нет, значит PR foundation ещё сырой.

---

## 14. Exit criteria for ManagerBot V1 testing readiness

ManagerBot V1 можно считать тестово готовым к пилотному запуску только если выполнены все условия:

- baseline migrations проходят с нуля;
- customer continuity подтверждена;
- `ops.*` persistence работает согласно contract;
- queue/routing/assignment logic покрыта domain tests;
- reply flow покрыт integration + Telegram tests;
- stale callback и retry paths проверены;
- smoke matrix пройдена руками;
- AI layer можно выключить без поломки manager contour.

Итоговая формула простая:

> ManagerBot V1 считается готовым не тогда, когда "бот открывается", а тогда, когда подтверждён полный operational loop: customer -> DB truth -> manager queue -> manager action -> customer-visible result.

Именно этот loop и должен быть главным объектом тестирования.

