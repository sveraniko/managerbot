# 35_manager_reply_flow.md

# ManagerBot Reply Flow V1

**Статус:** canonical interaction and persistence contract for manager/customer reply flows in ManagerBot V1  
**Дата:** 25 March 2026  
**Назначение:** этот документ фиксирует, как в V1 должны работать manager replies, customer inbound messages, internal notes, delivery attempts, compose states и возврат кейса в рабочие очереди.

---

## 1. Зачем нужен этот документ

Архитектура, domain model, statuses/routing и panels/navigation уже зафиксировали:

- ManagerBot = primary workspace для `OWNER` и `MANAGER`;
- V1 якорится на existing `core.quote_cases`;
- manager-side operational truth не должен смешиваться с commercial lifecycle;
- queue/list/detail/navigation уже определены;
- customer-visible thread и internal notes должны храниться отдельно;
- analytics не являются primary chat store.

Этого всё ещё недостаточно, чтобы безопасно реализовать переписку.

Самый опасный слой в ManagerBot не queues и не кнопки.
Самый опасный слой - это **реальная коммуникация с клиентом**.

Если reply flow не прибить заранее, система почти гарантированно скатится в один из трёх видов инженерного стыда:

1. reply "как бы ушёл", но в действительности потерялся;
2. internal note случайно выглядит как customer reply;
3. thread собирается из смеси Telegram-сообщений, analytics событий и случайных revision notes.

Этот документ нужен, чтобы этого не случилось.

Он фиксирует:

- кто владеет reply flow;
- что считается external communication;
- что считается internal communication;
- где и как это хранится;
- как работает compose/confirm/send lifecycle;
- как обрабатывается customer inbound message;
- как обновляются ops state и queues;
- как мы избегаем "phantom sent" и "message lost" сценариев.

Это **не visual design doc** и не чисто SQL-спека.
Это operational contract между Telegram surface, application services, persistence и future AI copilot.

---

## 2. Executive summary

ManagerBot Reply Flow V1 строится на пяти жёстких правилах:

1. **Вся customer-visible переписка хранится в БД.**
2. **Внутренние заметки хранятся отдельно от customer-visible thread.**
3. **Reply никогда не считается sent только потому, что менеджер нажал кнопку.**
4. **Каждая исходящая реплика имеет delivery lifecycle.**
5. **Inbound customer messages должны обновлять и thread, и manager ops state в одном domain flow.**

Базовая формула V1:

```text
Customer inbound message
    -> persist external thread entry
    -> update ops state / waiting / unread signals
    -> enqueue routing decision / analytics

Manager reply draft
    -> persist outgoing external thread entry (pending_delivery)
    -> attempt Telegram delivery
    -> persist delivery attempt/result
    -> update thread delivery status
    -> update ops state / waiting_state
```

В V1:

- **thread truth живёт в БД, не в Telegram history**;
- **delivery truth живёт в БД, не в optimistic UI**;
- **manager compose state живёт в отдельном `ManagerSessionState`**;
- **customer thread относится к manager operational domain и должен быть baseline-required persistence**.

---

## 3. Ответ на главный архитектурный вопрос: baseline или optional layer

Да, ты правильно давишь в эту точку.

Если исходить из вашей собственной продуктовой логики, то **возможность менеджерить клиента по quote/order workflow - это не optional vertical**, а **базовый operational функционал TradeFlow**.

### 3.1. Что из этого следует

Manager-side persistence **не должен жить как optional vertical migration** по модели "добавим потом, если проекту повезёт".

Правильное решение для V1:

- manager-side operational tables должны быть **baseline-required**;
- они должны подниматься **по умолчанию** вместе с системой;
- они должны находиться **в том же PostgreSQL контуре**;
- но быть отделены от commercial truth **не отдельной физической БД**, а отдельным operational schema boundary.

### 3.2. Уточнение к предыдущей рекомендации про schema

