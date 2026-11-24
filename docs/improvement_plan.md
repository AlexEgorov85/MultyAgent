# План доработки: от симптомов к причинам

Дата: 22.11.2026. Текущий baseline: 51 кейс / 67 реплик,
`answer_success_rate` 0.631, `process_success_rate` 0.677,
`success_rate` 0.538.

## 1. Почему предыдущий план был тактическим

Предыдущие меры — валидация `template_key`, fallback на generated SQL,
few-shot под отдельные вопросы, правка matcher чисел — полезны, но это
**защитные сетки**. Они не устраняют причины:

- LLM свободно выбирает `template_key` из текстового описания;
- LLM сразу пишет SQL, минуя проверяемую промежуточную модель запроса;
- контекст диалога передаётся текстом, а не структурой слотов;
- маршрут выбирается LLM и набором regex без явной таксономии интентов;
- ошибка выполнения возвращается как текст ответа, без контракта статуса;
- benchmark ожидает один конкретный путь, хотя допустимых путей может быть
  несколько.

Из-за этого каждый новый вопрос требует нового костыля.

## 2. Симптомы и корневые причины

| Симптом из бенчмарка | Корневая причина | Правильное решение |
|---|---|---|
| Несуществующие `template_key`: `simple_count_filter`, `metadata_snapshot`, `script_mismatch_count` | LLM выбирает capability из свободного текста, без typed-контракта | Capability registry с `enum`/JSON Schema и deterministic matcher |
| `status_summary` без `year`, неподходящий шаблон | нет валидации capability и обязательных слотов до выбора | typed input schema + preconditions |
| `medium_deviations_severity` группирует по теме/году | прямой NL→SQL без промежуточной модели | Query IR: metric + dimensions + filters |
| `medium_acts_approved_auditor` = 0 | LLM сам выбирает join и колонку | semantic layer с готовыми relations/metrics |
| `simple_pocket_mortgage_2026` без фильтра темы/кармана | фильтры не выделены в структуру | slots + Query IR + compiler |
| `complex_deviations_critical_theme` — `ai.theme_code` | LLM придумывает alias/колонку | компилятор SQL из semantic layer + column validation |
| `chain_correction.3` потерял `item_type=проблема` | контекст диалога — текст, а не state | DialogueState со слотами |
| «Чем отклонение отличается от проблемы?» → smalltalk | нет таксономии интентов и правил для definitional-вопросов | Intent taxonomy + deterministic pre-router |
| Ошибка SQL/шаблона возвращается как ответ, evidence пустой | нет контракта ответа и failure-статуса | AnswerEnvelope: ok / no_data / refused / failed |
| Верный ответ, но `strategy_ok=false` | benchmark требует один путь, хотя valid paths несколько | allowed strategies/tools в кейсе |
| 97.5% времени в LLM, 4 вызова на реплику | каждый вопрос идёт через LLM plan/summarize | fast path, model routing, кэш каталога |

## 3. Целевая архитектура

### 3.1. Semantic layer

Добавить машинно-читаемый каталог домена:

```text
metrics: audit_count, act_count, item_count, script_count,
         run_count, deviation_count, overdue_count, repeat_count,
         no_script_count, run_script_mismatch_count
dimensions: year, theme, status, audit_type, risk_level,
            item_type, responsible_unit, language, severity,
            entity_type, metric_name, auditor_id
relations: audits → pockets, acts → audits, items → acts,
           scripts → items, runs → scripts, deviations → items
allowed_values: statuses, themes, risks, types
time: audit.dataset_metadata.as_of_date (fallback — CURRENT_DATE)
```

Каталог — единый источник истины для агента, SQL-компилятора и benchmark.
`SCHEMA_TEXT` становится генерируемым представлением каталога, а не
рукописным текстом.

### 3.2. Query IR вместо свободного SQL

LLM возвращает не SQL, а `QueryPlan`:

```python
class QueryPlan(BaseModel):
    metric: str
    dimensions: list[str]
    filters: list[Filter]
    time_range: TimeRange | None
    order_by: list[Order]
    limit: int
```

`QueryCompiler` детерминированно собирает SQL:

