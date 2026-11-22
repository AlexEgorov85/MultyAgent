# Автоматическая доработка по бенчмарку

Конкретный план работ по текущим результатам — `docs/improvement_plan.md`.

Цель — превратить `reports/benchmark.json` в управляемый цикл:

```text
прогон → triage → proposal → sandbox → diff → gate → PR / откат
```

Инструменты не меняют код автоматически. Они готовят диагностику,
предложение и проверку, чтобы изменение применял человек или coding-agent
в отдельной ветке.

## Команды

```powershell
# 1. Полный или целевой прогон
.venv\Scripts\python.exe scripts\benchmark.py --tier simple

# 2. Сохранить baseline
Copy-Item reports\benchmark.json reports\benchmark_baseline.json

# 3. Разобрать провалы и получить backlog
.venv\Scripts\python.exe scripts\benchmark_triage.py

# 4. Получить безопасное предложение по топ-кластеру
.venv\Scripts\python.exe scripts\improve_agent.py --index 1

# 5. После изменения — снова benchmark и сравнение
.venv\Scripts\python.exe scripts\benchmark.py --only failing_case_1 failing_case_2
.venv\Scripts\python.exe scripts\benchmark_diff.py ^
    reports\benchmark_baseline.json reports\benchmark.json --gate
```

Отчёты:

| Файл | Что внутри |
|---|---|
| `reports/benchmark_backlog.md` | приоритизированный backlog |
| `reports/benchmark_backlog.json` | то же для автоматики |
| `reports/improvement_proposal.md` | гипотеза, файлы, проверка, ограничения |
| `reports/benchmark_diff.md` | улучшения, регрессии, gate |
| `reports/benchmark_diff.json` | машинный diff |

## Классификация провалов

`src/improvement.py` относит реплику к категориям:

| Категория | Признак | Что менять |
|---|---|---|
| `provider` | `llm_errors > 0` | backoff/лимит, не промпт |
| `runtime` | ошибка выполнения | окружение, БД, код |
| `routing` | `route_ok=false` | router, pre-router |
| `context` | `context_resolved_ok=false` | resolver и слоты |
| `tool_policy` | `tools_ok=false`, `strategy_ok=false` | tool descriptions, шаблоны |
| `sql` | `sql_ok=false`, retries | SQL-промпт, validator |
| `evidence` | `evidence_ok=false` | analytics/report/retrieval |
| `citations` | `citations_ok=false` | retrieval, critic |
| `numeric` | `numbers_ok=false` | SQL-агрегация и формат |
| `answer` | `must_include/exclude` | формат ответа |
| `steps` | `steps_ok=false` | ветка графа и trace |
| `efficiency` | лимиты вызовов/токенов/времени | model routing, контекст |
| `unknown` | провал без сработавшего признака | разобрать `state` вручную и добавить признак в triage |

`provider` и `runtime` исключаются из качества агента: при 429 или падении
БД остальные проверки недостоверны.

## Backlog

Для каждого кластера сохраняются:

- категория, приоритет, риск;
- уровень, маршрут, кейсы и реплики;
- токены, latency, число LLM/tool вызовов;
- примеры запросов и ошибок;
- затронутые промпты;
- файлы-кандидаты;
- команда целевого прогона.

Сортировка: `severity ↓`, затем частота, затем токены и время.
Приоритеты:

- 5 — routing, context, SQL, numeric;
- 4 — tools, evidence, citations;
- 3 — содержание ответа;
- 2 — шаги, эффективность;
- 0 — провайдер/runtime.

## Proposal

`scripts/improve_agent.py` не вызывает LLM и не меняет код. Он выбирает
кластер и формирует `improvement_proposal.md` (единственный побочный эффект —
запись отчётов, код и данные не трогаются):

- гипотеза;
- файлы;
- кейсы;
- примеры запросов;
- затронутые версии промптов;
- команда проверки;
- ограничения: не менять разметку, guardrails, не смешивать слои,
  поднимать версию промпта.

Дальше изменение применяется в отдельной ветке/worktree. Coding-agent может
использовать proposal как ТЗ.

## Diff и gate

