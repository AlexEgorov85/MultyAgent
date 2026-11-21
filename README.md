# Ассистент внутреннего аудитора

Мультиагентная аналитическая система на LangGraph для внутреннего аудита банка.
Аудитор задаёт вопрос на русском языке, система строит безопасный SQL, ищет
похожие находки в актах и готовит проект раздела акта со ссылками на источники.

> Учебный проект. Все данные синтетические, совпадения с реальными
> организациями и людьми случайны.

## Статус

| Слой | Готовность |
|---|---|
| Домен и план | ✅ схема «карманы → проверки → акты → пункты → скрипты» |
| OpenSpec-спецификации | ✅ 13 возможностей, `openspec validate --specs --strict` |
| PostgreSQL + миграции | ✅ `db/migrations/001–005`, реестр `public.schema_migrations` |
| Генератор данных | ✅ инварианты `data-generation`, детерминированный seed 42 |
| QA-проверки данных | ✅ `scripts/qa_checks.py`, включая расписание, дубли, шаблоны |
| SQL safety | ✅ `src/tools/sql_guard.py`, `src/tools/db.py`, 40 тестов |
| Agent protocol | ✅ `src/acl.py`: FIPA-ACL, корреляция, JSONL-журнал |
| Analytics-агент | ✅ LangGraph: NL→SQL, шаблоны, drill-down, multi-tool |
| Retrieval-агент | ✅ индекс методичек/пунктов/актов, гибридный поиск, цитаты, критик |
| Report + Inspector | ✅ проект акта, проверка ID и evidence, до 2 исправлений |
| Investigation (A7) | ✅ Coordinator, два раунда ACL, факт vs гипотеза |
| Тесты | ✅ 73 passed |
| Остальные агенты | ⏳ report, investigation |
| Чат-интерфейс (assistant-ui) | ⏳ следующий этап |

## Спецификации (OpenSpec)

Целевое поведение описано в `openspec/specs/`. Спецификации — источник истины
для реализации; при изменении поведения обновляйте соответствующий `spec.md`.

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

Проверка:

```powershell
openspec validate --specs --strict
openspec list --specs
```

## Данные

- **10 карманов**: 5 тем (ипотека, потребкредитование, платежи, карты, вклады)
  × 2 года (2025, 2026).
- **95 проверок**, **79 актов**, **600 пунктов**, **949 скриптов**,
  **949 запусков**, **2 954 отклонения** — baseline seed 42.
- Находки двух типов: `отклонение` (количественное, есть скрипт и `rows_found > 0`)
  и `проблема` (качественная, скрипт может отсутствовать).
- 12–15% пунктов 2026 года — повторные находки со ссылкой на пункт 2025 года.
- У каждого пункта есть `finding_template_key` и `finding_scope`; неразличимых
  дублей внутри акта нет, проверки одного аудитора не пересекаются по датам.
- Ловушки для демонстрации: отменённая проверка без акта, акт на согласовании,
  пункт без скрипта, просроченный открытый пункт, запуск со статусом `ошибка`,
  трёхуровневый номер пункта (`5.2.1`).

Baseline соответствует спецификациям `data-platform` и `data-generation`.
Остальные спецификации реализуются поэтапно.

**Языковая политика:** предметные и пользовательские значения в БД — на русском.
Технические идентификаторы (`PKT-2025-MORTGAGE`, `AUD-2026-CARDS-03`), email,
SQL и код скриптов — латиницей и не выдаются за пользовательские подписи.

## Быстрый старт

Провайдер LLM — **NeuralDeep**: OpenAI-совместимый endpoint
`https://api.neuraldeep.ru/v1`. Чат — `qwen3.6-35b-a3b` (tools, reasoning,
256k контекст), эмбеддинги — `frida` (RU-first, 1536 измерений).
Ключ `sk-...` добавляется в `.env` как `OPENAI_API_KEY`.

Нужен Python 3.12 (pgserver не поддерживает 3.13+). Если 3.12 нет:

```powershell
python -m pip install --user uv
python -m uv python install 3.12
python -m uv venv --python 3.12 .venv
python -m uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

Генерация и загрузка данных:

```powershell
.venv\Scripts\python.exe scripts\generate_data.py --deviations
.venv\Scripts\python.exe scripts\init_db.py --reset-db --yes --seed
.venv\Scripts\python.exe scripts\build_index.py --hash
.venv\Scripts\python.exe scripts\qa_checks.py
.venv\Scripts\python.exe -m pytest -q
```

Проверить базу вручную:

```powershell
# поднять сервер и получить DSN (Ctrl+C — остановить)
.venv\Scripts\python.exe scripts\run_db.py

# прогнать демонстрационные read-only запросы через sql_guard
.venv\Scripts\python.exe scripts\demo_queries.py --json reports\demo_queries.json
```

Запустить Analytics-агента (нужен `OPENAI_API_KEY` в `.env`):

```powershell
Copy-Item .env.example .env
# вписать ключ в .env
.venv\Scripts\python.exe scripts\run_analytics.py --question "Сколько завершённых проверок по ипотеке в 2026 году?"
```

Запустить Retrieval-агента:

```powershell
.venv\Scripts\python.exe scripts\run_retrieval.py --question "Что сказано про просроченную оценку залога?"
```

Сформировать проект раздела акта:

```powershell
.venv\Scripts\python.exe scripts\run_report.py --question "Сформируй раздел акта по AUD-2026-MORTGAGE-03"
```

Провести расследование:

```powershell
.venv\Scripts\python.exe scripts\run_investigation.py --question "Почему в ипотеке в 2026 году выросла доля просроченных пунктов?"
```

`init_db.py` поднимает встроенный PostgreSQL 16 через `pgserver`,
применяет миграции и создаёт read-only роль `audit_ro`.

### Особенность Windows с кириллическим именем пользователя

`initdb` падает с `invalid byte sequence for encoding "UTF8"`, если путь
к установке PostgreSQL содержит не-ASCII символы. `init_db.py` автоматически
копирует `pginstall` в `%PUBLIC%\audit-assistant-pg` и переключает `pgserver`
на этот путь. Данные при этом могут лежать в исходном каталоге проекта.

## Структура

```text
openspec/specs/          целевые спецификации по возможностям
src/                     конфигурация, lifecycle БД, ACL, tools (SQL-guard, templates)
db/migrations/          001–005: расширения, схема, views, выравнивание со спеками
scripts/generate_data.py  детерминированная генерация CSV и методичек
scripts/init_db.py        pgserver, миграции, read-only роль, загрузка CSV
scripts/qa_checks.py      проверки качества данных
scripts/demo_queries.py   демонстрационные read-only запросы
scripts/run_db.py         живой PostgreSQL для ручной проверки
scripts/run_analytics.py  CLI Analytics-агента
scripts/run_retrieval.py  CLI Retrieval-агента
scripts/run_report.py     CLI Report-агента
scripts/run_investigation.py CLI расследования (A7)
scripts/build_index.py    построение RAG-индекса
data/knowledge/           методические документы для RAG
data/seed/                сгенерированные CSV (не коммитятся)
data/pg/                  кластер PostgreSQL (не коммитится)
```

## Дальше по плану

1. Закрыть расхождения генератора и QA со спецификацией `data-generation`.
2. LangGraph: Router, Analytics (NL→SQL + sql_guard), Retrieval (pgvector + FTS),
   Report + Inspector, Guardrail, FIPA-ACL между подграфами.
3. assistant-ui поверх LangGraph API server.
4. Метрики эффективности и качества, `scripts/evaluate.py`.
5. A7: investigation-ветка Coordinator ↔ Analytics ↔ Retrieval.
6. README с архитектурой, метриками и ограничениями; скринкаст ≤ 10 минут.

Подробный план — в `ПЛАН_ПРОЕКТА.md`.
