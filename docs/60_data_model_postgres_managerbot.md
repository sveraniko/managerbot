# 60_data_model_postgres_managerbot.md

# ManagerBot PostgreSQL Data Model V1

**Статус:** canonical PostgreSQL persistence contract for ManagerBot V1  
**Дата:** 25 March 2026  
**Назначение:** этот документ фиксирует конкретную Postgres-модель для manager-side слоя TradeFlow V1: schema boundaries, таблицы, поля, FK, индексы, enum naming, baseline migration order и жёсткие ограничения, которые нельзя размывать в реализации.

---

## 1. Зачем нужен этот документ

Предыдущие документы уже зафиксировали:

- `quote_case` является V1 anchor;
- manager-side operational state не смешивается с commercial lifecycle;
- customer-visible thread и internal notes хранятся отдельно;
- ManagerBot является baseline-required operational contour;
- V1 использует только роли `OWNER` и `MANAGER`;
- V1 assumes single operator org per deployment;
- reply flow и queues опираются на DB truth, а не на Telegram history и не на analytics.

Этого достаточно для архитектуры и домена.
Для кода этого недостаточно.

Нужен документ, который отвечает на скучный, но решающий вопрос:

**какие именно таблицы, колонки, FK, индексы и enum types должны появиться в Postgres, чтобы ManagerBot можно было реализовать без домыслов и без последующего распила продовой схемы.**

Это не ORM implementation file и не Alembic migration.
Это canonical storage contract.

Если потом кто-то решит:

- хранить thread в `audit.analytics_events`;
- держать assignment только в Redis state;
- класть internal notes в тот же поток, что и customer replies;
- унести manager-side persistence в отдельную физическую БД;
- воткнуть `waiting_customer` прямо в `core.quote_cases.status`;

значит он спорит не с "мнением", а с зафиксированным persistence contract.

---

## 2. Executive summary

ManagerBot V1 хранится в **том же Postgres контуре TradeFlow**, но разделяется по schema responsibility.

Базовая модель V1:

- `core.*` = commercial/domain truth
- `ops.*` = manager operational truth
- `audit.*` = audit / analytics / action trail
- `read.*` = optional projections / read models

В V1 обязательно делаются:

1. **добавления в `core`**
   - persistent `display_number` для `core.quote_cases`
   - persistent `display_number` для `core.orders`
2. **baseline-required `ops` tables**
   - `ops.quote_case_ops_states`
   - `ops.quote_case_thread_entries`
   - `ops.quote_case_internal_notes`
   - `ops.quote_case_assignment_events`
   - `ops.manager_presence_states`
   - `ops.quote_case_routing_decisions`
   - `ops.reply_delivery_attempts`
3. **optional-later `read` projections**
   - не обязательны для первого запуска миграций
   - могут добавляться после стабилизации write model

Ключевой принцип:

> `core.quote_cases` остаётся коммерческим якорем, а `ops.*` добавляет поверх него operational handling.

Именно так мы избегаем двух архитектурных глупостей:

- не раздуваем `core` операционным шумом;
- не устраиваем отдельный database island для manager-side.

---

## 3. Schema boundaries

### 3.1. `core.*`

`core.*` остаётся доменным слоем коммерческой системы.

Сюда относятся:

- actors / bindings / roles
- company accounts / memberships
- catalog
- drafts
- quote cases / quote revisions
- orders
- projects / objects
- documents

Для ManagerBot V1 в `core` допускаются только **минимально необходимые дополнения**, которые являются частью коммерческой truth, а не operational chatter.

Разрешённые core additions V1:

- `core.quote_cases.display_number`
- `core.orders.display_number`
- supporting sequences / indexes / backfill logic

Запрещено тащить в `core`:

- waiting states
- queue flags
- manager presence
- internal notes
- delivery attempts
- routing decisions
- compose drafts

### 3.2. `ops.*`

`ops.*` - baseline-required operational persistence.