После сверки с текущим baseline reset правильнее уточнить рекомендацию так:

- **не отдельная физическая БД**;
- **не новая "левая" подсистема сбоку**;
- **не обязательно отдельный top-level schema `manager`**, если в проекте уже есть `ops` schema;
- для V1 наиболее рационально хранить manager operational persistence в **`ops.*`** как части baseline.

То есть practically:

- `core.*` = commercial/domain truth;
- `ops.*` = manager operational truth;
- `audit.*` = audit trail where needed;
- `read.*` = derived read models / projections when потребуется.

### 3.3. Почему это лучше, чем отдельная физическая БД

Потому что reply flow - это не изолированная мини-CRM.
Он tightly связан с:

- `core.quote_cases`
- `core.quote_revisions`
- `core.orders`
- access checks
- routing
- notifications
- analytics
- AI context

Нам нужны:

- FK/референциальная целостность;
- атомарные транзакции;
- простые joins;
- единые миграции;
- отсутствие distributed consistency circus.

Отдельная БД здесь дала бы не чистоту, а лишнюю боль.
Люди часто называют это "масштабируемой архитектурой", пока не приходится чинить прод.

### 3.4. Базовое решение V1

**Manager reply persistence = baseline-required `ops.*` layer внутри общего TradeFlow Postgres.**

Это и есть нормальный инженерный компромисс:

- не раздуваем `core.*`;
- не плодим cross-DB зависимость;
- не делаем ManagerBot optional-afterthought;
- не ломаем baseline philosophy.

---

## 4. Scope V1

### 4.1. Что входит в reply flow V1

В V1 входят:

- inbound customer text messages по quote case;
- manager text replies клиенту;
- internal notes;
- compose/confirm/send lifecycle;
- thread timeline в case detail;
- delivery attempts и delivery result;
- ops-state updates после inbound/outbound сообщений;
- reopen behavior when customer writes again.

### 4.2. Что не входит в reply flow V1

Чтобы не превратить первую реализацию в болото, в V1 **не входят**:

- произвольные media albums как основной сценарий;
- файловые вложения как обязательная часть every message flow;
- voice reply send из ManagerBot;
- message editing / recall / delete как сложная distributed semantics;
- cross-channel delivery beyond Telegram;
- AI autonomous send;
- universal omnichannel inbox.

### 4.3. Практическое правило V1

**V1 = text-first reply flow.**

Если позже потребуется media/file support, он должен добавляться как controlled extension поверх уже нормального text/delivery/thread lifecycle.

---

## 5. Основные понятия

### 5.1. External thread

`External thread` - это customer-visible история коммуникации по `quote_case`.

В external thread входят:

- customer inbound messages;
- manager outbound replies;
- optional system-visible service entries, если они реально показываются клиенту и влияют на разговор.

В external thread **не входят**:

- internal notes;
- routing decisions;
- assignment events;
- pure analytics events;
- internal SLA markers.

### 5.2. Internal note

`Internal note` - это запись для `OWNER/MANAGER`, которая относится к кейсу, но **никогда не должна попасть клиенту**.

Internal note используется для:

- объяснения, что делать дальше;
- передачи контекста между менеджерами;
- фиксации риска, цены, дедлайна, сомнений;
- owner guidance;
- triage notes.

### 5.3. Compose state

`Compose state` - временное armed-input состояние в `ManagerSessionState`, которое определяет:

- что именно сейчас вводит менеджер;
- для какого `quote_case_id`;
- куда вернуться после submit/cancel;
- нужен ли confirm step;
- какой draft уже собран.

Compose state не является source of truth для thread.
Это только transient UI/input state.

### 5.4. Delivery attempt

`Delivery attempt` - отдельная persistent запись попытки доставить outgoing manager reply клиенту.

Она нужна, чтобы не жить в мире иллюзий, где "мы нажали send, значит всё ушло".

### 5.5. Conversation anchor

