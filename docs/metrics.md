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

## Воспроизводимость

- temperature 0;
- фиксированный seed данных 42;
- одинаковый набор кейсов;
- фиксированная дата среза `2026-11-21`.
