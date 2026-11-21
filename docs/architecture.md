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

`load_memory → save_memory → guard_request → router → branch → guard_answer → finalize`

- Router возвращает `RouteDecision`.
- Все ветки вызываются только ACL-сообщениями.
- `thread_id` хранит краткосрочную память (InMemorySaver).
- `auditor_id` загружает долгосрочный профиль из `auditor_memory`.

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

- `InMemorySaver` не переживает перезапуск backend.
- `pgserver` — встроенный сервер для учебного запуска, не production.
- Данные синтетические, кроме методичек.
