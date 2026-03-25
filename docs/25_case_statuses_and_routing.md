# 25_case_statuses_and_routing.md

# ManagerBot Case Statuses and Routing V1

**Статус:** canonical status/routing contract for ManagerBot V1  
**Дата:** 25 March 2026  
**Назначение:** этот документ фиксирует канонические manager-side статусы, waiting-state, priority, escalation, presence и routing rules для `quote_case` в рамках ManagerBot V1.

---

## 1. Зачем нужен этот документ

`README_MANAGERBOT_V1.md`, `10_architecture_managerbot.md` и `20_domain_model_manager_cases.md` уже зафиксировали базу:

- ManagerBot = primary workspace для внутренних операторов;
- V1 опирается на existing `core.quote_cases`;
- commercial lifecycle и manager operational state не смешиваются;
- source of truth живёт в PostgreSQL, а не в Telegram и не в analytics ledger;
- роли V1 = только `OWNER` и `MANAGER`;
- V1 assumes single operator org per deployment;
- manager session state отдельный от customer shell.

Этого недостаточно, чтобы писать код.

На этапе реализации всегда возникает один и тот же бардак:

- кто-то пытается превратить operational status в “универсальный жизненный цикл всего”;
- кто-то хочет пихнуть `urgent` или `waiting_customer` в `quote_cases.status`;
- кто-то решает, что assignment можно держать “просто текущим полем” без нормального routing contract;
- кто-то считает, что очереди можно собрать “как-нибудь в UI”.

Этот документ нужен, чтобы дальше не заниматься археологией по собственным же PR.

---

## 2. Executive summary

В V1 manager-side handling строится вокруг **четырёх отдельных измерений состояния**, а не вокруг одного magical status field:

1. **Commercial status**  
   Живёт в существующем `core.quote_cases.status` и описывает коммерческий lifecycle quote.

2. **Operational status**  
   Живёт в `QuoteCaseOpsState.operational_status` и описывает manager-side handling state.

3. **Waiting state**  
   Живёт в `QuoteCaseOpsState.waiting_state` и отвечает на вопрос: **кто сейчас должен сделать следующий meaningful step**.

4. **Assignment / presence / escalation overlays**  
   Живут рядом и влияют на очередь, приоритет и routing, но не заменяют собой operational status.

Ключевое правило:

> В V1 очереди ManagerBot не хранятся как отдельные сущности.  
> Очереди вычисляются из `QuoteCaseOpsState`, assignment, priority, escalation и presence.

Базовая формула:

```text
Queue placement
= f(
    operational_status,
    waiting_state,
    assigned_manager_actor_id,
    priority,
    escalation_level,
    human_requested,
    sla_due_at,
    manager presence
  )
```

---

## 3. Что не является статусом

Это нужно прибить отдельно, потому что именно здесь обычно и начинается цирк.

Следующие вещи **не являются operational status**:

- `assigned`
- `unassigned`
- `urgent`
- `escalated`
- `mine`
- `waiting_for_me`
- `waiting_for_customer`
- `new_message`
- `sla_overdue`

Почему:

- `assigned/unassigned` выводятся из поля assignment;
- `urgent` выводится из `priority`;
- `escalated` выводится из `escalation_level`;
- `mine` и `waiting_for_me` это queue/read model, а не доменное состояние;
- `new_message` это routing trigger, а не state;
- `sla_overdue` это derived operational signal.

Если засунуть всё это в один enum, дальше система начинает объяснять сама себе, в каком именно виде она сломалась.

---

## 4. Канонические измерения состояния

### 4.1. Commercial status

Commercial status в V1 **не меняется этим документом**.

Он остаётся в existing `core.quote_cases.status` и отвечает на коммерческие вопросы:

- quote открыт или завершён;
- архивирован или активен;
- может ли из него быть создан order;
- должен ли он быть виден customer-side как активный quote case.

ManagerBot не должен перепридумывать этот lifecycle.

---

### 4.2. Operational status

#### Canonical enum V1