В V1:

- `conversation_id` логически совпадает с `quote_case_id`;
- отдельную universal conversation aggregate не вводим.

---

## 6. Persistence ownership

### 6.1. Где хранятся сообщения

В V1 customer-visible thread хранится в operational persistence внутри baseline-required `ops.*`.

Рекомендуемые сущности:

- `ops.quote_case_thread_entries`
- `ops.quote_case_internal_notes`
- `ops.quote_case_delivery_attempts`
- `ops.quote_case_ops_state`
- `ops.quote_case_assignment_events`
- `ops.quote_case_routing_decisions`

### 6.2. Что остаётся в `core.*`

В `core.*` остаются:

- `quote_cases`
- `quote_revisions`
- `orders`
- commercial lifecycle
- business documents
- draft/order/project truth

### 6.3. Что остаётся в analytics

В analytics остаются:

- counters;
- reporting events;
- funnel events;
- audit-like feed where useful.

Но analytics **не владеют reply history**.

### 6.4. Source-of-truth rule

Canonical rule:

> Если на экране case detail показывается реальная переписка клиента и менеджера, она должна читаться из `ops.quote_case_thread_entries`, а не собираться эвристикой из других источников.

---

## 7. External thread entry model

Каждая запись external thread должна минимум содержать:

- `id`
- `quote_case_id`
- `entry_direction` = `inbound` | `outbound`
- `entry_kind` = `message` | `service_visible` | `delivery_notice` (минимум V1 можно ограничить `message`)
- `author_role` = `customer` | `manager` | `owner` | `system`
- `author_actor_id` nullable
- `body_text`
- `body_format` = `plain_text`
- `telegram_chat_id` nullable
- `telegram_message_id` nullable
- `customer_visibility` boolean
- `delivery_status` = `not_applicable` | `pending` | `sent` | `failed`
- `created_at`
- `delivered_at` nullable
- `failed_at` nullable
- `reply_to_entry_id` nullable (optional for V1)
- `meta_json`

### 7.1. Canonical rule for inbound

Customer inbound entry:

- всегда `entry_direction = inbound`
- `author_role = customer`
- `customer_visibility = true`
- `delivery_status = not_applicable`

### 7.2. Canonical rule for outbound

Manager outbound entry:

- `entry_direction = outbound`
- `author_role = manager` or `owner`
- `customer_visibility = true`
- изначально создаётся как `delivery_status = pending`
- после send attempt меняет статус на `sent` или `failed`

### 7.3. Не хранить thread только в Telegram metadata

Нельзя делать архитектуру, где настоящий текст живёт "в отправленном сообщении Telegram", а БД хранит только ссылку.

В БД должен лежать канонический текст.
Telegram metadata - только transport/reference layer.

---

## 8. Internal note model

Каждая internal note должна минимум содержать:

- `id`
- `quote_case_id`
- `author_actor_id`
- `author_role` = `manager` | `owner`
- `body_text`
- `body_format` = `plain_text`
- `visibility_scope` = `internal_only`
- `created_at`
- `meta_json`

Canonical rule:

> Internal note никогда не делит таблицу с customer-visible thread entry, если это создаёт риск случайного outbound delivery.

V1 должен быть тупо безопасным.
Не "гибким".

---

## 9. Compose lifecycle V1

### 9.1. Supported compose modes

V1 поддерживает два основных armed text-input режима:

- `compose:reply`
- `compose:note`

Опционально later:

- `compose:close_reason`
- `compose:reassign_reason`

### 9.2. Compose state payload

`ManagerSessionState.compose` должен минимум хранить:

- `mode`
- `quote_case_id`
- `return_panel_key`
- `draft_text`
- `requires_confirm`
- `started_at`

### 9.3. Arming reply flow

Когда менеджер нажимает `Reply` из `case:detail`:

