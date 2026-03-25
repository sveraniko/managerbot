# 30_managerbot_panels_and_navigation.md

# ManagerBot Panels and Navigation V1

**Статус:** canonical Telegram UI/navigation contract for ManagerBot V1  
**Дата:** 25 March 2026  
**Назначение:** этот документ фиксирует panel model, screen families, navigation rules, state ownership и clean-chat discipline для ManagerBot V1.

---

## 1. Зачем нужен этот документ

Архитектура, доменная модель и routing уже зафиксировали:

- ManagerBot = primary workspace для внутренних операторов;
- V1 опирается на existing `core.quote_cases`;
- роли V1 = только `OWNER` и `MANAGER`;
- V1 assumes single operator org per deployment;
- manager operational state хранится в БД;
- thread / notes / routing не являются Telegram-only сущностями;
- manager session state должен быть отдельным.

Этого всё ещё недостаточно, чтобы кодить Telegram surface.

Почти все manager-side боты ломаются одинаково:

- экранов становится слишком много;
- back navigation начинает зависеть от случайной истории кликов;
- reply / note / assignment flows конфликтуют друг с другом;
- фильтры и queue context теряются;
- каждый handler рисует интерфейс по-своему;
- бот загаживает чат десятками сообщений;
- "быстрый фикс" превращает UI в археологический слой человеческих ошибок.

Этот документ нужен, чтобы этого не произошло.

Он отвечает на вопросы:

- какие panel families существуют в V1;
- какие экраны считаются canonical;
- как работает single-panel discipline;
- какой navigation state обязан храниться отдельно от customer shell;
- как устроены list/detail/compose flows;
- где разрешены multi-step input flows;
- как именно должно выглядеть поведение Back / Home / Refresh / Load more;
- где проходит граница между panel state, domain state и transient draft state.

Это **не visual design doc** и не SQL-спека.
Это operational UI contract под реализацию бота.

---

## 2. Executive summary

ManagerBot V1 использует **single-panel Telegram UX** с жёсткой дисциплиной навигации.

Ключевые решения:

1. **Один основной panel message на пользователя** внутри ManagerBot session.
2. **Никакой случайной многоэкранности.** Новый экран по умолчанию редактирует существующую панель.
3. **List-first manager UX.** Основной путь: queues → case list → case detail → action.
4. **Compose flows существуют отдельно от panel family**, но возвращают пользователя обратно в case detail.
5. **Queue context должен сохраняться** между переходами в detail и обратно.
6. **Back должен быть deterministic**, а не зависеть от "предыдущего сообщения" в чате.
7. **Manager session state живёт отдельно** от customer `ShellSessionState`.
8. **Load more вместо тяжёлой пагинации** для списков и timelines.
9. **Internal notes и customer replies разделяются уже на уровне UX**, а не только на уровне таблиц.
10. **Home и queue navigation важнее deep menu nesting.**

Базовая формула UI:

```text
Home
  -> Queues hub
      -> Queue list
          -> Case detail
              -> Reply / Note / Assign / Requeue / Escalate / Open linked artifact
```

---

## 3. Основные UX-принципы V1

### 3.1. Single-panel discipline

ManagerBot не должен вести себя как чат с россыпью живых экранов.

Canonical rule:

> У каждого manager user в каждый момент времени есть один основной panel message, который бот старается редактировать, а не плодить.

Это означает:

- panel rendering идёт через отдельный `ManagerPanelManager` или совместимый abstraction;
- при переходе между hub/list/detail бот делает `edit_message_text`, если это возможно;
- новый panel message создаётся только если старый недоступен, удалён или Telegram не даёт его отредактировать;
- panel message id хранится в `ManagerSessionState`, а не в customer shell state.

### 3.2. Clean-chat discipline

ManagerBot не должен превращать диалог в мусорник.

Нормальное поведение:

- hub/list/detail рендерятся в one live panel;
- callback interactions обычно только ack-аются и перерисовывают панель;
- случайные service confirmations не остаются висеть в чате, если можно обновить panel text;
- short-lived input prompts допустимы только для text-entry flows;
- после завершения compose flow бот должен возвращать пользователя в case detail panel.