`QuoteCaseOpsState.operational_status` принимает только следующие значения:

- `new`
- `active`
- `waiting`
- `resolved`
- `closed`

#### Смысл значений

##### `new`

Кейс стал manager-visible workload, но ещё не был нормально принят в работу.

Типовые причины:

- создан новый `quote_case`;
- пришло первое customer message в новый кейс;
- кейс восстановлен после миграции/repair job;
- routing layer пометил кейс как требующий первичной triage.

Смысл:

- кейс существует;
- он должен попасть в queue;
- над ним ещё не совершено нормальное manager-side принятие в работу.

##### `active`

Кейс находится в активной обработке.

Смысл:

- менеджерский контур уже “взял” кейс;
- по нему выполняется работа;
- кейс не ждёт внешнего участника как primary blocker;
- следующий meaningful step находится внутри operator-side handling.

Это не обязательно означает, что менеджер прямо сейчас печатает ответ.
Это означает, что кейс находится на стороне команды, а не на стороне клиента.

##### `waiting`

Кейс временно остановлен, потому что следующий шаг ожидается не от routing layer, а от определённого участника.

Смысл waiting задаётся **не самим статусом**, а через `waiting_state`.

Почему не делать `waiting_customer`, `waiting_manager`, `waiting_owner` отдельными status:
потому что это один и тот же класс состояния “временная пауза в активной обработке”, но с разными blockers.

##### `resolved`

С точки зрения manager-side операционки кейс доведён до результата.

Типовые варианты:

- клиент получил итоговый ответ;
- подготовлена актуальная коммерческая версия;
- customer question закрыт;
- кейс завершён без необходимости дальнейшего operator action.

`resolved` не означает, что quote обязательно archived/closed по коммерческому lifecycle.
Он означает, что manager-side active handling завершён.

##### `closed`

Manager-side handling окончательно закрыт и не должен возвращаться в обычные рабочие очереди без явного reopen trigger.

Типовые причины:

- коммерческий кейс действительно закрыт и больше не требует сопровождения;
- кейс архивирован;
- кейс объединён/заменён другим canonical case;
- кейс завершён owner decision.

`closed` — это operational terminal state.

---

### 4.3. Waiting state

#### Canonical enum V1

`QuoteCaseOpsState.waiting_state` принимает только следующие значения:

- `none`
- `customer`
- `manager`
- `owner`
- `system`

#### Смысл значений

##### `none`

У кейса нет explicit blocker.
Он либо `new`, либо `active`, либо `resolved/closed`.

##### `customer`

Следующий meaningful step должен сделать клиент.

Примеры:

- ожидается ответ клиента;
- ожидается подтверждение revision;
- ожидается уточнение параметров;
- ожидается реакция на отправленное предложение.

##### `manager`

Следующий meaningful step должен сделать назначенный менеджер.

Примеры:

- требуется подготовить revision;
- нужно сверить availability/price;
- нужно ответить клиенту;
- нужно проверить вложения или документы;
- требуется ручная обработка после AI suggestion.

##### `owner`

Кейс ждёт решения owner.

Примеры:

- нужен override;
- нужен approve по условиям;
- нужна эскалация цены/коммерческого решения;
- кейс выходит за рамки полномочий менеджера.

##### `system`

Следующий шаг заблокирован системным/техническим состоянием.

Примеры:

- failed delivery;
- broken integration;
- pending repair/retry job;
- inconsistent data, требующая repair flow.

#### Главный принцип

`waiting_state` задаёт **blocker owner**, а не просто красивую подпись в панели.

---

### 4.4. Priority

#### Canonical enum V1

`QuoteCaseOpsState.priority`:

- `normal`
- `high`
- `urgent`

#### Смысл

Priority отвечает только на вопрос:

**насколько быстро кейс должен быть поднят в очереди относительно других кейсов того же класса.**

Priority не заменяет operational status и не определяет assignment.

#### Примерные триггеры повышения priority