1. bot сохраняет compose state;
2. bot помечает текущий режим как `compose:reply`;
3. bot показывает явный prompt;
4. panel clearly indicates, что следующий текст уйдёт клиенту после confirm/send.

### 9.4. Arming note flow

Когда менеджер нажимает `Add internal note`:

1. bot сохраняет compose state;
2. bot помечает режим `compose:note`;
3. bot показывает явный prompt;
4. panel clearly indicates, что введённый текст останется internal.

### 9.5. No ambiguous compose mode

Пользователь никогда не должен гадать, вводит ли он сейчас:

- reply клиенту;
- internal note;
- search;
- фильтр.

Если compose armed, это должно быть явно видно в panel text.

---

## 10. Reply submit lifecycle

### 10.1. Canonical flow

`Reply` flow V1:

```text
Manager presses Reply
    -> compose:reply armed
Manager sends text
    -> draft captured
    -> confirm panel shown (or direct send if explicitly allowed by policy)
Manager confirms send
    -> persist outbound thread entry(status=pending)
    -> attempt Telegram delivery
    -> persist delivery attempt
    -> update outbound thread entry(status=sent|failed)
    -> update ops state
    -> render case detail with result notice
```

### 10.2. Confirm step

Рекомендация V1:

- internal note можно сохранять без heavy confirm;
- customer reply лучше делать через explicit confirm step.

Почему:

- цена ошибки выше;
- Telegram бот не даёт undo как мессенджер для человека;
- AI suggestions позже тоже будут вставляться сюда;
- смешение note/reply без confirm - плохая идея.

### 10.3. Persist-before-send rule

Для outbound customer reply canonical правило такое:

> Сначала создаём external thread entry со статусом `pending`, потом пытаемся отправить transport message.

Почему не наоборот:

- нужен auditability;
- нужен deterministic retry path;
- нельзя терять draft при transport failure.

### 10.4. Delivery attempt creation

Каждая send attempt должна создавать запись доставки с минимумом полей:

- `id`
- `thread_entry_id`
- `quote_case_id`
- `target_telegram_chat_id`
- `attempt_number`
- `transport` = `telegram_bot_api`
- `status` = `pending` | `sent` | `failed`
- `error_code` nullable
- `error_message` nullable
- `attempted_at`
- `completed_at` nullable

### 10.5. Delivery result handling

Если Telegram send успешен:

- delivery attempt -> `sent`
- thread entry -> `sent`
- сохраняются `telegram_message_id`, `delivered_at`
- ops state обновляется

Если Telegram send упал:

- delivery attempt -> `failed`
- thread entry -> `failed`
- кейс остаётся в manager-side queue
- в UI показывается recoverable failure notice

### 10.6. No phantom sent

Нельзя в UI писать "Reply sent", пока transport attempt реально не завершился success result.

Допустимо писать:

- `Reply queued for delivery...` пока идёт send;
- `Reply sent.` после success;
- `Reply saved, delivery failed.` после failure.

---

## 11. Internal note submit lifecycle

### 11.1. Canonical flow

```text
Manager presses Internal note
    -> compose:note armed
Manager sends text
    -> persist internal note
    -> optional analytics event
    -> return to case detail
```

### 11.2. No transport layer

Internal note:

- не создаёт outbound transport attempt;
- не пишет в external thread;
- не изменяет customer-visible history;
- не должен маркироваться как reply anywhere in UI.

### 11.3. Note visibility in case detail

В V1 internal notes должны быть видны:

- в case detail как отдельный internal block;
- или в отдельном subpanel `case:notes`.

Но даже если они визуально рядом с thread, разделение должно быть максимально явным.

---

## 12. Customer inbound lifecycle

### 12.1. Канонический принцип

Когда клиент пишет по quote-case, это не просто "новый текст в чат".
Это domain event, который должен изменить case state.

### 12.2. Canonical inbound flow