### 3.3. List-first B2B operator UX

ManagerBot не должен начинаться с карточек, меню второго уровня и бесполезной "CRM-театральности".

V1 UI строится от рабочего ритма менеджера:

- сначала человек хочет понять, **что горит**;
- затем открыть **очередь**;
- затем увидеть **краткий список кейсов**;
- затем провалиться в **один кейс**;
- затем выполнить **одно действие**.

Поэтому primary flow V1:

```text
Home -> Queue family -> Queue list -> Case detail -> Action -> Case detail
```

### 3.4. No hidden state magic

Пользователь не должен гадать:

- в какой очереди он сейчас находится;
- чей это кейс;
- кто кого ждёт;
- reply уйдёт клиенту или останется заметкой;
- вернёт ли Back в правильное место.

Поэтому panel text должен честно показывать:

- active queue/filter;
- assignee;
- waiting-state;
- priority/escalation;
- compose mode, если пользователь введёт текст.

### 3.5. Action safety above speed

ManagerBot = internal operator tool.

Это означает:

- dangerous actions не должны быть спрятаны в один тап рядом с benign actions;
- reply клиенту и internal note не должны визуально сливаться;
- escalation/reassign/close/reopen требуют явно понятного действия;
- AI suggestions, когда появятся, не должны автоматически улетать клиенту.

---

## 4. ManagerBot surface boundaries

### 4.1. Что относится к ManagerBot surface

В V1 в ManagerBot surface входят:

- home panel;
- presence controls;
- queues hub;
- queue lists;
- case detail;
- reply flow;
- internal note flow;
- assignment and triage actions;
- reopen/resolve/close actions;
- linked artifact open actions;
- refresh and load more flows;
- future AI summary/suggested reply panels.

### 4.2. Что не относится к ManagerBot surface

В V1 не надо тащить сюда полноформатный customer shell.

В частности, ManagerBot не должен пытаться стать:

- полным каталог-ботом;
- заменой OwnerBot;
- отдельным "внутренним WhatsApp";
- universal backoffice для всех модулей;
- главным экраном AI-ассистента для всего проекта.

ManagerBot решает одну задачу:

> дать OWNER/MANAGER нормальный оперативный контур для обработки quote-based customer workload.

---

## 5. Panel families V1

В V1 фиксируются следующие canonical panel families.

### 5.1. `hub:*`

Панели верхнего уровня.

Canonical keys:

- `hub:home`
- `hub:queues`
- `hub:presence`
- `hub:help` (optional lightweight help)

### 5.2. `queue:*`

Семейство queue list panels.

Canonical keys V1:

- `queue:new`
- `queue:mine`
- `queue:unassigned`
- `queue:waiting_customer`
- `queue:waiting_me`
- `queue:urgent`
- `queue:escalated`
- `queue:resolved`
- `queue:closed` (optional in V1 if useful operationally)

Это logical keys. Реальный key может включать active filter hash/version, но canonical navigation должна мыслить именно этими семействами.

### 5.3. `case:*`

Case detail family.

Canonical keys:

- `case:detail`
- `case:thread`
- `case:artifacts` (optional as separate subpanel)
- `case:history` (optional later)

Для V1 достаточно, чтобы primary case view жила в `case:detail`.

### 5.4. `compose:*`

Text-entry / action arming family.

Canonical keys:

- `compose:reply`
- `compose:note`
- `compose:reassign` (if text-based explanation is used)
- `compose:close_reason` (optional)

Важно:
`compose:*` не обязаны жить как полноценные редактируемые панели. Это может быть armed input state + confirmation subpanel.

### 5.5. `modal:*` / `confirm:*`

Telegram не даёт настоящих модалок, но нам нужен canonical способ подтверждений.

Canonical keys:

- `confirm:resolve`
- `confirm:close`
- `confirm:reopen`
- `confirm:reassign`
- `confirm:escalate`

В V1 они могут быть реализованы как обычная panel replacement с explicit confirm/cancel.

---

## 6. Canonical navigation map

### 6.1. Top-level map

