# Метрики

## Эффективность

| Метрика | Источник |
|---|---|
| `latency_total_sec` | время `graph.invoke` |
| `latency_p50/p95` | перцентили по тест-набору |
| `llm_calls` / `llm_attempts` / `llm_retries` / `llm_errors` | вызовы, попытки, 429-повторы и финальные ошибки LLM |
| `tool_calls` | счётчик инструментов |
| `input_tokens` / `output_tokens` / `cached_tokens` | токены LLM |
| `llm_latency_sec` / `llm_failed_latency_sec` / `tool_latency_sec` | время LLM, неудачных попыток и инструментов |
| `overhead_sec` | время графа вне LLM и tools |
| `sql_retries` | число исправлений SQL |
| `acl_rounds` | раунды расследования |
| `trace_step_count` | число шагов агента |
| `cost_usd` | токены × учебная цена |

## Качество

| Метрика | Проверка |
|---|---|
| `route_accuracy` | совпадение маршрута |
| `answer_success_rate` | качество ответа без процессных ограничений |
| `process_success_rate` | tools, шаги, лимиты вызовов/токенов/времени |
| `success_rate` | `answer_success` и `process_success` |
| `sql_validity_rate` | SQL проходит `sql_guard` |
| `numeric_accuracy` | ожидаемые числа найдены как самостоятельные в ответе |
| `evidence_coverage` | есть evidence для фактических ответов |
| `citation_coverage` | есть цитаты для retrieval |
| `steps_ok` | обязательные шаги `trace` присутствуют |

Планируемые, но **не реализованные** метрики (не выдавать за текущие):
`investigation_completeness` и `groundedness` (LLM-judge). Они описаны
в спецификации как будущее развитие, а не как факт текущего прогона.

## Запуск

```powershell
# проверка структуры набора без LLM
.venv\Scripts\python.exe scripts\evaluate.py --dry-run

# полный прогон (нужен ключ и построенный индекс)
.venv\Scripts\python.exe scripts\evaluate.py

# три прогона с mean/std (расходует лимит провайдера)
.venv\Scripts\python.exe scripts\evaluate.py --repeat 3
```

Результаты: `reports/metrics.csv`, `reports/metrics.md`.

Набор: `data/test_cases.jsonl` — 26 кейсов
(8 analytics, 6 retrieval, 6 report, 2 investigation, 2 out-of-domain,
1 unsafe, 1 memory).

## Многоуровневый бенчмарк

Отдельный набор `data/benchmark_cases.jsonl` делит проверки на четыре уровня:

| Уровень | Кейсов | Реплик | Что проверяет |
|---|---:|---:|---|
| `simple` | 13 | 13 | один факт, один фильтр, retrieval, отказы |
| `medium` | 18 | 18 | join, группировки, готовые шаблоны, метаданные |
| `complex` | 10 | 10 | multi-tool, отчёт, investigation, cross-table |
| `chain` | 8 | 24 | перенос года, темы, типа находки и кода проверки |

```powershell
.venv\Scripts\python.exe scripts\benchmark.py --dry-run
.venv\Scripts\python.exe scripts\benchmark.py --tier simple
.venv\Scripts\python.exe scripts\benchmark.py --tier medium
.venv\Scripts\python.exe scripts\benchmark.py --tier chain
```

Результаты: `reports/benchmark.csv`, `reports/benchmark.json`,
`reports/benchmark.md`.

Дополнительно к `evaluate.py` считаются:

| Метрика | Проверка |
|---|---|
| `answer_success_rate` | качество ответа |
| `process_success_rate` | качество процесса: tools, шаги, лимиты |
| `case_success_rate` | успешны все реплики кейса |
| `context_retention_rate` | сущность сохранилась в `resolved_query` или ответе |
| `context_rewrite_rate` | сущность явно попала в `resolved_query` |
| `context_answer_rate` | сущность видна в ответе |
| `chain_context_retention_rate` | retention только по цепочкам |
| `tool_accuracy` / `strategy_accuracy` | ожидаемые инструменты и стратегия Analytics |
| `citation_coverage` | цитаты retrieval |
| `llm_calls_total` / `tool_calls_total` | вызовы LLM и инструментов |
| `input_tokens_total` / `output_tokens_total` | генерация токенов |
| `latency_total_sec` / `llm_latency_total_sec` / `tool_latency_total_sec` | время выполнения и его разбивка |
| `embedding_calls_total` | вызовы эмбеддингов для retrieval |
| `tokens_per_success` / `cost_per_success_usd` | цена успешного ответа |

Телеметрия (`src/telemetry.py`) собирает по каждому ходу:

- вызовы LLM: модель, schema, input/output/cached tokens, latency, ошибки;
- вызовы инструментов: имя, статус, latency;
- эмбеддинги;
- версии промптов `id@vN:hash`;
- шаги `trace` и снимок состояния агента.

В отчётах сохраняются `state` и `fingerprint`; в CSV — краткие поля
`llm_calls`, `tool_calls`, токены, `llm_latency_sec`, `tool_latency_sec`,
`overhead_sec`, `trace_steps`, `acl_*`, `prompts`.

Подробное описание — `docs/benchmark.md`.

## Ограничение провайдера

На free-тарифе NeuralDeep действует сессионный лимит: **400 chat-запросов
за 3 часа** и 20 запросов/мин. Полный прогон 26 кейсов `evaluate.py` или
65 реплик бенчмарка (около 263 LLM-вызовов) расходует заметную часть лимита,
поэтому оценку лучше запускать после сброса окна (`/v1/limits`).
Скрипты поддерживают `--limit` и `--only`, чтобы прогнать подмножество.

## Исторический прогон `evaluate.py`

> Таблица — результат прошлого прогона, а не текущей ревизии. Отчёты
> `reports/*` не коммитятся; перед сдачей их нужно сгенерировать заново.

26 кейсов, seed 42, модель `qwen3.6-35b-a3b-noreason`:

| Метрика | Значение |
|---|---:|
| `route_accuracy` | 1.000 |
| `success_rate` | 0.962 |
| `sql_validity_rate` | 1.000 |
| `evidence_coverage` | 0.962 |
| `latency_mean_sec` | 28.324 |
| `latency_p50_sec` | 10.878 |
| `latency_p95_sec` | 72.124 |

Один кейс (`an_08`) упал из-за обрезки JSON плана SQL; после увеличения
лимита токенов он проходил отдельно. Повторный полный прогон ограничен
free-тарифом (400 запросов / 3 часа) и на текущей ревизии не выполнялся.

## Текущее состояние отчётов

- **Бенчмарк:** полный прогон 49 кейсов / 65 реплик выполнен 22.11.2026
  (модель `qwen3.6-35b-a3b-noreason`, seed 42, `run_id` и версии промптов —
  в `reports/benchmark.json`). Сводка опубликована в `docs/benchmark.md`.
  Часть метрик пересчитана `benchmark_rescore.py` после
  исправления matcher чисел; исходный JSON сохранён как
  `reports/benchmark_unresolved.json`.
- **`evaluate.py`:** последний полный прогон 26 кейсов относится к более
  ранней ревизии; на текущей ревизии не повторялся.

Отчёты `reports/*.csv`, `*.json` и сгенерированные `*.md` не коммитятся.
Проверка структуры без LLM:

- `scripts/evaluate.py --dry-run` — 26 кейсов `data/test_cases.jsonl`;
- `scripts/benchmark.py --dry-run` — 49 кейсов / 65 реплик.

## Воспроизводимость

- temperature 0;
- фиксированный seed данных 42;
- одинаковый набор кейсов;
- фиксированная дата среза `2026-11-21`.
