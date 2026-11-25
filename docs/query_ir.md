# Query IR: semantic layer и детерминированный SQL

Analytics-агент больше не просит LLM сразу писать SQL. Первый шаг —
`QueryPlan`: что считать, по каким разрезам и с какими фильтрами. SQL
собирает `src/query/compiler.py` из каталога `src/semantic/catalog.py`.

## Поток

```text
вопрос
  → LLM plan_query (structured output)
  → QueryPlan(metric, dimensions, filters, template_key)
  → review_query_plan: LLM находит недостающие условия
  → apply_plan_gaps: код валидирует и применяет их по каталогу
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
| `deviation_gap_max` | максимальный разрыв отклонения с порогом |

У метрики может быть контракт на обязательные измерения: `deviation_gap_max`
требует `title` и `audit_code`, иначе нельзя назвать, какое именно
отклонение самое крупное. План дополняется этими измерениями и `limit=1`
детерминированно, по описанию метрики, а не по формулировке вопроса.

## Измерения и фильтры

Измерения — только из каталога метрики. Основные:

`year`, `month`, `theme`, `pocket`, `status`, `audit_type`, `risk_level`,
`item_type`, `title`, `responsible_unit`, `is_repeat`, `audit_code`,
`act_status`, `lead_auditor_id`, `approved_by`, `language`, `run_status`,
`severity`, `entity_type`, `metric_name`, `specialization`.

`month` для проверок — месяц `COALESCE(end_date, start_date)`.

`pocket` — карман аудита (год + тема). Это отдельное измерение, а не
`status`: «по каждому карману» нельзя выразить разрезом по статусам.

Для `specialization` используется `op=contains`:

```json
{"field": "specialization", "value": "ипотека", "op": "contains"}
```

Период `year="last"` компилируется в максимальный год данных, а
`year="last_2"` — в последние два года:

```sql
p.pocket_year >= (SELECT max(p_last.pocket_year) - 1
                  FROM audit.audit_pockets p_last)
```

«Закрытая проверка» — `status="завершена"`, «закрытый пункт» —
`status="закрыт"`. Эти значения выбираются по метрике, а не по слову
«закрыт» вне контекста.

## Проверка плана второй моделью

LLM может вернуть верный смысл в `reason`, но пустые
`dimensions`/`filters`. Поэтому после `plan_query` Analytics делает
второй структурированный вызов — `review_query_plan`:

1. LLM получает вопрос, каталог и текущий `QueryPlan`.
2. Возвращает `PlanGaps`: `metric` (если текущая метрика неверна),
   `missing_dimensions`, `missing_filters`, `period`, `year`, `issues`,
   `clarification`.
3. Если `clarification` непустой, вопрос допускает две равноправные
   трактовки: SQL **не выполняется**, Analytics возвращает уточняющий
   вопрос, а не догадку.
4. Иначе `apply_plan_gaps` (`src/query/intent.py`) применяет gaps к плану
   и валидирует поля/значения по semantic layer. Неизвестные поля и
   значения отбрасываются; несколько значений одного поля превращаются
   в dimension, а не в AND-фильтры. При смене метрики несовместимые с ней
   фильтры отбрасываются.

`clarification` заполняется консервативно: только если пользователь сам
назвал две равноправные трактовки («проверки или пункты») и они дают
разные числа. Про значения статусов, имена колонок, «список или
количество» и определение периода агент не спрашивает: это решает
каталог или система. «Закрыто/завершено» без объекта — это проверки
(`audit_count`), доменный default.

Regex-парсера вопроса (`question_signals`, `theme_in_text`) больше нет.
Проверка плана — решение LLM, а код отвечает только за типы, enum-значения
и нормализацию.

Шаблон не является вторым источником истины. LLM выбирает `template_key`,
но контракт шаблона (`src/query/templates.py`) проверяет метрику, разрезы
и фильтры. Например, `status_summary` требует `status` и допускает только
`audit_count` и фильтр `year`; он не может ответить на вопрос «закрытые
проверки по каждому карману», поэтому отклоняется, а SQL собирается из
проверенного `QueryPlan`.

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
