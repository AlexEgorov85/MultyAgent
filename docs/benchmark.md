# Бенчмарк: простые, средние, сложные и цепочечные вопросы

Бенчмарк сделан по логике занятия 7: фиксированный набор задач с заранее
известными ответами, прогон на одинаковых данных, затем `SR/ER`, точность
маршрута, tool-call accuracy, citation accuracy и latency. В отличие от
`data/test_cases.jsonl`, здесь четыре уровня сложности, проверка покрытия
всех таблиц и отдельные диалоговые цепочки.

## Состав

| Уровень | Кейсов | Реплик | Что проверяет |
|---|---:|---:|---|
| `simple` | 13 | 13 | один факт, один фильтр, один инструмент |
| `medium` | 18 | 18 | join, группировки, готовые шаблоны, сравнения |
| `complex` | 10 | 10 | multi-tool, отчёт, investigation, cross-table |
| `chain` | 8 | 24 | перенос года, темы, кода и типа находки между репликами |
| **Итого** | **49** | **65** | все основные таблицы и сценарии |

Набор: `data/benchmark_cases.jsonl`.

## Файлы

| Файл | Назначение |
|---|---|
| `data/benchmark_cases.jsonl` | 51 кейс и 67 реплик |
| `scripts/benchmark.py` | прогон, прогресс и отчёты |
| `src/benchmark.py` | валидация, скоринг и покрытие таблиц |
| `tests/test_benchmark.py` | проверки структуры, формул и покрытия |
| `reports/benchmark.csv` | строка на каждую реплику |
| `reports/benchmark.json` | подробный машинный отчёт |
| `reports/benchmark.md` | человекочитаемый отчёт |

## Покрытие таблиц

Каждый кейс содержит поле `tables`, а отчёт строит сводку покрытия.

| Таблица / слой | Что проверяется |
|---|---|
| `auditors` | специализации, нагрузка ведущего, утверждение актов |
| `audit_pockets` | размер кармана, год и тема |
| `audits` | статусы, типы, отмены, проверки в работе |
| `acts` | черновики, согласование, даты 2027 года |
| `act_items` | типы, риски, статусы, просрочки, повторные находки |
| `scripts` | языки, версии, нулевые результаты, отсутствие скриптов |
| `script_runs` | успешные, частичные и ошибочные запуски |
| `deviations` | severity, entity_type, metric_name |
| `script_templates` | все шесть готовых шаблонов |
| `auditor_memory` | сохранение профиля аудитора |
| `knowledge_chunks` | retrieval по методичкам и актам |
| `dataset_metadata` | дата среза и seed |

## Уровни

### Simple — один факт

- размер кармана 2026 года по ипотеке;
- отменённые проверки 2026 года;
- акты-черновики;
- всего пунктов и критических пунктов 2026 года;
- скрипты на Python;
- запуски с ошибкой;
- отклонения по договорам;
- сроки устранения для критического риска;
- отличие отклонения от проблемы;
- отказ вне домена и отказ на изменение данных;
- сохранение профиля аудитора (`simple_memory_profile`, AUD-012);
- сброс профиля аудитора (`simple_memory_forget`);
- смешанная реплика не перехватывается памятью (`simple_memory_mixed_question`).

### Medium — join, группировка, шаблон

- статусы проверок 2026 года: завершено / в работе / запланировано / отменено;
- статусы актов 2025 года;
- акты с датой 2027 года;
- отклонения и проблемы 2026 года;
- просрочки 2025 года по темам;
- пункты без скриптов и повторные находки по темам;
- языки скриптов;
- статусы запусков скриптов;
- отклонения по уровням критичности;
- аудиторы с ипотечной специализацией;
- нагрузка `AUD-002` и акты `AUD-005`;
- готовые шаблоны: `status_summary`, `top_findings`,
  `items_without_scripts`, `theme_dynamics`;
- метаданные набора: дата среза и seed.

### Complex — несколько источников и сценариев

- два multi-tool кейса: пункты проверки + похожие формулировки;
- отчёт по завершённой проверке, черновику и акту на согласовании;
- investigation по картам и по просрочкам в платежах;
- тема с максимумом критических отклонений в 2026 году;
- расхождение `script_runs.rows_found` и `scripts.rows_found`;
- пункты без скриптов в актах на согласовании.

### Chain — контекст диалога

Все реплики цепочки идут в одной нити `thread_id`.