- выбирает разрешённые join из каталога;
- проверяет колонки и значения;
- добавляет обязательные фильтры;
- применяет LIMIT и read-only guard;
- возвращает SQL + использованные slots.

Свободная генерация SQL остаётся только fallback для неподдержанных
метрик и проходит тот же guard.

### 3.3. Capability registry

Вместо текстового списка шаблонов — typed capabilities:

```python
class Capability(BaseModel):
    id: Literal["status_summary", "top_findings", ...]
    description: str
    input_schema: type[BaseModel]
    required_slots: list[str]
    handler: str
```

Планировщик выбирает `capability.id` как enum. Несуществующий id
невозможен на уровне схемы. Deterministic matcher сначала пытается
сопоставить вопрос с capability по ключевым словам и слотам; LLM — только
для неоднозначных случаев.

### 3.4. DialogueState

Явное состояние диалога:

```python
class DialogueSlots(BaseModel):
    year: int | None
    theme: str | None
    item_type: str | None
    risk_level: str | None
    status: str | None
    audit_code: str | None
```

Resolver обновляет слоты, а не только переписывает текст. Агенты получают
и `resolved_query`, и `slots`. Benchmark проверяет `slot_accuracy` и
`context_retention`.

### 3.5. Intent taxonomy

Явные интенты:

`analytics_count`, `analytics_list`, `analytics_compare`,
`retrieval`, `report`, `investigation`, `smalltalk`, `unsafe`,
`out_of_domain`.

Для явных сигналов — deterministic rules:
`AUD-...` + «пункты» → analytics/drilldown;
`AUD-...` + «акт/сформируй» → report;
«чем X отличается», «что такое», «как оформлять» + домен → retrieval;
приветствие/спасибо → smalltalk.
LLM — только fallback с confidence.

### 3.6. AnswerEnvelope

Любой агент возвращает контракт:

```python
class AnswerEnvelope(BaseModel):
    status: Literal["ok", "no_data", "refused", "failed"]
    text: str
    evidence: list[Evidence]
    method: str
    assumptions: list[str]
    warnings: list[str]
```

Если SQL/шаблон упал, статус `failed`, а не текст ошибки в `answer`.
Если данных нет — `no_data`. Evidence обязателен для `ok` фактического
ответа. Это делает `evidence_coverage` осмысленным.

### 3.7. Benchmark contract

Кейс должен описывать не один путь, а допустимые:

```json
{
  "allowed_strategies": ["script", "generated"],
  "allowed_tools": ["run_script_template", "run_readonly_sql"],
  "required_evidence": ["sql_result"],
  "expected_semantic_result": {"metric": "item_count", "filters": {...}}
}
```

Ожидаемые числа лучше вычислять из semantic layer/golden queries, а не
хардкодить. Добавить holdout-кейсы, которые не используются при правках.

## 4. Что не делать

- Не добавлять regex/few-shot под каждый упавший кейс.
- Не считать валидацию `template_key` основной мерой — это safety net.
- Не менять `expected_*` после просмотра ответов агента.
- Не требовать один конкретный tool, если допустимы несколько.
- Не оптимизировать токены до исправления семантики.
- Не смешивать изменения semantic layer и промптов в одном эксперименте.

## 5. Этапы внедрения

### Этап 0. Зафиксировать baseline и контракт измерения

- [x] Исправлен matcher чисел.
- [x] Добавлен `benchmark_rescore.py`.
- [x] SQL добавлен в `state.content`.
- [x] Сохранён `reports/benchmark_baseline.json`.
- [ ] Разделить `answer_success` и `process_success` в отчётах.
- [ ] Добавить новые метрики: `plan_validity_rate`, `slot_accuracy`,
  `capability_resolution_rate`, `answer_contract_rate`,
  `allowed_strategy_rate`.

### Этап 1. Semantic layer

Статус: базовый каталог готов.

Файлы:

- `src/semantic/catalog.py`
- `src/semantic/__init__.py`
- `tests/test_query_compiler.py`

Сделано:

- [x] Описаны метрики, измерения, связи и допустимые значения.
- [x] Добавлены `audit_count`, `act_count`, `item_count`,
  `critical_item_count`, `overdue_item_count`, `repeat_item_count`,
  `no_script_item_count`, `script_count`, `run_count`,
  `run_script_mismatch_count`, `deviation_count`, `auditor_count`.
- [x] Добавлена валидация значений.
- [x] `missing_question_filters` работает по сигналам каталога
  (карман, последний год, закрытая проверка, тема, AUD-код), а не по
  отдельным словам.
- [ ] Сгенерировать `SCHEMA_TEXT` из каталога для fallback-пути.

### Этап 2. Query IR + compiler

Статус: базовый Query IR подключён к Analytics.

Файлы:

- `src/query/plan.py`
- `src/query/compiler.py`
- `src/prompts/analytics_plan_query.md`
- `tests/test_query_compiler.py`

Сделано:

- [x] Pydantic-модель `QueryPlan`.
- [x] LLM-план возвращает IR, не SQL.
- [x] Детерминированный compiler для top-метрик.
- [x] Fallback на free SQL только для неподдержанных запросов.
- [x] Analytics использует Query IR первым шагом.
- [x] `metrics.plan_source = query_ir`.
- [ ] Golden SQL tests на benchmark-кейсы.
- [ ] Перевести `missing_question_filters` и repair на IR.

### Этап 3. Capability registry

Статус: **пересмотрено повторно**. Шаблон больше не выбирает LLM:
это execution strategy, а не часть intent. `template_key` удалён из
`QueryPlan`; код сопоставляет проверенный план с контрактами шаблонов
(`src/query/templates.py`). Это устраняет подмену вопроса шаблоном.

Сделано:

- [x] Typed-контракты для шести шаблонов (метрики, разрезы, фильтры,
  параметры).
- [x] LLM возвращает только `QueryPlan(metric, dimensions, filters)`.
- [x] Для явных template-вопросов работает детерминированный fast path
  без вызова LLM; шаблон выбирается по контракту.
- [x] Код выбирает шаблон по контракту; при неполном покрытии — SQL.
- [x] Валидация обязательных параметров шаблона перед запуском.
- [x] Шаблон проверяется на покрытие разрезов, фильтров и периода вопроса.
- [ ] Хранить контракты шаблонов в БД рядом с `script_templates`, а не в коде.

Критерий: LLM не может вернуть `template_key`; template-кейсы выбирают
шаблон детерминированно по контракту плана.

### Этап 4. DialogueState + resolver

Статус: год и AUD-код переносятся детерминированно; семантические слоты
восстанавливает LLM-резолвер в тексте вопроса.

Файлы:

- `src/dialogue_slots.py`
- `src/graph/main_graph.py`
- `tests/test_dialogue_slots.py`
- `tests/test_main_graph.py`

Сделано:

- [x] Слоты year/audit_code извлекаются детерминированно.
- [x] Семантические слоты (тема, тип, риск, статус) не угадываются по словам.
- [x] `augment_query` добавляет только год и код проверки.
- [x] Слоты передаются в ACL-content Analytics.
- [x] Тест `chain_correction`: резолвер переносит «проблемы» при смене года.
- [ ] Использовать slots в QueryPlan и report напрямую.
- [ ] Восстанавливать slots из client_history после потери треда.

Критерий: `slot_accuracy` ≥ 0.90 на chain.

### Этап 5. Intent taxonomy + router

Файлы:

- `src/routing/intents.py`
- `src/routing/rules.py`
- `src/prompts/router.md`
- `tests/test_routing.py`

Задачи:

1. Enum интентов и обязательных слотов.
2. Deterministic pre-router для явных сигналов.
3. Definitional-вопросы → retrieval.
4. LLM fallback с confidence.

Критерий: `route_accuracy` ≥ 0.99, definitional-кейс проходит.

### Этап 6. Answer contract + evidence

Файлы:

- `src/contracts/answer.py`
- `src/graph/*_graph.py`
- `src/guardrails.py`

Задачи:

1. `AnswerEnvelope` для всех агентов.
2. `failed/no_data` не маскируются под `ok`.
3. Evidence обязателен для фактического `ok`.
4. Guardrail проверяет контракт.