Это не optional vertical.
Это часть минимально пригодного к эксплуатации TradeFlow.

Сюда относятся:

- assignment
- queue state
- waiting state
- priority
- escalation
- customer-visible thread persistence
- internal notes
- reply delivery lifecycle
- manager presence
- routing decisions

Это слой, где живёт operational truth для ManagerBot.

### 3.3. `audit.*`

`audit.*` продолжает хранить:

- analytics events
- action events
- rollups
- audit trail

Важно:

- `audit.*` **не является source of truth** для thread;
- события могут дублировать факт reply/inbound/routing для аналитики и аудита;
- но восстановление thread и case state из audit event feed не допускается как primary operational path.

### 3.4. `read.*`

`read.*` используется только для projections/read models.

В V1 можно обойтись без отдельных read tables и строить queue read path через SQL queries over `core + ops`.

Если после запуска потребуется ускорение, в `read.*` можно добавить:

- materialized projections
- denormalized queue rows
- unread counters
- SLA buckets

Но это **не baseline prerequisite**.

---

## 4. Baseline-required persistence scope

### 4.1. Обязательно в baseline

В baseline должны подниматься:

- schema `ops`
- manager enums
- все V1 write-model tables из `ops.*`
- `display_number` support в `core.quote_cases` и `core.orders`

Причина простая:

без этого TradeFlow не умеет жить как реальный B2B workflow, где после поиска и quote должен существовать нормальный внутренний operational contour.

### 4.2. Не требуется в baseline first migration

Необязательны в первом проходе:

- `read.*` projections
- topic bridge persistence
- AI summary cache tables
- attachment-heavy message tables
- omnichannel delivery tables beyond Telegram

---

## 5. Global persistence principles

### 5.1. UUID primary keys

Все новые write-model таблицы используют тот же подход, что и existing codebase:

- UUID primary key
- uuid7/ordered-UUID generation через общий mixin

Это сохраняет согласованность с current `Base` и existing models.

### 5.2. Timestamps

Все write-model сущности должны иметь:

- `created_at timestamptz not null`
- `updated_at timestamptz not null`

Если запись immutable по смыслу, `updated_at` всё равно остаётся допустимой через общий mixin, чтобы не плодить частные паттерны.

### 5.3. Soft archive

По умолчанию новые `ops.*` записи **не обязаны** использовать `SoftArchiveMixin`, если сущность естественно immutable или живёт как active state row.

Рекомендуемая логика:

- state tables: без soft archive
- append-only event/note/thread tables: без soft archive, если для V1 нет business requirement скрывать историю
- если позже потребуется conceal/archive, это отдельное решение V2

### 5.4. Enum style

Следуем существующему стилю ORM:

- PostgreSQL enums через SQLAlchemy `Enum(..., native_enum=False)` на уровне ORM
- в документе фиксируем logical enum names
- enum names префиксуются `manager_...`, чтобы не коллидировать с общими enum names

### 5.5. Foreign key philosophy

Общее правило:

- всё, что logically принадлежит `quote_case`, FK к `core.quote_cases.id`
- всё, что относится к внутреннему пользователю, FK к `core.actors.id`
- не плодить weak references строками, если есть нормальный FK

### 5.6. Text fields

Для message bodies и notes использовать `Text`, а не `String(500)`.

Потому что:

- reply может быть длиннее 500 символов;
- менеджер не должен внезапно упираться в искусственный лимит, придуманный из скуки;
- обрезка reply на storage layer создаёт грязные баги.

Короткие reason/code поля остаются `String(64/128/255)`.

### 5.7. JSONB only where justified

`JSONB` разрешён только там, где payload действительно semi-structured:

- routing inputs snapshot
- provider response payload (optional)
- metadata / extra context

Запрещено использовать `JSONB` как замену нормальным колонкам для:

- status
n- assignee
- waiting state
- delivery status
- timestamps

---

## 6. Core additions required for ManagerBot V1

