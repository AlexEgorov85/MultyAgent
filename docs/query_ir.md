# Query IR: semantic layer и детерминированный SQL

Analytics-агент больше не просит LLM сразу писать SQL. Первый шаг —
`QueryPlan`: что считать, по каким разрезам и с какими фильтрами. SQL
собирает `src/query/compiler.py` из каталога `src/semantic/catalog.py`.

## Поток

```text
вопрос
  → LLM plan_query (structured output)
  → QueryPlan(metric, dimensions, filters)
  → compiler + semantic catalog
  → read-only SQL
  → sql_guard
  → execute
  → summarize
```

Если метрика/разрез/значение не поддержаны, Analytics откатывается на
старый `plan_sql` (free SQL). Это safety net, а не основной путь.

## Пример

Вопрос:

> Сколько отклонений и проблем в пунктах 2026 года?

LLM возвращает:

```json
{
  "metric": "item_count",
  "dimensions": ["item_type"],
  "filters": [{"field": "year", "value": 2026}],
  "order_by": "count_desc",
  "limit": 200,
  "reason": "разрез по типу находки"
}
```

Компилятор строит:

```sql
SELECT i.item_type AS item_type, count(*) AS cnt
FROM audit.act_items i
JOIN audit.acts ac ON ac.act_id = i.act_id
JOIN audit.audits a ON a.audit_id = ac.audit_id
JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id
WHERE (p.pocket_year = 2026)
GROUP BY i.item_type
ORDER BY cnt DESC
LIMIT 200
```

## Метрики

| Метрика | Что считает |
|---|---|
| `audit_count` | проверки |
| `auditor_count` | аудиторы |
| `act_count` | акты |
| `item_count` | пункты |
| `critical_item_count` | критические пункты |
| `overdue_item_count` | просроченные незакрытые пункты |
| `repeat_item_count` | повторные находки |
| `no_script_item_count` | пункты без скриптов |
| `script_count` | скрипты |
| `run_count` | запуски скриптов |
| `run_script_mismatch_count` | расхождения запуска и скрипта |
| `deviation_count` | отклонения |

## Измерения и фильтры

Измерения — только из каталога метрики. Основные:

`year`, `theme`, `status`, `audit_type`, `risk_level`, `item_type`,
`title`, `responsible_unit`, `is_repeat`, `audit_code`, `act_status`,
`lead_auditor_id`, `approved_by`, `language`, `run_status`, `severity`,
`entity_type`, `metric_name`, `specialization`.

Для `specialization` используется `op=contains`:

```json
{"field": "specialization", "value": "ипотека", "op": "contains"}
```

## Валидация

`QueryCompileError`, `KeyError` и неизвестные измерения/значения не
попадают в SQL: Analytics откатывается на fallback. В `metrics.plan_source`
пишется `query_ir`, чтобы это было видно в бенчмарке и trace.

## Тесты

```powershell
.venv\Scripts\python.exe -m pytest tests\test_query_compiler.py -q
.venv\Scripts\python.exe -m pytest tests\test_analytics_agent.py -q
```

## Связанные слои

- `src/capabilities/` — typed-шаблоны и deterministic matcher. Явные
  template-вопросы обрабатываются до Query IR, без LLM-планировщика.
- `src/dialogue_slots.py` — слоты year/theme/item_type/risk/status/audit_code.
  Потерянный слот добавляется в `resolved_query`, поэтому QueryPlan видит
  контекст даже при слабом resolver.

## Что дальше

- Golden SQL для benchmark-кейсов.
- Перевести `missing_question_filters` и repair на IR.
- Добавить list-метрики (не только count) для «покажи пункты».
- Использовать slots в QueryPlan напрямую, а не только через текст запроса.
