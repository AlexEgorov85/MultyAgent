# Query IR: semantic layer и детерминированный SQL

Analytics-агент больше не просит LLM сразу писать SQL. Первый шаг —
`QueryPlan`: что считать, по каким разрезам и с какими фильтрами. SQL
собирает `src/query/compiler.py` из каталога `src/semantic/catalog.py`.

## Поток

```text
вопрос
  → LLM plan_query (structured output)
  → QueryPlan(metric, dimensions, filters, template_key)
  → complete_query_plan: доменные сигналы semantic layer
  → проверка покрытия вопроса (та же для шаблона и для SQL)
  → шаблон выбран LLM и прошёл контракт ИЛИ compiler + semantic catalog
  → read-only SQL
  → sql_guard
  → execute
  → summarize
```

Если метрика/разрез/значение не поддержаны или план не покрывает
вопрос, Analytics откатывается на старый `plan_sql` (free SQL). Это
safety net, а не основной путь.

Шаблон выбирает LLM: `QueryPlan.template_key`. Но шаблон — это execution
strategy, а не второй источник смысла. Код проверяет его контракт
(`src/query/templates.py`): метрику, обязательные/допустимые разрезы и
фильтры. Шаблон запускается, только если контракт полностью покрывает
план; иначе он отклоняется, и SQL собирает компилятор. Так LLM может
выбрать шаблон, но не может подменить им вопрос.

Детерминированного fast path по ключевым словам больше нет: выбор
шаблона — решение модели, а не regex-матчера.

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

`year`, `theme`, `pocket`, `status`, `audit_type`, `risk_level`,
`item_type`, `title`, `responsible_unit`, `is_repeat`, `audit_code`,
`act_status`, `lead_auditor_id`, `approved_by`, `language`, `run_status`,
`severity`, `entity_type`, `metric_name`, `specialization`.

`pocket` — карман аудита (год + тема). Это отдельное измерение, а не
`status`: «по каждому карману» нельзя выразить разрезом по статусам.

Для `specialization` используется `op=contains`:

```json
{"field": "specialization", "value": "ипотека", "op": "contains"}
```

Период `year="last"` компилируется в максимальный год данных:

```sql
p.pocket_year = (SELECT max(p_last.pocket_year) FROM audit.audit_pockets p_last)
```

«Закрытая проверка» — `status="завершена"`, «закрытый пункт» —
`status="закрыт"`. Эти значения выбираются по метрике, а не по слову
«закрыт» вне контекста.

## Дополнение и проверка плана

LLM может вернуть верный смысл в `reason`, но пустые
`dimensions`/`filters` или выбрать шаблон, который не покрывает вопрос.
Поэтому между `plan_query` и компилятором работает детерминированный
слой `src/query/intent.py`:

1. `question_signals` (`src/semantic/catalog.py`) извлекает из текста
   доменные сигналы: разрез по карманам/годам/статусам, «последний год»,
   закрытую проверку, темы, языки, AUD-код.
2. `complete_query_plan` дополняет `QueryPlan`, не перезаписывая уже
   заданные условия. Если названо несколько статусов/тем/языков, это
   разрез, а не несколько одновременных фильтров.
3. `missing_question_filters` проверяет, что SQL (или шаблон) реально
   содержит нужные разрезы и значения. Проверка общая: она применяется
   и к Query IR, и к готовому шаблону.

Шаблон не является вторым источником истины. Контракт шаблона описывает,
какие метрики, разрезы и фильтры он умеет считать (`src/query/templates.py`).
Например, `status_summary` требует `status` и допускает только `audit_count`
и фильтр `year`; он не может ответить на вопрос «закрытые проверки по
каждому карману», поэтому не выбирается, а SQL собирается из дополненного
QueryPlan.

Слой `intent` — это не обход шаблона, а детерминированный доменный парсер.
Он нужен потому, что модель может вернуть корректный `reason` и пустой
`QueryPlan`; без него пришлось бы либо молча выполнить не тот запрос,
либо каждый раз падать в свободный SQL. Если модель станет надёжнее,
`intent` можно ослабить, но разделение intent/execution остаётся.

### Почему темы всё ещё проверяются лексиконом

`theme_in_text` — не попытка понять вопрос вместо LLM, а проверка явного
упоминания темы. Это подтверждено бенчмарком: после удаления темы из
`question_signals` кейс «проверки в кармане 2026 года по ипотеке» вернул
52 вместо 11 — LLM потеряла фильтр темы. Лексикон закрытый, падежи и
омонимы («картина» ≠ «карты») перечислены явно, поэтому regex здесь
надёжнее свободной модели. Удалять его можно только после появления
LLM-verifier, который проверяет покрытие плана.

`missing_question_filters` — тоже не NLU, а защитная проверка SQL:
шаблон/свободный SQL не должны молча потерять условие вопроса.

## Валидация

`QueryCompileError`, `KeyError` и неизвестные измерения/значения не
попадают в SQL: Analytics откатывается на fallback. В `metrics.plan_source`
пишется `query_ir`, чтобы это было видно в бенчмарке и trace.

## Тесты

```powershell
.venv\Scripts\python.exe -m pytest tests\test_query_compiler.py -q
.venv\Scripts\python.exe -m pytest tests\test_query_intent.py -q
.venv\Scripts\python.exe -m pytest tests\test_analytics_agent.py -q
.venv\Scripts\python.exe -m pytest tests\test_analytics_filters.py -q
```

## Связанные слои

- `src/graph/main_graph.py` — router выбирает `analytics_mode`
  (`sql` / `drilldown` / `multi_tool`) по смыслу вопроса; Analytics
  валидирует значение по enum.
- `src/dialogue_slots.py` — детерминированно переносит только год и
  AUD-код. Тема, тип находки, риск и статус — семантика: их восстанавливает
  LLM-резолвер в тексте вопроса, а QueryPlan видит результат.

## Что дальше

- Golden SQL для benchmark-кейсов.
- Перевести repair с текста SQL на структуру QueryPlan.
- Добавить list-метрики (не только count) для «покажи пункты».
- Использовать slots в QueryPlan напрямую, а не только через текст запроса.
- Хранить контракт шаблона (метрика, разрезы, период) в БД, а не в
  `src/query/templates.py`: сейчас это код, синхронный с `script_templates`.