## 6.1. `core.quote_cases.display_number`

### Назначение

Persistent human-facing номер quote-case.

Он нужен, потому что runtime-computed "Quote #5 в списке пользователя" не годится для:

- manager queues
- стабильных ссылок в интерфейсе
- customer/manager communication
- search by public number
- owner oversight

### Contract

Добавить в `core.quote_cases`:

- `display_number BIGINT NOT NULL`

### Constraints

- `UNIQUE (display_number)`
- immutable after insert
- generated exactly once at quote-case creation

### Sequence

Рекомендуемая sequence:

- `core.quote_case_display_number_seq`

### Semantics

- global monotonic number per deployment
- не зависит от customer company
- не переиспользуется
- не меняется при archive / reopen / revision

### Why global and not per-company

Для V1 single-operator deployment глобальная последовательность проще и надёжнее:

- меньше логики
- меньше race conditions
- проще support/search/debug
- лучше для manager queues

---

## 6.2. `core.orders.display_number`

### Назначение

Persistent human-facing номер заказа.

### Contract

Добавить в `core.orders`:

- `display_number BIGINT NOT NULL`

### Constraints

- `UNIQUE (display_number)`
- immutable after insert

### Sequence

Рекомендуемая sequence:

- `core.order_display_number_seq`

---

## 6.3. Upgrade path

Если миграция накатывается на уже существующую БД, нужен deterministic backfill:

- создать sequence
- заполнить `display_number` в порядке `created_at, id`
- затем повесить `NOT NULL` и unique index

Если deployment чистый и baseline разворачивается с нуля, backfill не нужен.

---

## 7. New `ops.*` tables

Ниже фиксируется canonical V1 write model.

---

## 7.1. `ops.quote_case_ops_states`

### Назначение

Одна active operational state row на один `quote_case`.

Это главный manager-side state aggregate для queues и case handling.

### Ownership

- `core.quote_cases` отвечает на вопрос: что это за коммерческий кейс
- `ops.quote_case_ops_states` отвечает на вопрос: что сейчас с ним происходит операционно

### Cardinality

- one-to-one with `core.quote_cases`

### Columns

- `id UUID PK`
- `quote_case_id UUID NOT NULL`
- `status manager_case_ops_status NOT NULL`
- `waiting_state manager_case_waiting_state NOT NULL`
- `priority manager_case_priority NOT NULL`
- `assigned_manager_actor_id UUID NULL`
- `assigned_by_actor_id UUID NULL`
- `assigned_at TIMESTAMPTZ NULL`
- `human_requested BOOLEAN NOT NULL DEFAULT false`
- `escalation_level INTEGER NOT NULL DEFAULT 0`
- `sla_due_at TIMESTAMPTZ NULL`
- `next_followup_at TIMESTAMPTZ NULL`
- `last_customer_message_at TIMESTAMPTZ NULL`
- `last_manager_message_at TIMESTAMPTZ NULL`
- `last_internal_note_at TIMESTAMPTZ NULL`
- `last_inbound_entry_id UUID NULL`
- `last_outbound_entry_id UUID NULL`
- `reopen_count INTEGER NOT NULL DEFAULT 0`
- `resolution_code VARCHAR(64) NULL`
- `resolution_note VARCHAR(500) NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

### FKs

- `quote_case_id -> core.quote_cases.id ON DELETE CASCADE`
- `assigned_manager_actor_id -> core.actors.id ON DELETE SET NULL`
- `assigned_by_actor_id -> core.actors.id ON DELETE SET NULL`
- `last_inbound_entry_id -> ops.quote_case_thread_entries.id ON DELETE SET NULL`
- `last_outbound_entry_id -> ops.quote_case_thread_entries.id ON DELETE SET NULL`

### Constraints

- `UNIQUE (quote_case_id)`
- `CHECK (escalation_level >= 0)`
- `CHECK (reopen_count >= 0)`

### Notes

`status` и `waiting_state` не дублируют commercial lifecycle.
Они существуют исключительно для manager routing/handling.

### Suggested indexes

- index on `(status, waiting_state)`
- index on `(assigned_manager_actor_id, status)`
- index on `(priority, sla_due_at)`
- index on `(human_requested)`
- index on `(next_followup_at)`
- index on `(last_customer_message_at)`

### Why one-row state instead of append-only only

Потому что queues и case detail должны открываться быстро и deterministically.
Append-only events остаются, но active state хранится отдельно.

---

## 7.2. `ops.quote_case_thread_entries`

### Назначение

Persistent customer-visible thread по `quote_case`.

Это **не Telegram history mirror**, а operational source of truth для external communication.

### Cardinality

- one-to-many from `core.quote_cases`

### Columns

- `id UUID PK`
- `quote_case_id UUID NOT NULL`
- `entry_seq BIGINT NOT NULL`
- `direction manager_thread_direction NOT NULL`
- `author_side manager_thread_author_side NOT NULL`
- `entry_kind manager_thread_entry_kind NOT NULL`
- `author_actor_id UUID NULL`
- `body_text TEXT NOT NULL`
- `body_plain TEXT NULL`
- `customer_visible BOOLEAN NOT NULL DEFAULT true`
- `delivery_status manager_delivery_status NULL`
- `delivery_channel VARCHAR(32) NULL`
- `provider_message_ref VARCHAR(255) NULL`
- `provider_chat_ref VARCHAR(255) NULL`
- `sent_at TIMESTAMPTZ NULL`
- `delivered_at TIMESTAMPTZ NULL`
- `failed_at TIMESTAMPTZ NULL`
- `in_reply_to_entry_id UUID NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