| Цепочка | Реплики | Что проверяется |
|---|---|---|
| `chain_year_theme` | 3 | год сохраняется, затем заменяется тема |
| `chain_correction` | 3 | «нет, я имел в виду проблемы» меняет тип находки |
| `chain_overdue_risk` | 3 | просрочка + тема + критический риск |
| `chain_drilldown_context` | 3 | код акта переносится в подсчёт закрытых и «в работе» |
| `chain_agent_switch` | 3 | drill-down → проект акта → акцент на критическом пункте |
| `chain_report_context` | 3 | отчёт → «сделай короче» → ссылка на пункт 6.1 |
| `chain_ui_recovery` | 3 | после смены нити контекст восстанавливается из `client_history` |
| `chain_retrieval_followup` | 3 | retrieval → рекомендации → источники |

Числа в цепочках подобраны разными (`5 → 8 → 7`, `42 → 25 → 24`,
`20 → 4 → 2`, `2 → 6 → 8`), чтобы правильный ответ нельзя было получить
случайно, не перенеся год, тему, тип находки или фильтр риска.

## Формат кейса

```json
{
  "id": "chain_overdue_risk",
  "tier": "chain",
  "title": "Просрочки с фильтром по риску",
  "auditor_id": "AUD-004",
  "tables": ["act_items", "acts", "audits", "audit_pockets"],
  "turns": [
    {
      "query": "Сколько просроченных пунктов по картам в 2026 году?",
      "expected_route": "analytics",
      "expected_numbers": [20],
      "min_evidence": 1
    },
    {
      "query": "А сколько из них критического риска?",
      "expected_route": "analytics",
      "expected_context": ["2026", "карт", "критическ"],
      "expected_numbers": [4],
      "min_evidence": 1,
      "must_include": ["критическ"]
    }
  ]
}
```

Поля реплики:

| Поле | Смысл |
|---|---|
| `expected_route` | ожидаемый маршрут основного графа |
| `expected_strategy` | `generated`, `script`, `drilldown`, `multi_tool` |
| `expected_tools` | инструменты, которые должны быть использованы |
| `expected_evidence` | обязательные типы evidence (`sql_result`, `item`, `audit`, `citation`, `методика`) |
| `min_evidence` | минимум записей evidence |
| `min_citations` | минимум цитат retrieval |
| `min_acl_rounds` | минимум раундов investigation |
| `expected_numbers` | самостоятельные числа в ответе |
| `must_include` / `must_not_include` | обязательные и запрещённые фрагменты |
| `expected_context` | сущности, которые должны сохраниться из предыдущих реплик |
| `reset_thread` | начать новую нить и передать историю через `client_history` |

Поля процесса:

| Поле | Смысл |
|---|---|
| `expected_steps` | обязательные шаги `trace`: `route`, `sql`, `sql_result`, `retrieval`, `citations`, `report`, `inspector`, `acl`, `guard_request`, `guard_answer`, `memory` |
| `forbidden_tools` | инструменты, которые нельзя вызывать |
| `max_llm_calls` | потолок успешных вызовов LLM |
| `max_llm_errors` | потолок финальных ошибок LLM (по умолчанию 0) |
| `max_tool_calls` | потолок вызовов инструментов |
| `max_total_tokens` | потолок input + output токенов |
| `max_cost_usd` | потолок учебной стоимости |
| `max_latency_sec` | потолок времени реплики |
| `max_sql_retries` | потолок исправлений SQL |
| `max_acl_rounds` | потолок раундов investigation |
| `max_steps` | потолок числа шагов `trace` |

`expected_numbers` ищутся как самостоятельные числа: `5` не совпадёт с
`2025` или `5.1`.

## Метрики

Бенчмарк разделяет успех ответа и успех процесса:

- `answer_success` — маршрут, контекст, числа, evidence, citations, SQL;
- `process_success` — tools, strategy, шаги, лимиты вызовов, токенов,
  стоимости и времени;
- `success` = `answer_success` и `process_success`.

Качество ответа:

- `route_accuracy`;
- `answer_success_rate`;
- `success_rate` (SR) и `error_rate` (ER = 1 − SR);
- `case_success_rate` — успешны все реплики кейса;
- `numeric_accuracy`;
- `evidence_coverage`;
- `citation_coverage`.

Качество процесса:

- `process_success_rate`;
- `tool_accuracy` — ожидаемые инструменты среди реально вызванных;
- `strategy_accuracy` — выбранная стратегия Analytics;
- `steps_ok` — обязательные шаги `trace` присутствуют;
- `forbidden_tools_ok` — запрещённые инструменты не вызывались;
- `llm_calls_ok`, `tool_calls_ok`, `tokens_ok`, `cost_ok`, `latency_ok`;
- `sql_retries_ok`, `acl_rounds_ok`, `max_steps_ok`.

Вызовы и токены:

- `llm_calls_total`, `llm_attempts_total`, `llm_retries_total`,
  `llm_errors_total`;
- `tool_calls_total`;
- `embedding_calls_total`;
- `input_tokens_total`, `output_tokens_total`, `total_tokens_total`;
- `cost_usd_total`;
- `tokens_per_success`, `cost_per_success_usd`,
  `llm_calls_per_success`, `tool_calls_per_success`.

Время выполнения:

- `latency_total_sec` — суммарное время всех реплик;
- `latency_mean_sec`, `latency_p50_sec`, `latency_p95_sec`;
- `llm_latency_total_sec` — время внутри вызовов LLM (включая неудачные попытки);
- `llm_failed_latency_total_sec` — время только неудачных попыток LLM;
- `tool_latency_total_sec` — время инструментов, SQL и retrieval;
- `llm_time_share_pct`, `tool_time_share_pct`;
- `avg_llm_latency_sec`, `avg_tool_latency_sec`;
- `overhead_sec` на каждой реплике — время графа, не занятое LLM и tools.

Шаги и состояние:

- `trace_step_count`, `trace_steps`, `avg_steps_per_turn`;
- `acl_performative`, `acl_sender`, `acl_receiver`;
- `state` в `benchmark.json`: маршрут, `resolved_query`, guardrails,
  ACL-конверт, evidence, шаги, промпты, метрики и `fingerprint`;
- `state_fingerprint` в CSV — короткий отпечаток состояния.

Версии промптов:

- для каждой реплики в `prompts` фиксируются `id@vN:hash` реально
  загруженных промптов;
- в `benchmark.json` и разделе «Среда» отчёта сохраняется полный реестр
  `prompt_versions`;
- это позволяет сравнить прогоны при изменении промпта.

Контекст:

- `context_retention_rate` — сущность сохранилась в `resolved_query`
  **или** в ответе;
- `context_rewrite_rate` — сущность явно попала в `resolved_query`;
- `context_answer_rate` — сущность видна в ответе;
- `chain_context_retention_rate` — то же только по цепочкам.

`context_retention_rate` терпима к двум рабочим путям: rewrite-модель
переформулировала вопрос **или** подагент восстановил сущность из
`conversation_context`. `context_rewrite_rate` показывает качество именно
переформулировки.

## Как фиксируется состояние агента

На каждый ход сохраняется компактный снимок:

- маршрут, причина и уверенность;
- `resolved_query` и причина переформулировки;
- профиль аудитора и признак сохранения памяти;
- guardrail запроса и ответа;
- ACL-конверт: performative, sender, receiver, conversation_id;
- evidence: типы и ID источников;
- шаги `trace` с агентом, статусом и длительностью;
- версии промптов, метрики LLM/tools;
- длина и SHA-256 ответа;
- `fingerprint` — хэш маршрута, `resolved_query`, evidence, шагов и промптов.

Полный снимок лежит в `reports/benchmark.json` (поле `state`), краткие
поля — в `reports/benchmark.csv`. Тяжёлые `final_answer`, строки SQL и
полные тексты актов в снимок не дублируются.

## Запуск

```powershell
# структура, уровни и покрытие таблиц без LLM
.venv\Scripts\python.exe scripts\benchmark.py --dry-run

# один уровень
.venv\Scripts\python.exe scripts\benchmark.py --tier simple
.venv\Scripts\python.exe scripts\benchmark.py --tier medium
.venv\Scripts\python.exe scripts\benchmark.py --tier complex
.venv\Scripts\python.exe scripts\benchmark.py --tier chain

# один кейс или подмножество
.venv\Scripts\python.exe scripts\benchmark.py --only chain_overdue_risk
.venv\Scripts\python.exe scripts\benchmark.py --limit 5

# пересчитать отчёты после исправления самого бенчмарка, без LLM
.venv\Scripts\python.exe scripts\benchmark_rescore.py --backup
```

Полный прогон требует `OPENAI_API_KEY`, построенный RAG-индекс и свободный
лимит провайдера. На free-тарифе NeuralDeep — 400 chat-запросов за 3 часа.
67 реплик — это не 67 запросов: с учётом router, SQL-плана, саммари,
Inspector и investigation полный прогон занял 263 chat-запроса,
поэтому запускайте его после сброса лимита или используйте `--tier`/`--limit`.
Количество фактических вызовов LLM видно в `llm_calls_total` и
`llm_attempts_total`.

Перед первым живым прогоном примените миграции, включая
`db/migrations/006_chat_history.sql`:

```powershell
.venv\Scripts\python.exe scripts\init_db.py
```

Без таблиц `audit.chat_threads` и `audit.chat_messages` ответы работают, но
история диалога в PostgreSQL не сохраняется и в лог пишутся предупреждения.