```text
hub:home
  -> hub:presence
  -> hub:queues
      -> queue:new
      -> queue:mine
      -> queue:unassigned
      -> queue:waiting_customer
      -> queue:waiting_me
      -> queue:urgent
      -> queue:escalated
      -> queue:resolved
          -> case:detail
              -> compose:reply
              -> compose:note
              -> confirm:resolve
              -> confirm:close
              -> confirm:reopen
              -> linked artifact open
```

### 6.2. Canonical return path

Primary return logic:

- из `case:detail` Back возвращает в **последнюю queue panel**, а не просто в queues hub;
- из `compose:*` successful submit возвращает в `case:detail`;
- из `compose:*` cancel возвращает в `case:detail`;
- из `confirm:*` cancel возвращает в `case:detail`;
- из `hub:queues` Back возвращает в `hub:home`;
- `Home` всегда ведёт в `hub:home`, независимо от текущего depth.

### 6.3. Deep-link behavior

Если manager заходит по deep link прямо в кейс:

- panel открывается как `case:detail`;
- session запоминает `return_queue_key = none`;
- Back в этом сценарии ведёт в `hub:queues`, а не в несуществующую очередь.

---

## 7. Home panel contract

### 7.1. Назначение

Home panel не должна быть перегруженной.

Она отвечает на три вещи:

- кто я в системе;
- в каком presence/status я сейчас;
- куда мне идти работать.

### 7.2. Что показывает `hub:home`

Минимум:

- title: `ManagerBot`;
- role label (`OWNER` / `MANAGER`);
- current presence (`online`, `busy`, `offline` или канонический V1 enum);
- key queue counters summary;
- last assigned/open case shortcut if useful;
- notice если есть overdue/escalated cases.

### 7.3. Home actions

Минимальный набор кнопок:

- `📥 Queues`
- `🟢 Presence`
- `🔄 Refresh`
- `🏠 Home` обычно не нужен на home itself

Опционально:

- `🔥 Urgent`
- `👤 My cases`

Но home не должен превращаться в dashboard-ёлку.

---

## 8. Presence panel contract

### 8.1. Назначение

Presence panel даёт менеджеру контролировать, должен ли routing layer активно подкидывать ему workload.

### 8.2. Canonical V1 presence values

Если в `25_case_statuses_and_routing.md` зафиксирован конкретный enum, UI должен использовать только его.

Ожидаемый набор V1:

- `online`
- `busy`
- `offline`

### 8.3. Presence panel content

Показывает:

- current presence;
- short explanation каждого статуса;
- effect on routing;
- optional timestamp last changed.

### 8.4. Presence actions

- `🟢 Online`
- `🟠 Busy`
- `⚫ Offline`
- `⬅️ Back`
- `🏠 Home`

### 8.5. UX rule

Presence change не должен плодить отдельные messages.

Правильное поведение:

- callback;
- DB update;
- panel refresh with confirmation inline in panel text.

---

## 9. Queues hub contract

### 9.1. Назначение

Queues hub = точка выбора рабочей очереди.

### 9.2. Что показывает `hub:queues`

Минимум:

- list canonical queues;
- counter per queue;
- optional compact legend по приоритетам;
- active presence reminder;
- optional note about overdue/escalations.

### 9.3. Canonical queue buttons

Минимальный V1 набор:

- `🆕 New`
- `👤 Mine`
- `📭 Unassigned`
- `⏳ Waiting customer`
- `🛠 Waiting me`
- `🔥 Urgent`
- `⬆️ Escalated`
- `✅ Resolved`

Optional:

- `📦 Closed`
- `🔄 Refresh`
- `⬅️ Back`
- `🏠 Home`

### 9.4. Queue hub is not a list

`hub:queues` не должен уже здесь раскрывать 20 кейсов.

Иначе:

- пропадает ясность;
- ломается consistent back-navigation;
- home and hub становятся indistinguishable.

---

## 10. Queue list panel contract

### 10.1. Queue list = primary working surface

Каждая queue panel должна вести себя одинаково по структуре.

### 10.2. Что хранит session для queue context

`ManagerSessionState` должен уметь помнить:

- `current_queue_key`
- `queue_filters`
- `queue_loaded_limit`
- `queue_cursor` / cursor-like continuation token if needed
- `queue_result_case_ids`
- `selected_quote_case_id`
- `return_queue_key`

Если нужны простые load-more списки без backend cursor, всё равно нужен `loaded_limit`.

### 10.3. Queue panel text structure

Ожидаемая структура:

1. queue title;
2. current count / loaded slice;
3. filter summary;
4. concise legend;
5. list of visible cases.

Примерно по смыслу, не по стилю:

```text
Queue: Mine
Presence: online
Showing 10 of 24

#Q-1042  Urgent  Waiting me  Customer: Acme
Need revision after stock mismatch
Last customer message: 14:22

#Q-1039  Normal  Waiting customer  Customer: Beta
Sent revised offer
Last manager reply: 13:08
```

### 10.4. Case row contract in queue list

Каждая строка списка должна содержать минимум:

- stable public quote number;
- priority marker;
- waiting-state marker;
- brief assignee marker if relevant;
- customer/company label;
- short subject/summary;
- last activity hint.

### 10.5. Queue list actions

Минимальный набор:

- one button per visible case: `Open #...`
- `⬇️ Load more` when list not exhausted
- `🔄 Refresh`
- `⬅️ Back`
- `🏠 Home`

### 10.6. Load more behavior

Load more должен:

- увеличивать `queue_loaded_limit`;
- перерисовывать ту же panel;
- не сбрасывать queue selection;
- не плодить новые сообщения.

### 10.7. Empty queue behavior

Пустая очередь не должна выглядеть как ошибка.

Нужен explicit empty-state text:

- queue title;
- zero items;
- refresh action;
- back/home.

Optional:
- shortcut to nearest relevant queue.

---

## 11. Case detail panel contract

### 11.1. Case detail = manager command center

Case detail — главный экран работы по одному кейсу.

Он должен отвечать на вопросы без перехода по пяти подменю:

- какой это кейс;
- чей он;
- кто назначен;
- кто кого ждёт;
- что последнее произошло;
- что я могу сделать сейчас.

### 11.2. What `case:detail` must show

Минимальный блок:

- quote public number;
- commercial status;
- operational status;
- waiting state;
- priority;
- escalation level if any;
- assignee;
- customer/company;
- last customer message time;
- last manager message time;
- SLA due / overdue signal;
- compact latest external thread slice;
- compact latest internal notes count or preview;
- linked artifacts summary.

### 11.3. Detail text structure

Примерная структура:

```text
Case #Q-1042
Customer: Acme LLC
Commercial: open
Ops: active
Waiting: manager
Priority: urgent
Assignee: @manager_1
SLA: overdue by 18m

Latest external updates:
- Customer: Need delivery this week
- Manager: Checking availability and alternatives

Internal:
- 2 notes
- Last note by OWNER: approve 3% override if margin preserved

Linked:
Draft #D-77 · Quote PDF · Order none
```

### 11.4. Detail actions

Минимальный V1 набор:

- `💬 Reply to customer`
- `📝 Internal note`
- `👤 Assign to me` / `↔️ Reassign`
- `⏸ Waiting customer`
- `🛠 Back to work` / `Set waiting me`
- `⬆️ Escalate`
- `✅ Resolve`
- `🔒 Close`
- `🔄 Refresh`
- `📄 Open artifacts`
- `🕘 Load more thread`
- `⬅️ Back`
- `🏠 Home`

Не обязательно все в одной панели одновременно, но logical availability должна быть именно такой.

### 11.5. Case detail must not become mega-menu

Не надо превращать detail panel в 18 рядов кнопок.

Нормальная V1 стратегия:

- first row: primary actions (`Reply`, `Note`)
- second row: workload actions (`Assign`, `Waiting`, `Escalate`)
- third row: outcome actions (`Resolve`, `Close`)
- utility row: (`Refresh`, `Artifacts`, `Load more`)
- nav row: (`Back`, `Home`)

---

## 12. External thread presentation

### 12.1. Thread in case detail is a slice, not full transcript

В V1 не надо пытаться выводить полную переписку на одном экране.