### FKs

- `quote_case_id -> core.quote_cases.id ON DELETE CASCADE`
- `author_actor_id -> core.actors.id ON DELETE SET NULL`
- `in_reply_to_entry_id -> ops.quote_case_thread_entries.id ON DELETE SET NULL`

### Constraints

- `UNIQUE (quote_case_id, entry_seq)`
- `CHECK (entry_seq >= 1)`
- `CHECK (customer_visible = true)` for V1 can be omitted because table itself is external-thread only; the column remains for future controlled service entries

### Semantics

`direction`:

- `inbound`
- `outbound`

`author_side`:

- `customer`
- `manager`
- `system`

`entry_kind`:

- `message`
- `service`

### Delivery field rules

- inbound rows normally have `delivery_status = NULL`
- outbound rows must carry delivery lifecycle
- a row is **not** considered sent merely because it exists
- final state is determined by delivery attempts and the final update of this row

### `entry_seq`

`entry_seq` - monotonically increasing per `quote_case`, generated on insert.

Он нужен, потому что:

- UUID не даёт человекочитаемый order внутри кейса;
- `created_at` может совпасть в плотных транзакциях;
- timeline должен быть deterministic.

### Suggested indexes

- index on `(quote_case_id, entry_seq)` unique already covers main read path
- index on `(quote_case_id, created_at)`
- index on `(delivery_status)` partial for outbound rows if needed
- index on `(author_side, created_at)` optional for analytics-like reads

### Why `body_text` and `body_plain`

V1 text-first flow может обходиться только `body_text`.

`body_plain` оставлен как optional field на случай, если позже появится:

- rich formatting normalization
- sanitized plain text index
- provider/transport normalization

Если на старте не нужен, можно оставить nullable и не использовать.

---

## 7.3. `ops.quote_case_internal_notes`

### Назначение

Внутренние заметки, никогда не видимые клиенту.

### Columns