- customer explicitly requested human attention;
- owner manually raised priority;
- кейс связан с уже существующим order risk;
- есть SLA risk;
- есть repeated customer contact без ответа;
- есть delivery failure на важном исходящем сообщении.

---

### 4.5. Escalation level

#### Canonical enum V1

`QuoteCaseOpsState.escalation_level`:

- `none`
- `manager_attention`
- `owner_attention`

#### Смысл

Escalation отвечает на вопрос:

**какой уровень вмешательства требуется для кейса сверх обычной обработки.**

В V1 этого достаточно.
Не надо плодить “critical / supervisor / legal / finance / director / cosmic council”.

#### Примеры

- `none` — кейс обрабатывается штатно;
- `manager_attention` — кейс требует ускоренного ручного внимания, но не owner-level решения;
- `owner_attention` — кейс требует owner decision или owner visibility.

---

### 4.6. Human requested flag

`QuoteCaseOpsState.human_requested: bool`

Это отдельный сигнал.

Он отвечает на вопрос:

**нужно ли гарантированное участие человека в кейсе, независимо от других эвристик.**

Источники:

- клиент попросил живого менеджера;
- customer UI explicitly routed to human help;
- AI layer confidence insufficient и эскалировал в human path;
- owner/manager вручную пометил кейс.

Это не status, не priority и не escalation.
Но этот флаг должен влиять на routing и queue sorting.

---

### 4.7. Assignment

В V1 assignment хранится в `QuoteCaseOpsState.assigned_manager_actor_id`.

Важные правила:

- отсутствие assignment не означает `closed`;
- наличие assignment не означает `active`;
- `assigned_manager_actor_id = null` допустим только для `new` и части `active`/`waiting` кейсов, если routing policy это позволяет;
- owner может быть assignee;
- `assignment history` живёт в отдельной event-сущности, current assignee живёт в snapshot.

---

### 4.8. Manager presence

#### Canonical enum V1

`ManagerPresenceState.presence_status`:

- `online`
- `busy`
- `offline`

#### Смысл

Presence влияет на routing, но **не переписывает уже сохранённый case state**.

##### `online`

Менеджер доступен для новых кейсов и ручной обработки.

##### `busy`

Менеджер работает, но не должен получать новые кейсы по auto-routing, если есть доступные альтернативы.

##### `offline`

Менеджер не должен считаться доступным для auto-routing.

Presence — это routing input, а не case status.

---

## 5. Разрешённые комбинации состояния

Не все сочетания допустимы.

### 5.1. Допустимые пары `operational_status` + `waiting_state`

#### `new`

Допустимо только с:

- `none`
- `manager`
- `owner`

Не должно быть:

- `customer` — новый кейс не может ожидать клиента до первичного triage;
- `system` — если кейс сломан системно, он уже должен быть поднят в `active` или `waiting/system` после фиксации проблемы.

#### `active`

Допустимо только с:

- `none`
- `manager`
- `owner`

Не должно быть:

- `customer` — если primary blocker клиент, это уже `waiting/customer`;
- `system` — если primary blocker система, это уже `waiting/system`.

#### `waiting`

Допустимо только с:

- `customer`
- `manager`
- `owner`
- `system`

Не должно быть:

- `none`

#### `resolved`

Допустимо только с:

- `none`

#### `closed`

Допустимо только с:

- `none`

---

### 5.2. Допустимость assignment по статусам

#### `new`

- `assigned_manager_actor_id` может быть `null`
- может быть назначен сразу owner/manager при manual triage

#### `active`

- assignment желателен почти всегда
- `null` допускается только как краткое transitional состояние во время reassign/repair, но не как steady-state policy

#### `waiting/customer`

- assignment должен сохраняться
- кейс должен оставаться закреплён за ответственным человеком

#### `waiting/manager`

- assignment обязателен

#### `waiting/owner`

- assignment может оставаться на менеджере с owner escalation
- либо быть напрямую переведён на owner, если policy такова
- это уже routing policy, а не доменный запрет