Case detail показывает только **latest visible slice**.

Для этого state должен хранить:

- `thread_loaded_limit`

### 12.2. Load more thread behavior

`Load more thread`:

- увеличивает `thread_loaded_limit`;
- не меняет `selected_quote_case_id`;
- не выбрасывает пользователя из `case:detail`;
- не открывает отдельный чат.

### 12.3. Presentation rule

Thread entries должны визуально различаться минимум по направлениям:

- `Customer:`
- `Manager:`
- optional delivery marker if failed/pending

### 12.4. Internal notes never render as customer thread entries

Даже если "технически удобно" засунуть всё в одну timeline.

Нет.

External thread и internal notes должны отличаться уже на UI уровне.

---

## 13. Internal notes UX contract

### 13.1. Internal note = отдельный action type

Internal note должна быть настолько визуально отдельной, чтобы менеджер не спутал её с reply клиенту.

### 13.2. Entry path

Из `case:detail` кнопка `📝 Internal note` делает:

- arm input state `compose:note`;
- panel text меняется и явно говорит: следующий текст останется только внутри команды;
- user sends message;
- note persists into `manager.quote_case_internal_notes` equivalent;
- panel returns to `case:detail` with inline confirmation.

### 13.3. Cancel behavior

Во время armed note mode должны работать:

- `Cancel note`
- `Back to case`

Иначе Telegram input flows превращаются в дешёвый аттракцион тревожности.

---

## 14. Customer reply UX contract

### 14.1. Reply flow must be explicit

Кнопка `💬 Reply to customer` должна однозначно переводить UI в reply mode.

Panel text обязан явно показать:

- что следующее сообщение уйдёт клиенту;
- в какой кейс оно уйдёт;
- optional delivery expectations.

### 14.2. Reply flow state

`ManagerSessionState` должен уметь хранить минимум:

- `armed_input_kind = reply`
- `armed_quote_case_id`
- `draft_text` optional
- `return_panel_key = case:detail`

### 14.3. Successful reply behavior

После отправки manager reply:

- reply сохраняется в external thread store;
- создаётся/обновляется delivery attempt;
- ops state обновляется согласно routing rules;
- panel возвращается в `case:detail`;
- latest thread slice уже содержит новую manager entry.

### 14.4. Failure behavior

Если delivery клиенту не удалась:

- сообщение не должно теряться;
- в panel detail должно быть видно, что delivery failed/pending;
- менеджер должен иметь способ retry/refresh later.

---

## 15. Assignment and routing actions UX

### 15.1. Minimal assignment flows V1

Минимум нужны:

- `Assign to me`
- `Unassign` (owner or policy-dependent)
- `Reassign` (later if multiple managers present)

### 15.2. UX requirement

Assignment action не должен выкидывать пользователя в отдельный странный wizard, если он не нужен.

Предпочтительно:

- one-tap `Assign to me`
- explicit confirm only where risky
- detail refresh after state change

### 15.3. Waiting-state actions

Из detail должны быть доступны at least:

- `Set waiting customer`
- `Set waiting me`
- `Resume work` / `Back to active`

Это не отдельный long wizard. Это status transition actions.

### 15.4. Escalation action

Escalation может потребовать optional note/reason.

В V1 допустимы два варианта:

1. quick escalate button without free-text reason;
2. escalate → armed input for reason.

Но поведение должно быть consistent по всему боту.

---

## 16. Resolve / close / reopen UX contract

### 16.1. Resolve is not close

UI должен разделять:

- `Resolve` = active handling done;
- `Close` = terminal operational state;
- `Reopen` = explicit return into working queues.

### 16.2. Confirmation behavior

Для `Resolve`, `Close`, `Reopen` допустим confirm step.

Canonical rule:

- dangerous/terminal actions желательно подтверждать;
- confirm panel replaces current panel;
- cancel returns to `case:detail`.

### 16.3. Post-action behavior

После `Resolve` / `Close` / `Reopen`:

- detail panel refreshes;
- queue placement changes accordingly;
- if user presses Back after action, он возвращается в last queue context, уже с обновлённым списком.