- `id UUID PK`
- `quote_case_id UUID NOT NULL`
- `note_seq BIGINT NOT NULL`
- `author_actor_id UUID NOT NULL`
- `note_kind manager_note_kind NOT NULL`
- `body_text TEXT NOT NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

### FKs

- `quote_case_id -> core.quote_cases.id ON DELETE CASCADE`
- `author_actor_id -> core.actors.id ON DELETE RESTRICT`

### Constraints

- `UNIQUE (quote_case_id, note_seq)`
- `CHECK (note_seq >= 1)`

### `note_kind`

Recommended V1 values:

- `general`
- `handoff`
- `risk`
- `resolution`
- `system`

### Suggested indexes

- index on `(quote_case_id, note_seq)` unique already covers main path
- index on `(author_actor_id, created_at)`
- index on `(note_kind)` optional

### Why separate table and not `is_internal` flag on thread

Потому что смешивать internal и external communication в одной таблице - плохая идея даже когда кажется удобно.

Разные правила:

- разные права доступа
- разные UX flows
- разный риск утечки
- разная аналитика

V1 не должен строиться на флажке "ой, главное не забыть поставить internal=true".

---

## 7.4. `ops.quote_case_assignment_events`

### Назначение

Append-only история назначений и ownership changes.

### Columns

- `id UUID PK`
- `quote_case_id UUID NOT NULL`
- `event_seq BIGINT NOT NULL`
- `event_kind manager_assignment_event_kind NOT NULL`
- `from_manager_actor_id UUID NULL`
- `to_manager_actor_id UUID NULL`
- `triggered_by_actor_id UUID NULL`
- `reason_code VARCHAR(64) NULL`
- `reason_text VARCHAR(500) NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

### FKs

- `quote_case_id -> core.quote_cases.id ON DELETE CASCADE`
- `from_manager_actor_id -> core.actors.id ON DELETE SET NULL`
- `to_manager_actor_id -> core.actors.id ON DELETE SET NULL`
- `triggered_by_actor_id -> core.actors.id ON DELETE SET NULL`

### Constraints

- `UNIQUE (quote_case_id, event_seq)`
- `CHECK (event_seq >= 1)`

### Recommended `event_kind`

- `assigned`
- `unassigned`
- `reassigned`
- `claimed`
- `released`
- `owner_override`
- `auto_routed`
- `escalated`

### Suggested indexes

- index on `(quote_case_id, event_seq)`
- index on `(to_manager_actor_id, created_at)`
- index on `(event_kind, created_at)`

### Why separate event table if active assignee exists in ops state

Потому что active row отвечает на вопрос "кто владеет сейчас", а event table отвечает на вопрос "как мы сюда пришли".

Нужны оба слоя.

---

## 7.5. `ops.manager_presence_states`

### Назначение

Текущее presence/capacity состояние внутреннего менеджера.

### Cardinality

- one active row per internal actor participating in ManagerBot

### Columns

