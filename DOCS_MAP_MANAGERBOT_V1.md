# ManagerBot Docs Map V1

**Назначение:** карта документов для manager-side слоя.  
**Принцип:** README фиксирует канон, остальные документы раскрывают его по слоям.  
**Версия карты:** 25 March 2026.

---

## 0. Главный входной документ

### `README_MANAGERBOT_V1.md`
Главный canonical-док.

Фиксирует:

- зачем нужен ManagerBot;
- почему ManagerBot primary, а group topics secondary;
- human-first + AI-copilot модель;
- V1 decisions: `OWNER/MANAGER only`, single operator org per deployment, separate manager session state;
- quote-case as V1 anchor;
- separation of commercial status vs manager operational status;
- persistent numbering;
- dedicated external thread and internal notes persistence;
- MVP-границы;
- roadmap.

---

## 1. Документы, которые нужно создать

### `00_overview_managerbot.md`
Короткий обзор manager-side контура:
- что это за продукт;
- зачем он нужен;
- какую дыру закрывает между customer bot и реальной работой команды.

### `10_architecture_managerbot.md`
Архитектура ManagerBot:

- primary manager workspace;
- DB-first truth;
- single operator org assumption for V1;
- связь с TradeFlow;
- optional group bridge;
- AI-copilot placement;
- separate manager session state;
- separate manager read/write seams.

### `15_access_and_scope_managerbot.md`
Access/scope документ для V1:

- existing roles only: `OWNER`, `MANAGER`;
- почему в V1 не вводятся `senior/supervisor` как system roles;
- границы owner vs manager;
- company roles vs internal operator roles;
- deployment assumption and operator scope.

### `20_domain_model_manager_cases.md`
Доменная модель manager-side:

- existing `quote_cases` as V1 anchor;
- `quote_case_ops_state`;
- external thread entry;
- internal note;
- assignment history;
- presence state;
- routing decision;
- SLA-related fields.

### `25_case_statuses_and_routing.md`
Статусы, waiting states, priority, escalation и routing rules.

Здесь же описать:

- commercial status vs operational status split;
- human_requested;
- safe-auto lanes;
- human-required lanes;
- offline/away manager behavior.

### `30_managerbot_panels_and_navigation.md`
Контракт по панелям и навигации:

- home;
- queues;
- case list;
- case detail;
- internal notes;
- assignment;
- AI assist panel;
- deterministic back behavior;
- clean chat expectations;
- manager state isolation from customer shell.

### `35_manager_reply_flow.md`
Полный сценарий ответа менеджера:

- customer message -> external thread persistence;
- queue/state update;
- manager reply -> delivery attempt;
- delivery success/failure;
- state update after reply;
- repeated customer message handling.

### `40_presence_sla_and_assignment.md`
Presence states, assignment rules, SLA markers и queue logic:

- `online / busy / away / offline`;
- assign/reassign rules;
- owner override rules;
- stale assignment handling;
- overdue logic.

### `45_ai_copilot_rules.md`
Правила встроенного AI:

- summary;
- suggested reply;
- risk flags;
- missing-fields prompt;
- safe auto;
- что AI нельзя доверять;
- как manager AI seam подключается, но не становится отдельным продуктом раньше времени.

### `50_external_vs_internal_threads.md`
Разделение customer-visible и internal-only коммуникации.

Критично зафиксировать:

- thread store не живёт в analytics;
- external thread != internal notes;
- delivery state belongs to external thread;
- AI summaries/internal remarks не текут к клиенту.

### `55_group_topics_bridge.md`
Optional collaboration layer, не primary workflow:

- зачем нужен;
- как синкается с БД;
- какие события туда идут;
- что не должно жить только там;
- как bridge выключается без потери истины.

### `60_data_model_postgres_managerbot.md`
Постгрес-модель manager-side контура.

Нужно описать:

- новые таблицы V1 рядом с existing quote domain;
- stable display/public number fields;
- внешние ключи;
- индексы;
- audit/timestamp fields;
- soft archive assumptions if нужны;
- что не надо делать через “универсальную таблицу на всё”.

### `65_integrations_managerbot.md`
Интеграции:

- TradeFlow domain access;
- notifications;
- customer bot handoff points;
- optional group bridge;
- AI services;
- future web/admin seams;
- manager integration flag/seam status.

### `70_notifications_and_delivery.md`
События и доставка:

- new customer message;
- manager reply delivered/failed;
- case assigned;
- case escalated;
- SLA warning;
- acknowledgement sent;
- retry/recovery expectations.

### `75_testing_strategy_managerbot.md`
Тестовая стратегия:

- service tests;
- persistence tests;
- bot panel tests;
- callback tests;
- routing/delivery tests;
- AI decision tests with fakes;
- regression checks against customer shell state.

### `80_non_goals_and_guardrails_managerbot.md`
Что не делать:

- не делать AI вместо сервиса;
- не делать group-only архитектуру;
- не делать giant universal case engine в V1;
- не смешивать internal/external threads;
- не смешивать manager state с customer shell state;
- не пихать business logic в handlers;
- не городить новые system roles без отдельного решения.

### `90_pr_plan_managerbot.md`
Roadmap manager-side PR wave:

- MPR0 docs freeze;
- MPR1 thread foundation + stable identifiers;
- MPR2 ops state + queues;
- MPR3 ManagerBot bootstrap surface;
- MPR4 reply delivery + notes;
- MPR5 AI copilot;
- MPR6 optional group bridge / operations polish.

### `95_seed_and_demo_scenarios_managerbot.md`
Набор seed/demo кейсов для локального тестирования:

- new quote case;
- waiting customer;
- escalated case to owner;
- offline manager + safe auto ack;
- urgent case;
- delivery failure case.

---

## 2. Минимальный пакет для старта с кодингом

Если не хочется сразу писать весь комплект, минимально обязательны:

1. `README_MANAGERBOT_V1.md`
2. `10_architecture_managerbot.md`
3. `20_domain_model_manager_cases.md`
4. `25_case_statuses_and_routing.md`
5. `30_managerbot_panels_and_navigation.md`
6. `35_manager_reply_flow.md`
7. `60_data_model_postgres_managerbot.md`
8. `75_testing_strategy_managerbot.md`
9. `80_non_goals_and_guardrails_managerbot.md`
10. `90_pr_plan_managerbot.md`

С этого уже можно стартовать кодинг без хаоса и без иллюзий, что недописанный persistence magically соберётся сам.

---

## 3. Рекомендуемый порядок написания docs

1. `README_MANAGERBOT_V1.md`
2. `10_architecture_managerbot.md`
3. `20_domain_model_manager_cases.md`
4. `25_case_statuses_and_routing.md`
5. `30_managerbot_panels_and_navigation.md`
6. `35_manager_reply_flow.md`
7. `60_data_model_postgres_managerbot.md`
8. `75_testing_strategy_managerbot.md`
9. `80_non_goals_and_guardrails_managerbot.md`
10. `90_pr_plan_managerbot.md`

Потом уже добивать:

11. `15_access_and_scope_managerbot.md`
12. `40_presence_sla_and_assignment.md`
13. `45_ai_copilot_rules.md`
14. `50_external_vs_internal_threads.md`
15. `55_group_topics_bridge.md`
16. `65_integrations_managerbot.md`
17. `70_notifications_and_delivery.md`
18. `95_seed_and_demo_scenarios_managerbot.md`

---

## 4. Что именно изменилось в этой карте

По сравнению с ранней версией карты теперь явно зафиксировано:

- V1 uses only `OWNER` and `MANAGER`;
- `senior/supervisor` убраны из V1 role model и не должны протаскиваться как system roles;
- single operator org per deployment;
- separate manager session state как обязательное решение;
- `quote_cases` as V1 anchor;
- persistent numbering и dedicated thread persistence как обязательный фундамент;
- testing/data-model docs подняты в минимально обязательный пакет.

---

## 5. Главный принцип

Документы по ManagerBot должны быть:

- конкретными;
- модульными;
- жёсткими по контрактам;
- достаточно приземлёнными к текущему коду;
- без giant markdown-простыней “обо всём”;
- такими, чтобы Codex не трактовал архитектуру творчески после полуночи.