#### `resolved`

- assignment может сохраняться для audit/read model
- active handling больше не требуется

#### `closed`

- assignment может сохраняться исторически
- routing на него не производится

---

## 6. Канонические переходы статусов

Ниже перечислены допустимые high-level transitions.

### 6.1. `new -> active`

Триггеры:

- менеджер/owner открыл кейс и принял его в работу;
- auto-triage successfully assigned case;
- кейс требует operator-side действия и обработка начата.

### 6.2. `new -> waiting/owner`

Триггеры:

- первичный triage сразу выявил owner-only decision;
- кейс требует ручного approve вне менеджерских полномочий.

### 6.3. `new -> closed`

Допускается редко.

Только если:

- кейс технически дубль;
- кейс признан невалидным и закрыт owner decision;
- migration/repair flow схлопнул его в другой canonical case.

Обычным маршрутом `new` не должен сразу превращаться в `closed`.

### 6.4. `active -> waiting/customer`

Триггеры:

- отправлен вопрос клиенту;
- отправлено предложение и ожидается реакция;
- требуется уточнение, подтверждение, фото, параметры, выбор варианта.

### 6.5. `active -> waiting/manager`

Триггеры:

- менеджер сам отложил кейс на внутреннее выполнение;
- нужно подготовить revision или документы;
- идёт ручная сверка с каталогом, availability, ценой или условиями.

### 6.6. `active -> waiting/owner`

Триггеры:

- кейс поднят на owner decision;
- требуется approve/override/exception.

### 6.7. `active -> waiting/system`

Триггеры:

- failed delivery;
- broken dependency;
- inconsistent data, требующая repair/retry job.

### 6.8. `active -> resolved`

Триггеры:

- manager-side задача выполнена;
- клиент получил финальный meaningful answer;
- operator handling завершён.

### 6.9. `waiting/* -> active`

Триггеры:

- blocker снят;
- клиент ответил;
- owner дал решение;
- system repair завершён;
- менеджер вернулся к кейсу после внутреннего ожидания.

### 6.10. `waiting/* -> resolved`

Допускается, если кейс может быть завершён без возврата в `active`.

Пример:

- клиент отменил запрос;
- owner дал окончательное решение и кейс больше не требует действий;
- system retry показал, что дальнейшая обработка не нужна.

### 6.11. `resolved -> active`

Триггеры reopen:

- новый customer message;
- owner reopen;
- повторный вопрос по тому же кейсу;
- failed post-resolution delivery correction;
- AI/manual audit обнаружил, что кейс был закрыт преждевременно.

### 6.12. `resolved -> closed`

Триггеры:

- lifecycle кейса окончательно завершён;
- owner/manual archival;
- case retention policy.

### 6.13. `closed -> active`

Разрешено только через explicit reopen action.

Обычные routing events не должны автоматически воскрешать `closed` кейс без явного правила.

---

## 7. Routing triggers

Routing не случается “вообще”.
Он всегда происходит по конкретному trigger.

### Canonical routing triggers V1

- `quote_case_created`
- `customer_message_received`
- `manager_message_saved`
- `manager_reply_delivery_failed`
- `manager_reply_delivery_succeeded`
- `assignment_changed`
- `presence_changed`
- `owner_escalated`
- `owner_deescalated`
- `sla_due_reached`
- `sla_overdue_reached`
- `human_requested`
- `case_reopened`
- `repair_job_completed`
- `manual_refresh`

---

## 8. Routing reasons

Routing reason должен быть сохранён в `QuoteCaseRoutingDecision`.
Он отвечает на вопрос:

**почему система или оператор положили кейс именно в это состояние/очередь.**

### Canonical enum V1

- `new_case`
- `new_customer_signal`
- `await_customer`
- `await_manager_work`
- `await_owner_decision`
- `await_system_repair`
- `human_requested`
- `delivery_failure`
- `reassigned_due_presence`
- `owner_manual_override`
- `sla_risk`
- `sla_overdue`
- `reopened`
- `manual_triage`
- `manual_requeue`
- `repair_completed`

