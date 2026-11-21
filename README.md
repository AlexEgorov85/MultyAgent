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
| Основной граф | ✅ Router + ACL-ветки + `thread_id`-память + профиль аудитора |
| Guardrails | ✅ блокировка изменения данных, PII, prompt injection, проверка SQL |
| Веб-интерфейс | ✅ assistant-ui + LangGraph API (`ui/`) |
| Тесты | ✅ 92 passed |
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
`https://api.neuraldeep.ru/v1`. Чат — `qwen3.6-35b-a3b-noreason`
(быстрый структурированный вывод, 256k контекст), эмбеддинги — `frida`
(RU-first, 1536 измерений). Ключ `sk-...` добавляется в `.env`
как `OPENAI_API_KEY`.

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

Чат с памятью нити и профилем аудитора:

```powershell
.venv\Scripts\python.exe scripts\run_chat.py --auditor-id AUD-001 --thread-id demo-001
```

## Результаты оценки

Полный прогон 26 кейсов на seed 42:

| Метрика | Значение |
|---|---:|
| `route_accuracy` | 1.000 |
| `success_rate` | 0.962 (25/26) |
| `sql_validity_rate` | 1.000 |
| `evidence_coverage` | 0.962 |
| `latency_mean_sec` | 28.3 |
| `latency_p50_sec` | 10.9 |
| `latency_p95_sec` | 72.1 |

Единственный сбой (`an_08`, обрезка JSON плана SQL) исправлен и проверен
отдельным прогоном: `an_08` → OK. Следующий полный прогон должен дать 26/26.
Лимит free-тарифа — 400 chat-запросов на 3 часа.

## Метрики и оценка

```powershell
# проверить структуру набора без LLM
.venv\Scripts\python.exe scripts\evaluate.py --dry-run

# полный прогон (нужен OPENAI_API_KEY и построенный индекс)
.venv\Scripts\python.exe scripts\evaluate.py
```

Результаты: `reports/metrics.csv` и `reports/metrics.md`.
Набор: `data/test_cases.jsonl` (26 кейсов).

Документация: `docs/architecture.md`, `docs/metrics.md`,
`docs/sql_safety.md`, `docs/screencast_script.md`.

## Проверка чистого клона

```powershell
# базовая проверка: клон, зависимости, БД, seed, индекс, QA, тесты, API
python scripts/verify_clean_clone.py

# плюс production-сборка UI
python scripts/verify_clean_clone.py --with-ui

# плюс живой LLM-запрос (расходует лимит провайдера)
python scripts/verify_clean_clone.py --with-live --index openai
```

Скрипт клонирует `origin/main` в отдельный каталог, поднимает БД,
проверяет идемпотентность seed, строит индекс, запускает QA/pytest,
проверяет API и (опционально) UI. Клон удаляется после проверки;
`--keep` оставляет его для разбора.

## Веб-интерфейс

Готовый чат на `assistant-ui` (Next.js) находится в `ui/`.

```powershell
# 1. API-сервер графа
.venv\Scripts\langgraph.exe dev --port 2024 --no-browser

# 2. во втором терминале — интерфейс
Copy-Item ui\.env.local.example ui\.env.local
npm --prefix ui install
npm --prefix ui run dev
```

Откройте `http://localhost:3000`. Интерфейс работает с тем же графом:
маршрутизация, SQL, retrieval, отчёт, расследование, память и guardrails.
Ключ LLM остаётся только на backend.

Браузер обращается не напрямую к `:2024`, а к Next-прокси `/api/*`
(`ui/app/api/[..._path]/route.ts`), поэтому CORS не нужен. Адрес API
задаётся в `ui/.env.local`:

```dotenv
LANGGRAPH_API_URL=http://127.0.0.1:2024
NEXT_PUBLIC_LANGGRAPH_ASSISTANT_ID=audit_assistant
```

> `.env` должен оставаться в ASCII. `langgraph dev` читает его через
> `python-dotenv` с локальной кодировкой Windows (cp1251), и кириллические
> комментарии вызывают `UnicodeDecodeError`. Поэтому комментарии
> в `.env.example` — на английском.

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
scripts/run_chat.py       интерактивный чат основного графа
scripts/build_index.py    построение RAG-индекса
ui/                       assistant-ui (Next.js) поверх LangGraph API
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
