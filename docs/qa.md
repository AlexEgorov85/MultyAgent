# Проверки и подготовка к сдаче

## Чек-лист перед сдачей

| Проверка | Команда | Ожидание |
|---|---|---|
| Тесты | `.venv\Scripts\python.exe -m pytest -q` | все зелёные, 0 failed |
| QA данных | `.venv\Scripts\python.exe scripts\qa_checks.py` | без нарушений |
| Набор оценки | `.venv\Scripts\python.exe scripts\evaluate.py --dry-run` | 26 кейсов валидны |
| Бенчмарк | `.venv\Scripts\python.exe scripts\benchmark.py --dry-run` | 49 кейсов / 65 реплик |
| Спецификации | `openspec validate --specs --strict` | 13 passed, 0 failed |
| UI | `npm --prefix ui run lint` и `npm --prefix ui run build` | exit code 0 |
| Чистый клон | `python scripts/verify_clean_clone.py --no-env --with-ui` | `RESULT: OK` |
| Секреты | `git status`, `git ls-files` | нет `.env`, ключей, БД, видео |
| Скринкаст | ссылка из README в инкогнито | доступна без запроса |

Живой прогон `evaluate.py`/`benchmark.py` не входит в обязательные
офлайн-проверки: он требует ключ и расходует лимит провайдера
(400 chat-запросов за 3 часа, 20 запросов/мин). Если он выполнен,
обновите сводки в [metrics.md](metrics.md) и [benchmark.md](benchmark.md),
укажите дату и `run_id`; отчёты в `reports/` сохраните вне git.

## Проверка чистого клона

```powershell
# базовая проверка: клон, зависимости, БД, seed, индекс, QA, тесты, API
python scripts/verify_clean_clone.py

# проверить конкретную ветку/SHA и репозиторий, без секретов в клоне
python scripts/verify_clean_clone.py --repo origin --ref main --no-env

# плюс production-сборка UI
python scripts/verify_clean_clone.py --with-ui

# плюс живой LLM-запрос (расходует лимит провайдера)
python scripts/verify_clean_clone.py --with-live --index openai
```

Скрипт клонирует репозиторий (`--repo`, по умолчанию `origin`) и указанную
ревизию (`--ref`, по умолчанию `main`) в отдельный каталог, поднимает БД,
проверяет идемпотентность seed, строит индекс, запускает QA/pytest,
проверяет API и (опционально) UI, а также отсутствие секретов и файлов
больше 5 МБ в git. `--no-env` не копирует `.env` и проверяет, что офлайн-этапы
не зависят от секретов. Клон удаляется после проверки; `--keep` оставляет
его для разбора. В конце печатается `RESULT: OK` или `RESULT: FAIL <причина>`,
код возврата 0/1.

## Спецификации (OpenSpec)

Целевое поведение описано в `openspec/specs/`. Спецификации — источник
истины для реализации; при изменении поведения обновляйте соответствующий
`spec.md` в том же изменении.

```powershell
openspec validate --specs --strict
openspec list --specs
```

| Возможность | Что описывает |
|---|---|
| `data-platform` | жизненный цикл PostgreSQL, миграции, роли, seed |
| `data-generation` | состав и инварианты синтетического набора |
| `sql-safety` | read-only SQL, allowlist, LIMIT, шаблоны |
| `analytics-agent` | NL→SQL, самокоррекция, evidence, multi-tool |
| `retrieval-rag` | индекс, гибридный поиск, цитаты, критик |
| `report-inspector` | проект акта и проверка обоснованности |
| `investigation-orchestration` | A7: раунды Coordinator ↔ Analytics ↔ Retrieval |
| `agent-protocol` | FIPA-ACL-конверт и корреляция сообщений |
| `conversation-memory` | `thread_id` и `auditor_memory` |
| `guardrails` | отказы, приватность, финальная проверка |
| `chat-ui` | assistant-ui, LangGraph API, секреты |
| `observability-evaluation` | метрики, тест-набор, evaluate.py |
| `delivery-and-qa` | README, чистый клон, скринкаст, тесты |

## Оценка качества

- `scripts/evaluate.py` — 26 кейсов `data/test_cases.jsonl`;
  метрики и исторические прогоны — [metrics.md](metrics.md).
- `scripts/benchmark.py` — 49 кейсов / 65 реплик
  `data/benchmark_cases.jsonl`, процессные метрики —
  [benchmark.md](benchmark.md).
- `scripts/benchmark_triage.py`, `scripts/benchmark_diff.py`,
  `scripts/improve_agent.py` — цикл доработки по провалам бенчмарка:
  backlog → правка → сравнение прогонов с regression-gate.
  Архитектура цикла — [improvement_loop.md](improvement_loop.md).

```powershell
# backlog провалов: категории, приоритеты, файлы и команды проверки
.venv\Scripts\python.exe scripts\benchmark_triage.py

# безопасное предложение по топ-кластеру (без изменения кода)
.venv\Scripts\python.exe scripts\improve_agent.py --index 1

# сравнение baseline/candidate и regression-gate
Copy-Item reports\benchmark.json reports\benchmark_baseline.json
# ... изменение и новый прогон ...
.venv\Scripts\python.exe scripts\benchmark_diff.py reports\benchmark_baseline.json reports\benchmark.json --gate
```

Triage отделяет провайдера/runtime от ошибок агента, группирует провалы по
router/context/tools/SQL/evidence/citations/numeric/efficiency и пишет
`reports/benchmark_backlog.md`. Diff считает Δ success, токенов, latency и
стоимости; `--gate` возвращает код 1 при регрессиях.

## Скринкаст

Сценарий на 10 минут: [screencast_script.md](screencast_script.md)
(аналитика, шаблон, drill-down, multi-tool, retrieval, отчёт,
investigation, память, guardrail, метрики, тесты). Перед сдачей видео
записывается по этому сценарию и проверяется в режиме инкогнито; ссылка
добавляется в README.

Видео не входит в репозиторий: `*.mp4`, `*.mov` и архивы запрещены
правилами сдачи и `.gitignore`.