---

## 9. Канонические queue views

В V1 очереди — это **derived read models**.

### 9.1. `New`

Логика:

- `operational_status = new`
- `closed/resolved` исключены

Назначение:
- первичная triage-очередь

### 9.2. `Unassigned`

Логика:

- `assigned_manager_actor_id is null`
- `operational_status in (new, active, waiting)`

Назначение:
- кейсы без владельца

### 9.3. `Assigned to me`

Логика:

- `assigned_manager_actor_id = current_actor_id`
- `operational_status in (new, active, waiting)`

Фильтрация/сортировка уже может разбивать это на подвиды.

### 9.4. `Waiting for me`

Логика:

- `assigned_manager_actor_id = current_actor_id`
- и один из вариантов:
  - `operational_status in (new, active)` с `waiting_state in (none, manager, owner)` в зависимости от policy
  - либо `operational_status = waiting and waiting_state = manager`

Для V1 рекомендовано читать это так:

> все кейсы текущего менеджера, по которым следующий operator-side meaningful step ожидается от него или должен быть им инициирован.

### 9.5. `Waiting for customer`

Логика:

- `operational_status = waiting`
- `waiting_state = customer`

### 9.6. `Urgent`

Логика:

- `priority = urgent`
- и `operational_status not in (resolved, closed)`

### 9.7. `Escalated`

Логика:

- `escalation_level != none`
- и `operational_status not in (resolved, closed)`

### 9.8. `SLA at risk`

Логика:

- `sla_due_at is not null`
- `now() >= sla_due_at - configured_warning_window`
- ещё не overdue

### 9.9. `SLA overdue`

Логика:

- `sla_due_at is not null`
- `now() > sla_due_at`
- `operational_status not in (resolved, closed)`

---

## 10. Routing policy V1

### 10.1. Общий принцип

Routing V1 должен быть **простым, детерминированным и объяснимым**.

Нельзя строить black-box распределение кейсов с первого релиза.
ManagerBot должен быть предсказуемым для owner и менеджеров.

### 10.2. Базовые правила распределения

#### Правило 1. Новый кейс

При `quote_case_created`:

- создаётся `QuoteCaseOpsState`, если его ещё нет;
- выставляется `operational_status = new`;
- `waiting_state = none` или `manager` по реализации triage;
- assignment может быть пустым;
- priority по умолчанию `normal`.

#### Правило 2. Новое сообщение клиента

При `customer_message_received`:

- создаётся external thread entry;
- обновляется `last_customer_message_at`;
- если кейс был `resolved`, он reopen'ится в `active`;
- если кейс был `waiting/customer`, он переводится в `active`;
- если assignment пустой, кейс попадает в `new` или `active/unassigned` согласно policy;
- если assignment есть, кейс возвращается в очередь текущего владельца;
- `human_requested=true` усиливает priority/escalation, но не ломает остальную модель.

#### Правило 3. Сообщение менеджера клиенту

При `manager_message_saved`:

- создаётся external thread entry;
- обновляется `last_manager_message_at`;
- если сообщение предполагает ответ клиента, кейс переводится в `waiting/customer`;
- если сообщение завершает обработку, допускается `resolved`;
- если сообщение — только промежуточное уведомление, кейс может остаться `active`.

#### Правило 4. Failed delivery

При `manager_reply_delivery_failed`:

- кейс получает `waiting/system` либо `active + escalation`, в зависимости от характера ошибки;
- priority поднимается минимум до `high`;
- создаётся delivery attempt;
- кейс не должен тихо “исчезнуть”.

#### Правило 5. Presence change

При `presence_changed`:

- новые кейсы не должны автоматически сыпаться на `busy/offline` менеджеров;
- уже назначенные кейсы не обязаны немедленно переезжать;
- reassign допускается по manual action owner/manager или по отдельному explicit rebalance policy;
- V1 не должен делать агрессивный auto-rebalance.