```text
Customer sends message in customer bot
    -> access / case resolution
    -> persist inbound thread entry
    -> update quote_case_ops_state
    -> mark waiting_state=manager
    -> set/unset operational status as needed
    -> create routing decision if required
    -> emit analytics event
    -> update case detail read model / queues
```

### 12.3. Что именно меняется при inbound customer message

Обычно V1 должен делать следующее:

- append inbound entry to external thread;
- обновить `last_customer_message_at`;
- сбросить resolved/quiet assumptions, если кейс reopened;
- выставить `waiting_state = manager`;
- если кейс был `resolved`, перевести его обратно в `active` или `waiting` по canonical routing rule;
- если кейс был unassigned, routing может вернуть его в `new`/`unassigned` queue;
- если кейс assigned, он должен попасть в `mine`/`waiting_me`.

### 12.4. Reopen rule

Если customer пишет после того, как кейс был `resolved`, canonical правило V1:

- кейс **может быть reopened автоматически**, если коммерческий lifecycle ещё допускает работу;
- `closed` кейсы не должны автоматически восстанавливаться без явного policy rule.

Рекомендуемое V1 поведение:

- `resolved` + inbound customer message -> `active` with `waiting_state=manager`
- `closed` + inbound customer message -> routing flag `needs_owner_review` or explicit reopen policy

---

## 13. Ops-state updates from reply flow

### 13.1. После successful manager reply

Рекомендуемое canonical обновление:

- `last_manager_message_at = now()`
- `waiting_state = customer`
- `status = waiting` если менеджер теперь действительно ждёт клиента
- `status = active` если reply - это только промежуточный шаг и follow-up остаётся за менеджером

### 13.2. После failed manager reply

Рекомендуемое canonical обновление:

- `last_manager_message_at` можно не обновлять как delivered communication timestamp
- кейс остаётся `active`
- `waiting_state` не переключается в `customer`
- выставляется operational signal / flag: `delivery_failed = true`

### 13.3. После internal note

Internal note:

- не должна автоматически менять `waiting_state`;
- может обновить `status`, только если note является частью explicit triage action;
- сама по себе note = context persistence, не delivery action.

---

## 14. Idempotency and duplicate protection

### 14.1. Почему это нужно

Telegram, retries, double taps и нестабильные сети любят создавать дубли. Так уж устроен мир: интерфейс делает вид, что всё просто, а потом оказывается, что у тебя два одинаковых сообщения ушли клиенту.

### 14.2. Canonical idempotency rules

Для outbound reply V1 нужен idempotency guard на уровне application service.

Минимум:

- `compose_submission_token` или `action_token`
- уникальный send attempt key per confirmed draft
- защита от double confirm / repeated callback

### 14.3. Inbound dedup

Для customer inbound transport желательно иметь transport-level dedup по telegram update identity, чтобы один входящий update не создавал два thread entries.

---

## 15. Rendering rules in case detail

### 15.1. Thread section

Case detail должен показывать:

- последние external thread entries;
- delivery status для outbound entries, если он relevant;
- визуальное различие inbound/outbound.

### 15.2. Internal notes section

Internal notes:

- не должны смешиваться с external thread так, будто это одна и та же переписка;
- могут показываться отдельным блоком ниже или отдельным subpanel;
- должны быть clearly marked as internal.

### 15.3. Compose warning

Если armed compose mode активен, panel должна явно показывать:

- `Reply armed` или `Internal note armed`;
- что именно произойдёт с следующим текстом;
- как отменить режим.

---

## 16. Error handling and recovery

### 16.1. Delivery failure

Если outbound send не удался:

- текст не теряется;
- thread entry уже существует;
- entry помечается `failed`;
- менеджер видит recoverable action: `Retry delivery` или `Open failed draft`.

### 16.2. Invalid case / lost access

Если во время compose flow кейс стал недоступен:

- send запрещается;
- compose state очищается или переводится в safe failure;
- пользователю показывается честное сообщение, что кейс changed/unavailable.