---

## 17. Linked artifacts UX

### 17.1. What counts as linked artifacts

V1 detail panel может открывать связанные сущности:

- procurement draft;
- quote revision/PDF;
- related order;
- project/object if linked;
- relevant documents.

### 17.2. UX rule

ManagerBot не должен копировать весь customer shell, но должен давать **достаточный drilldown**.

Допустимые стратегии V1:

- send document/file directly when requested;
- open compact artifact summary subpanel;
- deep-link into a specific artifact view if such manager-safe view exists.

### 17.3. No context loss rule

После открытия/отправки артефакта manager не должен терять current case context.

То есть:

- `selected_quote_case_id` remains;
- Back returns to `case:detail`.

---

## 18. ManagerSessionState contract

### 18.1. Отдельный state обязателен

ManagerBot не использует customer `ShellSessionState`.

Нужен отдельный state object, условно:

- `ManagerSessionState`

и отдельный Redis key prefix, например:

- `tf:manager:session:{telegram_user_id}`

### 18.2. Required state sections V1

Минимально state должен уметь хранить:

#### Top-level

- `telegram_user_id`
- `panel_message_id`
- `active_panel_key`
- `back_panel_key`
- `selected_quote_case_id`
- `last_notice`

#### Queue context

- `current_queue_key`
- `queue_loaded_limit`
- `queue_cursor` optional
- `queue_result_case_ids`
- `queue_filters`
- `return_queue_key`

#### Case context

- `thread_loaded_limit`
- `artifacts_subpanel_open` optional

#### Compose context

- `armed_input_kind`
- `armed_quote_case_id`
- `armed_prompt`
- `pending_action`
- `draft_text` optional

#### Presence/UI context

- `presence_snapshot` optional cached view
- `last_refresh_at`

### 18.3. What must not live only in session state

Следующие вещи **не могут быть only-in-session**:

- assignee;
- operational status;
- waiting-state;
- notes;
- replies;
- delivery status;
- routing decisions;
- queue truth.

Это доменная truth и живёт в БД.

Session state хранит только UI/navigation/transient compose context.

---

## 19. Callback naming and routing contract

### 19.1. Separate callback namespace

ManagerBot должен иметь собственный callback namespace.

Например:

- `tfm:nav:*`
- `tfm:queue:*`
- `tfm:case:*`
- `tfm:compose:*`
- `tfm:presence:*`
- `tfm:confirm:*`

Не надо смешивать это с customer callback namespace.

### 19.2. Canonical actions

Примерно такой словарь:

- `presence:set:<value>`
- `queue:open:<queue_key>`
- `queue:more:<queue_key>`
- `case:open:<quote_case_id>`
- `case:refresh:<quote_case_id>`
- `case:reply:<quote_case_id>`
- `case:note:<quote_case_id>`
- `case:assign_me:<quote_case_id>`
- `case:set_waiting:<quote_case_id>:<waiting_state>`
- `case:resolve:<quote_case_id>`
- `case:close:<quote_case_id>`
- `case:reopen:<quote_case_id>`
- `case:more_thread:<quote_case_id>`
- `nav:back`
- `nav:home`

Точная сериализация может отличаться. Contract важен на уровне семантики.

---

## 20. Error and recovery UX

### 20.1. Panel recovery

Если panel message удалён или недоступен:

- bot sends a new panel message;
- updates `panel_message_id` in `ManagerSessionState`;
- does not reset domain context unless truly necessary.

### 20.2. Stale case context

Если кейс недоступен, закрыт миграцией, или пользователь потерял доступ:

- detail panel заменяется explicit recovery notice;
- user gets `Back to queues` and `Home`.

### 20.3. Compose recovery

Если manager armed reply/note, но state потерян:

- incoming text should not silently become a reply;
- bot must respond with explicit recovery prompt and reopen `case:detail` or `hub:home`.

---

## 21. Refresh semantics

### 21.1. Refresh is a first-class action

У queue и case panels должен быть explicit `Refresh`.

### 21.2. What refresh does

#### Queue refresh

- re-queries current queue read model;
- keeps active filters;
- preserves loaded limit where sensible;
- re-renders same panel.