#### Правило 6. Owner escalation

При `owner_escalated`:

- `escalation_level = owner_attention`;
- при необходимости `waiting_state = owner`;
- SLA может быть ужат;
- кейс обязан стать видимым owner.

---

### 10.3. Рекомендуемая политика auto-routing V1

Для V1 рекомендована **консервативная политика**:

- не делать сложный balancing engine;
- не учитывать десятки эвристик;
- не перераспределять кейсы автоматически при каждом чихе.

Практически:

1. Новый кейс:
   - либо остаётся unassigned,
   - либо назначается доступному manager по простому правилу.

2. Если assigned manager = `offline`:
   - кейс не пропадает;
   - owner видит его как risk;
   - manual reassign остаётся основным механизмом.

3. Если assigned manager = `busy`:
   - кейс остаётся назначенным;
   - новые кейсы по возможности идут не ему.

Это сильно проще, чем имитировать “умный routing”, который потом никто не сможет объяснить.

---

## 11. SLA contract V1

SLA в V1 нужен как operational signal, а не как корпоративный театр.

### 11.1. Что измеряет `sla_due_at`

`sla_due_at` отвечает на вопрос:

**до какого времени кейс должен получить следующий required operator action.**

Это не universal deadline навсегда.
Это текущий operational due point.

### 11.2. Когда SLA обновляется

В V1 рекомендуется обновлять `sla_due_at` при:

- создании нового кейса;
- получении нового customer message;
- owner escalation;
- reopen кейса;
- failed delivery;
- ручном priority override.

### 11.3. Когда SLA можно очищать

Допускается `sla_due_at = null`, если:

- кейс `resolved`;
- кейс `closed`;
- кейс `waiting/customer` и V1 policy не требует отдельного follow-up timer.

Если follow-up нужен, это уже отдельное поле, а не повод ломать базовый SLA contract.

---

## 12. Presence and routing interaction

Presence влияет только на **future routing decisions**, а не переписывает историю.

### `online`

- может получать новые кейсы;
- может оставаться assignee;
- участвует в обычных очередях.

### `busy`

- остаётся видимым владельцем своих кейсов;
- новые auto-assigned кейсы по возможности не идут к нему;
- manual assign допустим.

### `offline`

- не должен получать auto-assigned кейсы;
- его кейсы остаются в системе;
- owner видит operational risk;
- manual reassign допустим.

---

## 13. Reopen contract

Reopen нужен, чтобы избежать тупой схемы “раз кейс был resolved, пусть теперь навсегда мёртв”.

### Reopen triggers V1

- новое сообщение клиента;
- owner/manual reopen;
- повторное обращение по тому же case context;
- correction after failed delivery;
- migration/repair recovery.

### Reopen effect

Рекомендуемый эффект:

- `resolved -> active`
- `waiting_state = manager` или `none`
- `priority` может быть повышен
- `escalation_level` пересчитывается
- `sla_due_at` пересчитывается
- routing reason = `reopened`

---

## 14. Persistence boundary and storage placement

Этот раздел отвечает на практический вопрос, который всегда всплывает при реализации:

**где физически хранить manager-side thread, notes, routing и ops state.**

### Canonical решение V1

Manager-side persistence хранится:

- **в том же TradeFlow deployment**
- **в том же PostgreSQL instance/cluster**
- **в отдельном schema namespace manager-side слоя**
- **не в отдельной физической БД**

Рекомендуемая форма:

```text
core.*      -> customer/commercial domain
manager.*   -> manager-side operational domain
analytics.* -> metrics/event ledger
```

### Почему это правильное решение

#### 1. ManagerBot V1 якорится на `core.quote_cases`

Если вынести manager-side persistence в отдельную физическую БД, ты сразу получишь:

- cross-database consistency pain;
- сложнее миграции;
- сложнее joins/read models;
- сложнее transactional updates;
- выше риск рассинхрона thread/ops/core state.

Для V1 это бессмысленное усложнение.

#### 2. Нужны атомарные обновления