Критерий: `evidence_coverage` ≥ 0.90, `answer_contract_rate` 1.0.

### Этап 7. Fast path и эффективность

- deterministic fast path для простых count/list;
- дешёвая модель для router/format/summary;
- кэш каталога и capabilities;
- меньше контекста и tool calls;
- замер `tokens_per_success`, p95.

Критерий: `tokens_per_success` ≤ 10 000, p95 ≤ 60 с без падения success.

### Этап 8. Benchmark contract

- allowed_strategies/allowed_tools;
- expected semantic result;
- holdout-кейсы;
- gate в CI;
- improvement_log.

## 6. Новые метрики

| Метрика | Что показывает |
|---|---|
| `plan_validity_rate` | QueryPlan проходит каталог и валидатор |
| `slot_accuracy` | слоты диалога извлечены/сохранены |
| `capability_resolution_rate` | capability выбрана детерминированно |
| `sql_semantic_validity` | SQL соответствует IR и каталогу |
| `answer_contract_rate` | ответ имеет корректный status/evidence |
| `allowed_strategy_rate` | выбран допустимый путь, а не один ожидаемый |

## 7. Целевые метрики

| Метрика | Сейчас | Цель |
|---|---:|---:|
| `answer_success_rate` | 0.631 | ≥ 0.80 |
| `success_rate` | 0.538 | ≥ 0.70 |
| `medium_success_rate` | 0.389 | ≥ 0.60 |
| `tool_accuracy` | 0.500 | ≥ 0.85 |
| `strategy_accuracy` | 0.500 | ≥ 0.85 |
| `evidence_coverage` | 0.774 | ≥ 0.90 |
| `slot_accuracy` | — | ≥ 0.90 |
| `plan_validity_rate` | — | ≥ 0.95 |
| `tokens_per_success` | 11 988 | ≤ 10 000 |
| `latency_p95_sec` | 61.979 | ≤ 60 |

## 8. Порядок и контроль

1. Этапы 1–2 — semantic layer и Query IR.
2. Этапы 3–4 — capabilities и dialogue state.
3. Этап 5 — intent taxonomy.
4. Этап 6 — answer contract.
5. Этап 7 — эффективность.
6. Этап 8 — benchmark contract и CI.

После каждого этапа:

```powershell
.venv\Scripts\python.exe scripts\benchmark.py --only <target_cases>
.venv\Scripts\python.exe scripts\benchmark.py
.venv\Scripts\python.exe scripts\benchmark_diff.py ^
    reports\benchmark_baseline.json reports\benchmark.json --gate
```

## 9. Критерии готовности

- Semantic layer используется и агентом, и benchmark.
- Для top-10 метрик SQL строится из QueryPlan, а не свободной генерацией.
- Нет несуществующих capability/template.
- Dialogue slots сохраняются между репликами.
- Ошибки возвращаются как `failed/no_data`, а не как ответ.
- Benchmark проверяет допустимые пути, а не один.
- `answer_success_rate` ≥ 0.80, `success_rate` ≥ 0.70.
- `pytest -q` и `openspec validate --specs --strict` зелёные.
- Есть holdout и improvement log.

## 10. Вне рамок текущей сдачи

Эти пункты осознанно не входят в сдачу и зафиксированы как развитие:

- **LLM-judge** с рубрикой 1–10 и `groundedness`/`hallucination_rate`:
  требует отдельного бюджета и стабильной модели-judge.
- **Сравнительные эксперименты** «без Inspector» и «шаблон против
  генерации»: нужен воспроизводимый прогон двух конфигураций.
- **Потоковая выдача UI** (`runs/stream` вместо `runs/wait`): отдельная
  задача фронтенда, не блокирует текущую сдачу.
- **`sql_execution_success_rate`, `citation_precision`,
  `investigation_completeness`**: метрики запланированы, но пока не
  считаются; не выдавать их за реализованные.

Соответствующие SHALL-требования из `observability-evaluation`
и `chat-ui` убраны или переформулированы, чтобы спецификация не обещала
несуществующего поведения.
