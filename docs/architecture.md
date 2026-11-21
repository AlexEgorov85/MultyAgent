# Архитектура

## Слои

```text
assistant-ui (Next.js)
        │ LangGraph API
        ▼
MainGraph: Router + Guardrails + память
        │ FIPA-ACL
        ├── AnalyticsAgent   (NL→SQL, шаблоны, drill-down, multi-tool)
        ├── RetrievalAgent   (pgvector + FTS, цитаты, критик)
        ├── ReportAgent      (проект акта + Inspector)
        └── InvestigationCoordinator (2 раунда ACL)
        │
PostgreSQL 16 (pgserver): audit.* + pgvector
```

## Основной граф

`load_memory → save_memory → resolve_query → guard_request → router → branch → guard_answer → present → finalize`

- Router возвращает `RouteDecision`.
- Все ветки вызываются только ACL-сообщениями.
- `thread_id` хранит краткосрочную память (InMemorySaver).
- `auditor_id` загружает долгосрочный профиль из `auditor_memory`.

## Диалог

`load_memory` собирает `dialogue_context` из последних реплик треда:

- до 8 сообщений и 4000 символов;
- текущий вопрос исключается;
- если тред потерян после перезапуска backend, используется
  `client_history` от UI (последние реплики из localStorage).

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

`audit_pockets → audits → acts → act_items → scripts` + `script_runs`, `deviations`, `knowledge_chunks`, `auditor_memory`, `dataset_metadata`.

## Протокол

Каждое межагентное взаимодействие — `ACLMessage`:
`performative`, `sender`, `receiver`, `content`, `conversation_id`,
`reply_with`, `in_reply_to`, `protocol=fipa-acl`, `language=ru`.

## Ограничения

- `InMemorySaver` не переживает перезапуск backend. UI присылает
  `client_history`, поэтому контекст последних реплик восстанавливается,
  но полная серверная история треда — нет.
- `pgserver` — встроенный сервер для учебного запуска, не production.
- Данные синтетические, кроме методичек.