Типовой inbound flow должен уметь в одном logical transaction сделать:

- записать external thread entry;
- обновить `QuoteCaseOpsState`;
- записать routing decision;
- при необходимости записать delivery attempt;
- отправить analytics event.

Это намного надёжнее делать в одном Postgres контуре.

#### 3. Нужно держать bounded context, а не отдельный зоопарк инфраструктуры

Правильная изоляция здесь — **не отдельная БД**, а:

- отдельный schema namespace;
- отдельные модули кода;
- отдельные сервисы;
- отдельный session state;
- отдельные миграции manager-side блока.

То есть изоляция логическая и доменная, а не искусственно инфраструктурная.

### Что не рекомендовано в V1

Не рекомендовано:

- хранить manager-side thread в analytics tables;
- хранить manager-side thread в Redis;
- хранить manager-side thread только в Telegram;
- выносить manager-side domain в отдельную физическую БД;
- пихать manager-side таблицы прямо в `core.*`, если это не core commercial truth.

### Допустимое исключение в будущем

Отдельная физическая БД может понадобиться позже, если появится:

- real multi-tenant operator SaaS model;
- отдельный сервис manager platform;
- требования по независимому scaling / replication / retention;
- выделенная operational CRM subsystem.

Для V1 это premature complexity.

---

## 15. Что должно получиться в коде после этого документа

После этого документа кодовая реализация должна отражать простую модель:

1. `core.quote_cases` остаётся коммерческим anchor.
2. `manager.*` хранит:
   - ops state,
   - external thread,
   - internal notes,
   - assignment history,
   - routing decisions,
   - presence,
   - delivery attempts.
3. Очереди вычисляются как read models.
4. `urgent`, `escalated`, `unassigned`, `mine` — это не статусы, а derived operational views.
5. Presence влияет на routing, но не переписывает case history.
6. Новое сообщение клиента может reopen'ить `resolved` кейс.
7. `closed` не должен самопроизвольно оживать без explicit reopen rule.

---

## 16. Anti-patterns, которые запрещены этим документом

### 16.1. Запрещено пихать всё в один enum

Нельзя делать поле вида:

```text
status = new | active | urgent | waiting_customer | waiting_manager | escalated | mine | overdue
```

Это не статус.
Это каша.

### 16.2. Запрещено считать queue = status

Очередь — это read model.
У одного и того же кейса одновременно могут быть свойства:

- assigned to me
- urgent
- escalated
- SLA at risk

И это нормально.

### 16.3. Запрещено хранить manager-side truth в Telegram

Telegram — transport/surface.
Не source of truth.

### 16.4. Запрещено делать отдельную физическую БД “потому что tradeflow и так сложный”

Сложность не лечится разрезанием системы по случайным инфраструктурным швам.
Она лечится bounded contexts, schema discipline и нормальной моделью.

### 16.5. Запрещено смешивать waiting-state и presence

`waiting/customer` означает blocker на уровне case.
`manager offline` означает availability на уровне actor.
Это разные сущности.

---

## 17. Decision summary

### Жёсткие решения V1

- роли V1 = только `OWNER` и `MANAGER`
- `quote_case` остаётся anchor
- operational status отдельный от commercial status
- waiting-state отдельный от operational status
- priority и escalation не являются status
- queues являются derived read models
- presence влияет на routing, но не заменяет case state
- manager-side persistence хранится в том же Postgres контуре TradeFlow, но в отдельном manager-side schema namespace
- отдельная физическая БД для ManagerBot в V1 **не нужна и не рекомендована**

---

## 18. Что делать дальше

Следующим документом должен идти:

- `30_managerbot_panels_and_navigation.md`

Но если хочется сначала прибить физику хранения и SQL contracts, допустимо раньше сделать:

- `60_data_model_postgres_managerbot.md`

С инженерной точки зрения оба порядка рабочие.
С практической точки зрения лучше сначала описать panel/navigation contract, чтобы таблицы не начали жить в вакууме.