`scripts/benchmark_diff.py` сравнивает два `benchmark.json`:

- улучшения и регрессии по `case_id.step`;
- изменения `route`, ответов;
- Δ токенов, latency, cost, LLM/tool calls;
- Δ summary.

`--gate` проверяет:

- `success_rate`, `answer_success_rate`, `process_success_rate` не упали;
- `total_tokens_total` не вырос больше чем на 10%;
- `latency_p95_sec` не вырос больше чем на 10%;
- `cost_usd_total` не вырос больше чем на 10%;
- число регрессий не больше заданного.

При провале скрипт возвращает код 1. Это позволяет использовать его в CI.

```powershell
.venv\Scripts\python.exe scripts\benchmark_diff.py ^
    reports\benchmark_baseline.json reports\benchmark.json ^
    --gate --max-regressions 0 --max-token-increase 0.10
```

## Что можно автоматизировать

| Слой | Автоматически | После gate |
|---|---|---|
| Промпты router/resolver | да, diff + версия | PR |
| Tool policy и few-shot | да | PR |
| SQL-примеры и repair-feedback | да, высокий риск | PR + review |
| Retrieval top_k/веса | да | PR |
| Формат ответа | да | PR |
| Model routing | да | PR |
| Backoff/retry | да | PR |
| Код графа и tools | предложение diff | обязательный review |
| Guardrails/allowlist | нет | только человек |
| Разметка benchmark | нет | только человек |
| Схема БД/секреты | нет | только человек |

## Уровни автономности

1. **Диагностика** — triage и backlog.
2. **Proposal** — файл с гипотезой и планом.
3. **Auto-PR** — агент применяет diff в worktree, гоняет тесты и benchmark.
4. **Auto-merge** — только низкорисковые промпты/конфиги с canary.
5. **Онлайн-самомодификация** — не рекомендуется.

## Ограничения

- Не подгонять `expected_*` под ответы агента.
- Держать holdout-кейсы.
- Повторять прогон 2–3 раза для нестабильных кейсов.
- Отделять 429/timeout от ошибок логики.
- Не менять больше одного слоя за эксперимент.
- Хранить baseline, версии промптов и `improvement_log.md`.

## Пример: прогон 22.11.2026

- `answer_success_rate` 0.631, `process_success_rate` 0.677,
  `success_rate` 0.538, `case_success_rate` 0.449.
- `route_accuracy` 0.985, `context_retention_rate` 0.938,
  `numeric_accuracy` 0.651, `tool_accuracy` 0.500, `evidence_coverage` 0.774.
- 263 LLM-вызова, 419 568 токенов, $0.275, p95 latency 62 с.

Главные кластеры backlog по этому прогону (порядок triage):

1. **Numeric**: 6 + 4 + 3 + 2 реплики в разных срезах — числа в ответе не
   совпадают с ожидаемыми (`medium_acts_approved_auditor`, `simple_acts_draft`,
   `chain_correction` и др.).
2. **SQL semantics**: 3 реплики — неполная группировка по статусам, неверный
   join `approved_by`, группировка `severity`.
3. **Resolver / context**: 2 + 1 реплика — потерян `item_type` в
   `chain_correction`, контекст в `chain_agent_switch`.
4. **Router**: 1 реплика — definitional-вопрос ушёл в `smalltalk`.
5. **Tool policy / template**: 4 реплики — LLM выбирает несуществующие
   `template_key` или `status_summary` без `year`.
6. **Efficiency**: 97.5% времени — LLM; около 4 LLM-вызовов на реплику.

Первый практичный шаг — валидировать `template_key` и параметры до
выполнения, с fallback на generated SQL. Это один слой, который закрывает
сразу несколько кластеров.

## Следующие шаги

- `--variant` в `benchmark.py` для A/B промптов и моделей;
- `--repeat 3` и pass@k для оценки нестабильности;
- `scripts/improve_agent.py --apply` в git worktree с автоматическим
  запуском pytest и benchmark;
- `reports/improvement_log.md` с принятыми и отклонёнными изменениями;
- CI-job: `pytest` + `benchmark_diff --gate`.