#### Case refresh

- reloads ops state;
- reloads latest thread slice;
- reloads note summary;
- reloads delivery statuses;
- re-renders same panel.

### 21.3. What refresh does not do

Refresh не должен:

- сбрасывать current queue selection;
- выбрасывать пользователя в home;
- сбрасывать thread limit без причины;
- silently close compose mode.

---

## 22. Notifications and active panel interplay

### 22.1. Incoming events do not automatically hijack the panel

Если пользователь сейчас читает один кейс, а в другом прилетает новое сообщение, V1 не должен самовольно уводить экран.

Правильное поведение:

- update counters in future refresh;
- optional short notification message;
- optional badge-like summary next time home/queue opens.

### 22.2. Current open case refresh

Если new event прилетел именно в открытый кейс, допустимо:

- keep panel as is;
- show `Refresh` affordance;
- optional silent stale notice in panel text after next action.

Auto-refresh допустим later, но не нужен как обязательный V1 behavior.

---

## 23. AI panel implications for future PR

### 23.1. AI must fit existing panel model

Когда появится AI copilot:

- summary и suggested reply должны жить как extension to `case:detail` or `case:ai` subpanel;
- AI не должен ломать back-navigation;
- AI panel должен возвращать в `case:detail`.

### 23.2. No AI-first home

ManagerBot home не должен превращаться в "поговорите с ИИ".

Рабочий центр — queues and cases.
AI — инструмент внутри кейса.

---

## 24. Out of scope for V1

Чтобы потом никто не изобразил, что "раз мы уже здесь, давайте ещё и это".

Вне V1:

- multi-case split screen;
- concurrent multiple live panels per manager;
- full-text case inbox search across all histories;
- kanban board inside Telegram;
- topic-first team collaboration;
- rich inline artifact editing;
- automatic push re-render on every incoming event;
- supervisor-only dedicated menu tree;
- universal admin settings surface inside ManagerBot.

---

## 25. Canonical V1 panel set

Ниже минимальный набор экранов, который считается достаточным для первого боевого контура.

### 25.1. Must-have panels

- `hub:home`
- `hub:presence`
- `hub:queues`
- `queue:new`
- `queue:mine`
- `queue:unassigned`
- `queue:waiting_customer`
- `queue:waiting_me`
- `queue:urgent`
- `queue:escalated`
- `case:detail`
- `compose:reply`
- `compose:note`
- `confirm:resolve`
- `confirm:close`
- `confirm:reopen`

### 25.2. Nice-to-have but optional in first code wave

- `queue:resolved`
- `queue:closed`
- `case:artifacts`
- `confirm:reassign`
- `compose:escalation_reason`
- lightweight `hub:help`

---

## 26. Implementation implications

Этот документ означает для кодовой реализации следующее:

1. Нужен отдельный `app/manager_bot/*` surface.
2. Нужен отдельный `ManagerSessionState` + store.
3. Нужен отдельный callback codec/namespace.
4. Нужен manager-specific panel manager wrapper или reuse existing pattern через отдельный contract.
5. Queue list rendering должен быть uniform across queue families.
6. Case detail rendering должен читать из domain read model, а не собирать данные наугад по пяти сервисам в handler.
7. Compose flows должны быть explicit и reversible.
8. Back navigation должна быть deterministic и state-based.
9. Load more для queues и thread должен быть stateful.
10. Internal notes и customer replies должны быть разделены и в state, и в UI text, и в persistence.

---

## 27. Final contract

ManagerBot V1 Telegram UX строится как **single-panel, list-first, deterministic operator surface**.

Главные правила:

- один живой panel message на пользователя;
- queues → case → action как основной путь;
- отдельный manager session state;
- queue context не теряется;
- Back детерминированный;
- Load more вместо грязной пагинации;
- reply и internal note разведены жёстко;
- panel text всегда честно показывает operational truth;
- Telegram UI отражает domain model, а не пытается заменить её импровизацией.

Если будущий PR ломает эти правила ради "удобно прямо сейчас", значит он строит не ManagerBot, а новую форму техдолга.

