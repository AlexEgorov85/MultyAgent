# Архитектура

## Слои

```text
assistant-ui (Next.js)
        │ LangGraph API
        ▼
MainGraph: Router + Guardrails + память + диалоговый контекст
        │ FIPA-ACL
        ├── AnalyticsAgent   (NL→SQL, шаблоны, drill-down, multi-tool)
        ├── RetrievalAgent   (pgvector + FTS, цитаты, критик)
        ├── ReportAgent      (проект акта + Inspector)
        └── InvestigationCoordinator (2 раунда ACL)
        │
PostgreSQL 16 (pgserver): audit.* + pgvector
```

## Основной граф

`load_memory → resolve_query → save_memory → guard_request → router → branch → guard_answer → present → finalize`

- Router возвращает `RouteDecision` и выбирает маршрут по смыслу вопроса
  через LLM; жёсткие доменные эвристики не используются.
- `unsafe` определяется детерминированным `guard_request` до Router.
  Если LLM недоступна, Router использует минимальный fallback
  (smalltalk / `out_of_domain`) и не угадывает доменный маршрут.
- Все ветки вызываются только ACL-сообщениями.
- `thread_id` хранит краткосрочную память (InMemorySaver).
- `auditor_id` загружает долгосрочный профиль из `auditor_memory`.

## Диалог и история

История диалога хранится в PostgreSQL:

```text
audit.chat_threads   (conversation_id, auditor_id, title, updated_at)
audit.chat_messages  (conversation_id, turn_id, role, content, trace)
```

Ключ — стабильный `conversation_id` из UI (`chat.id`), а не backend
`thread_id`. Поэтому пересоздание LangGraph-треда после перезапуска backend
не теряет контекст.

`load_memory` собирает `dialogue_context`:

- сначала из `audit.chat_messages` по `conversation_id`;
- если истории в БД ещё нет — из сообщений LangGraph;
- если потерян и тред, и БД-история — из `client_history` от UI;
- до 12 сообщений и 6000 символов, текущий вопрос исключается.

`finalize` одной транзакцией пишет пару `user + assistant`, `trace` и
`resolved_query`. Повторный запуск с тем же `turn_id` не создаёт дублей.

`resolve_query` переформулирует уточнения («а за 2025?», «почему?», «а по
картам?») в самостоятельный вопрос. Результат сохраняется в `resolved_query`;
исходный текст остаётся в `user_query`.

- `guard_request` проверяет и исходный, и переформулированный вопрос.
- `router` и все подагенты получают `resolved_query`.
- `dialogue_context` передаётся в ACL-content полем
  `conversation_context`, поэтому LLM видит историю, даже если
  переформулировка не удалась.
- Если модель не перенесла код проверки, Report и Analytics берут последний
  `AUD-…` из `conversation_context`.
- В `trace` появляется шаг «Уточнение вопроса» с парой
  «исходный → самостоятельный».

## Подагенты

| Агент | Состояние | Ключевые узлы |
|---|---|---|
| Analytics | `AnalyticsState` | plan → validate → execute → repair → summarize |
| Retrieval | `RetrievalState` | retrieve → generate → critic → rewrite |
| Report | `ReportState` | collect_facts → draft → inspector → revise |
| Investigation | `InvestigationState` | plan → round1 → round2 → synthesize |

## Данные

`audit_pockets → audits → acts → act_items → scripts` + `script_runs`, `deviations`, `knowledge_chunks`, `auditor_memory`, `chat_threads`, `chat_messages`, `dataset_metadata`.

## Протокол

Каждое межагентное взаимодействие — `ACLMessage`:
`performative`, `sender`, `receiver`, `content`, `conversation_id`,
`reply_with`, `in_reply_to`, `protocol=fipa-acl`, `language=ru`.

В `content` запроса Orchestrator → агент дополнительно передаются
`original_question` и `conversation_context`, чтобы подагент мог
восстановить ссылки, если переформулировка уточнения не удалась.

## Ограничения

- `InMemorySaver` не переживает перезапуск backend: сам LangGraph-тред
  теряется. Но история диалога уже лежит в `audit.chat_messages` и
  восстанавливается по стабильному `conversation_id`; UI дополнительно
  присылает `client_history` как аварийный fallback.
- Список чатов в UI пока хранится в `localStorage`. Для истории на другом
  устройстве нужен отдельный API `GET /chats` поверх `chat_threads`.
- `pgserver` — встроенный сервер для учебного запуска, не production.
- Данные синтетические, кроме методичек.