## Как читать отчёт

В `reports/benchmark.md`:

1. **Среда** — модель, embedding-модель, seed, дата среза, версии промптов.
2. **Итог** — общие метрики ответа и процесса.
3. **По уровням** — сравнение `simple`, `medium`, `complex`, `chain`
   по answer/process/success.
4. **Процесс и эффективность** — вызовы, токены, стоимость, время LLM/tools.
5. **Версии промптов** — какие промпты и версии реально использовались.
6. **Процесс по кейсам** — LLM, tools, токены, время и process success.
7. **Покрытие таблиц** — сколько кейсов приходится на каждую таблицу.
8. **Кейсы** — успех по каждому кейсу.
9. **Цепочки** — `resolved_query` и отметки «В запросе» / «В ответе».
10. **Снимки состояния** — где смотреть `state` и `fingerprint`.
11. **Ошибки** — что именно не прошло.

Типичные выводы:

- высокий `success_rate` на `simple`, но низкий на `chain` → страдает
  перенос контекста, а не базовые инструменты;
- низкий `context_rewrite_rate` при высоком `context_retention_rate` →
  rewrite-модель не переформулирует, но подагенты спасают контекст;
- ошибки в `chain_ui_recovery` → `client_history` не доходит до
  `build_dialogue_context` или теряется при смене нити;
- провал `medium_template_*` при успешных обычных SQL-кейсах → модель
  игнорирует готовые шаблоны.

## Исторический прогон 22.11.2026 (baseline до Query IR)

Полный прогон 22.11.2026, `qwen3.6-35b-a3b-noreason`, seed 42,
`run_id` `1795295013-13fd4f`.
Набор на момент прогона — 49 кейсов / 65 реплик. Сейчас в наборе 51 кейс / 67 реплик (добавлены сброс профиля и регрессия на смешанную реплику), поэтому цифры ниже — исторический baseline, а не текущая ревизия.
Это baseline **до** внедрения Query IR; после архитектурных изменений нужен
новый прогон.

| Метрика | Значение |
|---|---:|
| `answer_success_rate` | 0.631 |
| `process_success_rate` | 0.677 |
| `success_rate` | 0.538 |
| `case_success_rate` | 0.449 |
| `route_accuracy` | 0.985 |
| `numeric_accuracy` | 0.651 |
| `context_retention_rate` | 0.938 |
| `context_rewrite_rate` | 0.812 |
| `tool_accuracy` | 0.500 |
| `strategy_accuracy` | 0.500 |
| `evidence_coverage` | 0.774 |
| `citation_coverage` | 0.800 |
| `latency_mean_sec` | 15.676 |
| `latency_p95_sec` | 61.979 |
| `llm_calls_total` | 263 |
| `total_tokens_total` | 419568 |
| `cost_usd_total` | 0.275 |
| `tokens_per_success` | 11988 |
| `sql_retries_total` | 8 |
| `llm_errors_total` | 0 |

Первичный JSON до исправления matcher чисел сохранён как
`reports/benchmark_unresolved.json`; исправленный — `reports/benchmark.json`.
Разбор провалов — `reports/benchmark_backlog.md`.

## Воспроизводимость

- seed данных 42;
- фиксированная дата среза `2026-11-21`;
- temperature 0;
- ожидаемые числа рассчитаны по baseline seed 42;
- для кейсов используется `AUD-004` без персональных предпочтений в
  `auditor_memory`; профиль сохраняется только в отдельных кейсах
  `simple_memory_profile` (AUD-012) и `simple_memory_forget`;
- каждый прогон получает уникальный `run_id` в `thread_id`, чтобы история
  диалога в PostgreSQL не протекала из предыдущего запуска.

Если данные перегенерированы с другим seed, числа в `expected_numbers`
нужно пересчитать.

## Как перепроверить прогон

Файлы `reports/benchmark.csv`, `reports/benchmark.json` и
`reports/benchmark.md` не коммитятся, поэтому в чистом клоне их нет.
Чтобы получить свежие цифры:

```powershell
.venv\Scripts\python.exe scripts\benchmark.py
.venv\Scripts\python.exe scripts\benchmark_triage.py
```

Если изменился только скоринг (matcher чисел, разметка проверок), повторный
прогон LLM не нужен:

```powershell
.venv\Scripts\python.exe scripts\benchmark_rescore.py --backup
```

Сравнивать прогоны нужно через `scripts/benchmark_diff.py` с `--gate`.
Числа выше не следует выдавать за результат текущей ревизии, пока не
выполнен новый прогон и не сохранён его `run_id`.