- `id UUID PK`
- `actor_id UUID NOT NULL`
- `presence_status manager_presence_status NOT NULL`
- `capacity_slots INTEGER NULL`
- `active_case_limit INTEGER NULL`
- `self_note VARCHAR(255) NULL`
- `last_seen_at TIMESTAMPTZ NULL`
- `last_heartbeat_at TIMESTAMPTZ NULL`
- `set_by_actor_id UUID NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

### FKs

- `actor_id -> core.actors.id ON DELETE CASCADE`
- `set_by_actor_id -> core.actors.id ON DELETE SET NULL`

### Constraints

- `UNIQUE (actor_id)`
- `CHECK (capacity_slots IS NULL OR capacity_slots >= 0)`
- `CHECK (active_case_limit IS NULL OR active_case_limit >= 0)`

### `presence_status`

Recommended V1 values:

- `online`
- `busy`
- `offline`

### Suggested indexes

- unique index on `(actor_id)`
- index on `(presence_status)`
- index on `(last_seen_at)` optional

### Scope note

Это table текущего состояния, не audit history.
Если позже понадобится полноценная история изменений presence, она добавляется отдельно как append-only audit/event table.

---

## 7.6. `ops.quote_case_routing_decisions`

### Назначение

Append-only запись значимых routing/evaluation решений по кейсу.

Это не замена `ops_state`, а след логики маршрутизации.

### Columns

- `id UUID PK`
- `quote_case_id UUID NOT NULL`
- `decision_seq BIGINT NOT NULL`
- `decision_kind manager_routing_decision_kind NOT NULL`
- `decided_assignee_actor_id UUID NULL`
- `decided_by_actor_id UUID NULL`
- `reason_code VARCHAR(64) NULL`
- `reason_text VARCHAR(500) NULL`
- `inputs_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `applied BOOLEAN NOT NULL DEFAULT true`
- `applied_at TIMESTAMPTZ NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

### FKs

- `quote_case_id -> core.quote_cases.id ON DELETE CASCADE`
- `decided_assignee_actor_id -> core.actors.id ON DELETE SET NULL`
- `decided_by_actor_id -> core.actors.id ON DELETE SET NULL`

### Constraints

- `UNIQUE (quote_case_id, decision_seq)`
- `CHECK (decision_seq >= 1)`

### Recommended `decision_kind`

- `initial_queue`
- `claim`
- `manual_assign`
- `manual_reassign`
- `customer_reopen`
- `sla_escalation`
- `owner_override`
- `presence_overflow`
- `resolution_reopen`

### Suggested indexes

- index on `(quote_case_id, decision_seq)`
- index on `(decision_kind, created_at)`
- index on `(decided_assignee_actor_id, created_at)`

### Why this table exists

Потому что в реальном проде потом всегда появляется вопрос:

- почему кейс ушёл именно этому менеджеру?
- почему он снова всплыл в urgent?
- почему owner увидел escalation?

Ответ "ну так получилось в коде" не считается системой.

---

## 7.7. `ops.reply_delivery_attempts`

### Назначение

История попыток доставить outgoing thread entry клиенту.

### Columns

- `id UUID PK`
- `thread_entry_id UUID NOT NULL`
- `quote_case_id UUID NOT NULL`
- `attempt_no INTEGER NOT NULL`
- `channel_code VARCHAR(32) NOT NULL`
- `attempt_status manager_delivery_attempt_status NOT NULL`
- `started_at TIMESTAMPTZ NOT NULL`
- `finished_at TIMESTAMPTZ NULL`
- `provider_message_ref VARCHAR(255) NULL`
- `provider_chat_ref VARCHAR(255) NULL`
- `error_code VARCHAR(128) NULL`
- `error_summary TEXT NULL`
- `provider_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `correlation_id VARCHAR(128) NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

### FKs

- `thread_entry_id -> ops.quote_case_thread_entries.id ON DELETE CASCADE`
- `quote_case_id -> core.quote_cases.id ON DELETE CASCADE`

### Constraints

- `UNIQUE (thread_entry_id, attempt_no)`
- `CHECK (attempt_no >= 1)`

### `attempt_status`

Recommended V1 values:

- `started`
- `succeeded`
- `failed_retryable`
- `failed_terminal`

### Suggested indexes

- index on `(thread_entry_id, attempt_no)` unique already covers main path
- index on `(quote_case_id, created_at)`
- index on `(attempt_status, created_at)`
- index on `(correlation_id)` optional

### Why this is separate from thread entry

Потому что thread entry - это logical message record.
Delivery attempts - transport lifecycle.

Одна outgoing message может иметь:

- несколько попыток;
- разные provider responses;
- retryable failure before success;
- terminal failure.

Не надо сжимать это в одну колонку "sent_ok = true/false" как будто мир так прост.

---

## 8. Enum contracts

Ниже фиксируются logical enums. Конкретные Python Enum classes создаются в manager module и мапятся в ORM в стиле существующего проекта.

---

## 8.1. `manager_case_ops_status`

Recommended values:

- `new`
- `active`
- `resolved`
- `closed`

Смысл:

- `new` = кейс появился в operational contour, ещё не взят/не обработан по существу
- `active` = ведётся работа
- `resolved` = operationally resolved, но ещё может требовать финального закрытия/наблюдения
- `closed` = operationally finished and not expected in normal active queues

---

## 8.2. `manager_case_waiting_state`

Recommended values:

- `none`
- `waiting_manager`
- `waiting_customer`
- `waiting_owner`
- `waiting_delivery`

---

## 8.3. `manager_case_priority`

Recommended values:

- `normal`
- `high`
- `urgent`

V1 deliberately keeps this small.
Не надо устраивать NASA-grade priority matrix в первом релизе.

---

## 8.4. `manager_thread_direction`

Values:

- `inbound`
- `outbound`

---

## 8.5. `manager_thread_author_side`

Values:

- `customer`
- `manager`
- `system`

---

## 8.6. `manager_thread_entry_kind`

Values:

- `message`
- `service`

В V1 почти все записи будут `message`.
`service` оставляется для controlled future use.

---

## 8.7. `manager_delivery_status`

Recommended values:

- `pending`
- `sent`
- `failed`

Это final/current status outgoing entry на уровне thread row.
Детали попыток живут в `ops.reply_delivery_attempts`.

---

## 8.8. `manager_note_kind`

Values:

- `general`
- `handoff`
- `risk`
- `resolution`
- `system`

---

## 8.9. `manager_assignment_event_kind`

Values:

- `assigned`
- `unassigned`
- `reassigned`
- `claimed`
- `released`
- `owner_override`
- `auto_routed`
- `escalated`

---

## 8.10. `manager_presence_status`

Values:

- `online`
- `busy`
- `offline`

---

## 8.11. `manager_routing_decision_kind`

Values:

- `initial_queue`
- `claim`
- `manual_assign`
- `manual_reassign`
- `customer_reopen`
- `sla_escalation`
- `owner_override`
- `presence_overflow`
- `resolution_reopen`

---

## 8.12. `manager_delivery_attempt_status`

Values:

- `started`
- `succeeded`
- `failed_retryable`
- `failed_terminal`

---

## 9. Read-model guidance for V1

### 9.1. No mandatory `read.*` tables in first implementation

Первый проход можно реализовать без отдельных `read` tables.

Queue queries могут строиться как joins over:

- `core.quote_cases`
- `ops.quote_case_ops_states`
- optionally latest thread timestamps / order info

### 9.2. If projections become necessary later

Potential later read models:

- `read.manager_case_queue_rows`
- `read.manager_case_unread_counters`
- `read.manager_case_sla_buckets`

Но сначала надо стабилизировать write model.
Люди любят строить projections до того, как поняли, что именно проецируют. Это редко кончается хорошо.

---

## 10. Referential integrity and delete behavior

### 10.1. `quote_case` as parent

Почти всё в `ops.*` принадлежит `quote_case`.

Если quote_case hard-deleted на уровне БД, manager-side operational rows могут удаляться cascade.

Это согласуется с тем, что:

- thread
- notes
- state
- assignments
- routing
- delivery attempts

не имеют смысла без родительского кейса.

### 10.2. Actors should usually be `SET NULL` for history rows

Для historical/event/thread сущностей, где actor может исчезнуть/быть archived, обычно лучше `ON DELETE SET NULL`, чтобы не разрушать историю.

Исключение:

- `internal_notes.author_actor_id` разумно держать `RESTRICT`, если бизнес хочет сохранять автора как обязательную часть внутренней записи
- но если policy допускает удаление actor records, можно пересмотреть

Для V1 я рекомендую:

- historical thread/assignment/routing rows -> `SET NULL`
- author of internal note -> `RESTRICT`

---

## 11. Suggested migration order

### 11.1. Migration A: schema + enums + core additions

Содержимое:

- create schema `ops`
- create required enums
- create `core.quote_case_display_number_seq`
- create `core.order_display_number_seq`
- add `display_number` columns to `core.quote_cases` and `core.orders`
- backfill if needed
- add unique indexes and not-null constraints

### 11.2. Migration B: core `ops` write-model tables

Содержимое:

- create `ops.quote_case_ops_states`
- create `ops.quote_case_thread_entries`
- create `ops.quote_case_internal_notes`
- create `ops.quote_case_assignment_events`
- create `ops.manager_presence_states`
- create `ops.quote_case_routing_decisions`
- create `ops.reply_delivery_attempts`

### 11.3. Migration C: secondary indexes / tuning

Содержимое:

- non-unique indexes for queues / SLA / assignment / timelines
- optional partial indexes after smoke profiling

### 11.4. Migration D: read projections if actually needed

Только после первых real flows and profiling.

---

## 12. Query patterns the schema must support

### 12.1. Queue list queries

Нужно быстро уметь отвечать на:

- new cases
- mine
- unassigned
- waiting_customer
- waiting_me
- urgent
- escalated

Основной источник:

- `ops.quote_case_ops_states`
- join `core.quote_cases`
- optional join to `core.orders`

### 12.2. Case detail timeline

Нужно быстро читать:

- external thread ordered by `entry_seq`
- internal notes ordered by `note_seq`
- assignment history ordered by `event_seq`

### 12.3. Delivery inspection

Нужно быстро открыть:

- outgoing thread row
- all delivery attempts by `attempt_no`

### 12.4. Search by public number

Нужно быстро искать:

- quote by `display_number`
- order by `display_number`

Это ещё одна причина, почему persistent display numbers нужны в `core`, а не в каком-нибудь UI helper service.

---

## 13. What must not be done

### 13.1. Не хранить manager thread в `audit.analytics_events`

Analytics могут отражать событие, но не должны быть operational source of truth.

### 13.2. Не хранить active ops state только как derived state из событий

Чистый event-sourcing здесь не нужен.
В V1 нужен явный active state row.

### 13.3. Не смешивать external thread и internal notes в одной таблице

Даже если очень хочется "сэкономить" одну migration.

### 13.4. Не делать отдельную физическую БД для manager-side

Один Postgres contour, разные schema boundaries.

### 13.5. Не пихать operational enums в `core.quote_cases.status`

`waiting_customer` и `urgent` не являются quote commercial statuses.

### 13.6. Не держать display numbers как вычисляемое UI-представление

Они должны быть persistent and immutable.

---

## 14. Minimal ORM module layout guidance

Этот документ не диктует exact file names, но рекомендуемая раскладка выглядит так:

- `app/db/models/ops/__init__.py`
- `app/db/models/ops/managerbot.py`
- `app/modules/managerbot/enums.py`
- `app/modules/managerbot/types.py` (optional)

Новые ORM модели не должны размазываться по customer modules.

---

## 15. Final contract summary

ManagerBot V1 storage contract фиксируется так:

1. **Один Postgres contour.**
2. **`core.*` остаётся commercial truth.**
3. **`ops.*` вводится как baseline-required manager operational persistence.**
4. **`core.quote_cases` и `core.orders` получают immutable `display_number`.**
5. **External thread хранится в `ops.quote_case_thread_entries`.**
6. **Internal notes хранятся отдельно в `ops.quote_case_internal_notes`.**
7. **Active queue state хранится в `ops.quote_case_ops_states`.**
8. **Assignment, routing и delivery attempts живут в отдельных append-only tables.**
9. **`audit.*` не является source of truth для manager communication.**
10. **`read.*` может появиться позже, но не обязателен для V1.**

Именно этот набор даёт нормальную стартовую модель:

- не слишком тяжёлую;
- не хрупкую;
- совместимую с текущим baseline philosophy;
- и не превращающую manager-side в опциональный довесок.

Следующий естественный шаг после этого документа - писать PR plan и migration-first implementation notes, потому что теперь уже зафиксировано, **что именно надо создавать**, а не только "куда хотелось бы прийти".
