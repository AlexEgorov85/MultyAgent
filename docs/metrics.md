# Метрики

## Эффективность

| Метрика | Источник |
|---|---|
| `latency_total_sec` | время `graph.invoke` |
| `latency_p50/p95` | перцентили по тест-набору |
| `llm_calls` | счётчик в ответе/логах |
| `tool_calls` | счётчик инструментов |
| `sql_retries` | число исправлений SQL |
| `acl_rounds` | раунды расследования |
| `cost_usd` | токены × учебная цена |

## Качество

| Метрика | Проверка |
|---|---|
| `route_accuracy` | совпадение маршрута |
| `success_rate` | маршрут + обязательные строки + evidence |
| `sql_validity_rate` | SQL проходит `sql_guard` |
| `evidence_coverage` | есть evidence для фактических ответов |
| `investigation_completeness` | есть и SQL-, и текстовые доказательства |
| `groundedness` | LLM-judge (внешняя оценка) |

## Запуск

```powershell
# проверка структуры набора без LLM
.venv\Scripts\python.exe scripts\evaluate.py --dry-run

# полный прогон (нужен ключ и построенный индекс)
.venv\Scripts\python.exe scripts\evaluate.py
```

Результаты: `reports/metrics.csv`, `reports/metrics.md`.

Набор: `data/test_cases.jsonl` — 26 кейсов
(8 analytics, 6 retrieval, 6 report, 2 investigation, 2 out-of-domain,
1 unsafe, 1 memory).

## Многоуровневый бенчмарк

Отдельный набор `data/benchmark_cases.jsonl` делит проверки на три уровня:

| Уровень | Кейсов | Реплик | Что проверяет |
|---|---:|---:|---|
| `simple` | 8 | 8 | один факт, шаблон, drill-down, retrieval, отказы |
| `complex` | 5 | 5 | multi-tool, отчёт, investigation, динамика |
| `chain` | 5 | 15 | перенос года, темы и кода проверки между репликами |

```powershell
.venv\Scripts\python.exe scripts\benchmark.py --dry-run
.venv\Scripts\python.exe scripts\benchmark.py --tier simple
.venv\Scripts\python.exe scripts\benchmark.py --tier chain
```

Результаты: `reports/benchmark.csv`, `reports/benchmark.json`,
`reports/benchmark.md`.

Дополнительно к `evaluate.py` считаются:

| Метрика | Проверка |
|---|---|
| `case_success_rate` | успешны все реплики кейса |
| `context_retention_rate` | сущность сохранилась в `resolved_query` или ответе |
| `context_rewrite_rate` | сущность явно попала в `resolved_query` |
| `context_answer_rate` | сущность видна в ответе |
| `chain_context_retention_rate` | retention только по цепочкам |
| `tool_accuracy` / `strategy_accuracy` | ожидаемые инструменты и стратегия Analytics |

Подробное описание — `docs/benchmark.md`.

## Ограничение провайдера

На free-тарифе NeuralDeep действует сессионный лимит: **400 chat-запросов
за 3 часа** и 20 запросов/мин. Полный прогон 26 кейсов расходует лимит,
поэтому оценку лучше запускать после сброса окна (`/v1/limits`).
`evaluate.py` поддерживает `--limit` и `--only`, чтобы прогнать подмножество.

## Фактический прогон

26 кейсов, seed 42:

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
лимита токенов он проходит отдельно. Повторный полный прогон ограничен
free-тарифом (400 запросов / 3 часа).

## Воспроизводимость

- temperature 0;
- фиксированный seed данных 42;
- одинаковый набор кейсов;
- фиксированная дата среза `2026-11-21`.