### 16.3. Missing customer chat binding

Если для кейса нет valid Telegram target:

- reply можно сохранить как outbound pending/failed draft entry;
- transport attempt завершается failed с понятной причиной;
- кейс помечается на manual attention.

---

## 17. Analytics and audit side effects

Reply flow может и должен эмитить analytics/audit события, но это всегда **побочный продукт**, а не источник истины.

Типовые события V1:

- `manager.reply_composed`
- `manager.reply_sent`
- `manager.reply_delivery_failed`
- `manager.internal_note_added`
- `customer.message_received`
- `quote_case.reopened_by_customer_message`

Но UI и domain reads не должны зависеть от того, дошло ли событие в analytics pipeline.

---

## 18. AI seam implications

Reply flow V1 должен быть совместим с future AI copilot.

Это означает:

- AI может предлагать draft reply;
- AI может summarise thread;
- AI может highlight missing context;
- AI не должен владеть transport send.

Canonical rule:

> Любой AI-generated reply draft до отправки становится обычным manager draft и проходит тот же confirm/send/delivery lifecycle.

---

## 19. Implementation guidance

### 19.1. Что нужно поменять в текущем customer quote path

Сейчас customer quote thread местами читается из analytics events.
Для ManagerBot V1 это нужно перевести на новый persistence path.

Практически это означает:

- customer-side `submit_quote_message(...)` должен писать в `ops.quote_case_thread_entries`;
- analytics event может эмититься параллельно;
- quote detail в customer shell и manager case detail должны читать один и тот же canonical external thread store.

### 19.2. Что должно появиться в application layer

Нужны отдельные сервисы/handlers уровня application/domain:

- `QuoteCaseThreadService`
- `QuoteCaseReplyService`
- `QuoteCaseInternalNoteService`
- `QuoteCaseDeliveryService`
- `QuoteCaseInboundMessageService`

### 19.3. Что должно появиться в bot layer

В bot layer понадобятся:

- manager compose arming handler;
- manager compose submit handler;
- confirm send handler;
- retry delivery handler;
- cancel compose handler;
- case detail renderer, умеющий показывать delivery state.

---

## 20. Canonical V1 decisions

Для V1 фиксируются следующие решения:

1. `Reply flow` поддерживает **text-first communication**.
2. Все customer-visible messages хранятся в baseline-required `ops.*` persistence.
3. `Internal notes` хранятся отдельно от external thread.
4. `Outbound reply` сначала сохраняется, потом отправляется.
5. Каждая outbound attempt имеет отдельный delivery record.
6. `Analytics` не являются thread store.
7. `ManagerSessionState` хранит только transient compose state, не сам truth.
8. Customer inbound messages обновляют и thread, и ops state.
9. `Resolved` кейс может reopen-нуться customer inbound сообщением по policy V1.
10. AI suggestions проходят тот же confirm/send flow, что и human drafts.

---

## 21. Out of scope until later PRs

Вне V1 остаются:

- advanced attachment lifecycle;
- omnichannel adapters;
- message edit/recall synchronization;
- quoted replies with full threading trees;
- group-topic mirrored discussion as primary note space;
- autonomous AI messaging.

---

## 22. Итог

ManagerBot V1 не должен делать вид, что Telegram history и есть CRM.

Правильная модель такая:

- `core.quote_cases` остаётся коммерческим якорем;
- `ops.*` хранит manager-side operational truth;
- customer-visible thread живёт как нормальный persistent store;
- internal notes отделены;
- delivery attempts фиксируются явно;
- UI показывает честный state;
- AI подключается только как помощник.

Если это сделать так, reply flow станет опорой для бизнеса.
Если начать экономить на этом слое, потом система будет "вроде работать", пока не случится первый важный клиентский диалог и не выяснится, что половина истины жила в Telegram, четверть в аналитике, а остальное в воображении разработчика.
