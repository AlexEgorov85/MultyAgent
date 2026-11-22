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
| PostgreSQL + миграции | ✅ `db/migrations/001–007`, реестр `public.schema_migrations` |
| Генератор данных | ✅ инварианты `data-generation`, детерминированный seed 42 |
| QA-проверки данных | ✅ `scripts/qa_checks.py`, включая расписание, дубли, шаблоны |
| SQL safety | ✅ `src/tools/sql_guard.py`, `src/tools/db.py`, 33 теста |
| Agent protocol | ✅ `src/acl.py`: FIPA-ACL, корреляция, JSONL-журнал |
| Analytics-агент | ✅ QueryPlan → детерминированный SQL, шаблоны, drill-down, multi-tool, fallback NL→SQL |
| Query IR | ✅ semantic catalog + детерминированный SQL-компилятор |
| Capabilities | ✅ typed templates + deterministic matcher |
| Dialogue slots | ✅ year/theme/item_type/risk/status/audit_code |
| Retrieval-агент | ✅ индекс методичек/пунктов/актов, гибридный поиск, цитаты, критик |
| Report + Inspector | ✅ проект акта, проверка ID и evidence, до 2 исправлений |
| Investigation (A7) | ✅ Coordinator, два раунда ACL, факт vs гипотеза |
| Основной граф | ✅ Router + ACL-ветки + `thread_id`-память + профиль аудитора |
| Guardrails | ✅ блокировка изменения данных, PII, prompt injection, проверка SQL |
| Веб-интерфейс | ✅ assistant-ui + LangGraph API (`ui/`) |
| Тесты | ✅ 284 passed (`pytest -q`) |
| Проверки интерфейса | ✅ `npm --prefix ui run lint`, `npm --prefix ui run build` |

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
  трёхуровневый номер пункта (`5.1.1`).

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

> **Статус измерений.** Таблица ниже — исторический прогон `evaluate.py`
> на 26 кейсах (seed 42, модель `qwen3.6-35b-a3b-noreason`). Она не
> пересчитана на текущей ревизии кода. Отчёты `reports/*.csv`,
> `reports/*.json` и сгенерированные `reports/*.md` не коммитятся
> (кроме `reports/README.md`): их нужно сгенерировать заново перед сдачей
> и сверить с этой таблицей.

| Метрика | Значение (исторический прогон) |
|---|---:|
| `route_accuracy` | 1.000 |
| `success_rate` | 0.962 (25/26) |
| `sql_validity_rate` | 1.000 |
| `evidence_coverage` | 0.962 |
| `latency_mean_sec` | 28.3 |
| `latency_p50_sec` | 10.9 |
| `latency_p95_sec` | 72.1 |

Единственный сбой того прогона (`an_08`, обрезка JSON плана SQL) был
исправлен и проверен отдельным запуском. Повторный полный прогон не
выполнялся на текущей ревизии: он расходует лимит free-тарифа
(400 chat-запросов за 3 часа). Пока новый прогон не сделан, числа выше
не следует приводить как результат текущей версии.

Бенчмарк `data/benchmark_cases.jsonl` (49 кейсов / 65 реплик) прогнан
22.11.2026 на `qwen3.6-35b-a3b-noreason` (baseline до внедрения Query IR,
`run_id` `1795295013-13fd4f`): `answer_success_rate` 0.631,
`process_success_rate` 0.677, `success_rate` 0.538, `case_success_rate` 0.449,
`route_accuracy` 0.985, `numeric_accuracy` 0.651, `context_retention_rate` 0.938.
Расход: 263 LLM-вызова, 419 568 токенов, $0.275; p95 latency 62 с.
Первичный отчёт до исправления matcher чисел сохранён как
`reports/benchmark_unresolved.json`, исправленный — `reports/benchmark.json`,
разбор провалов — `reports/benchmark_backlog.md`.

## Метрики и оценка

```powershell
# проверить структуру набора без LLM
.venv\Scripts\python.exe scripts\evaluate.py --dry-run

# полный прогон (нужен OPENAI_API_KEY и построенный индекс)
.venv\Scripts\python.exe scripts\evaluate.py

# три прогона с mean/std (расходует лимит провайдера)
.venv\Scripts\python.exe scripts\evaluate.py --repeat 3
```

Результаты: `reports/metrics.csv` и `reports/metrics.md`.
Набор: `data/test_cases.jsonl` (26 кейсов).

### Бенчмарк: простые, средние, сложные и цепочки

Дополнительный набор `data/benchmark_cases.jsonl` — 49 кейсов и 65 реплик:
13 простых, 18 средних, 10 сложных и 8 цепочек по 3 реплики. Кейсы покрывают
все основные таблицы — от `audit_pockets` и `act_items` до `script_runs`,
`deviations`, `auditor_memory` и `dataset_metadata`. В цепочках
контролируется перенос года, темы, типа находки, фильтра риска и кода
проверки в `resolved_query` и ответ; `chain_ui_recovery` восстанавливает
контекст из `client_history` после смены нити.

```powershell
# структура набора без LLM
.venv\Scripts\python.exe scripts\benchmark.py --dry-run

# уровни и отдельные кейсы
.venv\Scripts\python.exe scripts\benchmark.py --tier simple
.venv\Scripts\python.exe scripts\benchmark.py --tier medium
.venv\Scripts\python.exe scripts\benchmark.py --tier complex
.venv\Scripts\python.exe scripts\benchmark.py --tier chain
.venv\Scripts\python.exe scripts\benchmark.py --only chain_overdue_risk
```

Результаты: `reports/benchmark.csv`, `reports/benchmark.json`,
`reports/benchmark.md`. Оценивается не только ответ, но и процесс:

- вызовы LLM, инструментов и эмбеддингов, input/output/cached токены,
  стоимость;
- шаги `trace`, ACL-конверт, SQL-retries, ACL-раунды Inspector;
- время: общее, LLM, инструменты, overhead и доли;
- версии промптов `id@vN:hash` и полный реестр версий;
- снимок состояния агента (`state`) и `fingerprint` в JSON.

Основные метрики: `answer_success_rate`, `process_success_rate`,
`success_rate`, `route_accuracy`, `numeric_accuracy`, `tool_accuracy`,
`steps_ok`, `evidence_coverage`, `citation_coverage`,
`context_retention_rate`, `tokens_per_success`, `cost_per_success_usd`.
Подробно — `docs/benchmark.md`.

### Автоматическая доработка по бенчмарку

```powershell
# backlog провалов: категории, приоритеты, файлы и команды проверки
.venv\Scripts\python.exe scripts\benchmark_triage.py

# безопасное предложение по топ-кластеру (без изменения кода)
.venv\Scripts\python.exe scripts\improve_agent.py --index 1

# сравнение baseline/candidate и regression-gate
Copy-Item reports\benchmark.json reports\benchmark_baseline.json
# ... изменение и новый прогон ...
.venv\Scripts\python.exe scripts\benchmark_diff.py ^
    reports\benchmark_baseline.json reports\benchmark.json --gate
```

Triage отделяет провайдера/runtime от ошибок агента, группирует провалы по
router/context/tools/SQL/evidence/citations/numeric/efficiency и пишет
`reports/benchmark_backlog.md`. Diff считает Δ success, токенов, latency и
стоимости; `--gate` возвращает код 1 при регрессиях. Архитектура цикла —
`docs/improvement_loop.md`.

Документация: `docs/architecture.md`, `docs/metrics.md`,
`docs/benchmark.md`, `docs/improvement_loop.md`, `docs/improvement_plan.md`,
`docs/query_ir.md`, `docs/sql_safety.md`, `docs/screencast_script.md`.

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

Слева расположен список чатов: можно создать новый диалог, вернуться
к предыдущему или удалить его. Список и локальный кэш сообщений хранятся
в `localStorage` браузера, а серверная нить продолжается по сохранённому
`thread_id`.

Диалог контекстный: последние реплики передаются маршрутизатору и агентам,
а уточнения вроде «а за 2025 год?» или «а по картам?» переформулируются в
самостоятельный вопрос.

Сообщения и заголовки чатов сохраняются в PostgreSQL (`audit.chat_threads`
и `audit.chat_messages`) по стабильному `conversation_id`. Состояние
LangGraph checkpointer (`InMemorySaver`) перезапуск backend не переживает,
но контекст последних реплик восстанавливается из истории в PostgreSQL.
Если недоступна и серверная история, UI присылает `client_history`
из `localStorage`.

После обновления кода примените миграции:

```powershell
.venv\Scripts\python.exe scripts\init_db.py
```

> **Важно про язык интерфейса.** `langgraph dev` предлагает
> **LangGraph Studio** (`smith.langchain.com/studio`) — это сторонний
> облачный интерфейс LangChain с английскими меню и настройками. Он не
> входит в проект и не локализуется. Для работы используйте именно
> `http://localhost:3000`: в нём есть собственные настройки
> (шестерёнка внизу слева), меню и переключение языка **RU / EN**.
> Ответы ассистента формируются на языке вопроса.
>
> Английский значок внизу слева, который показывал меню `Route Info` /
> `Preferences`, — это индикатор **Next.js DevTools**. Он отключён в
> `ui/next.config.ts` (`devIndicators: false`), поэтому вместо него
> остаётся только русская шестерёнка настроек приложения.

### Настройки интерфейса

Шестерёнка внизу слева или «Меню → Настройки» открывает панель с вкладками
«Интерфейс», «Поведение», «Данные» и «О системе». Доступны:

- тема (светлая / тёмная / системная), акцентный цвет, шрифт, фон чата;
- размер интерфейса и отдельный размер текста чата;
- плотность сообщений, скругление углов, ширина диалога;
- анимации и стеклянный эффект;
- язык RU / EN, отправка по Enter или Ctrl+Enter, время сообщений,
  аватары, подсказки и статус «онлайн»;
- идентификатор аудитора, новый диалог и сброс настроек.

Настройки сохраняются в `localStorage` браузера и применяются сразу.

Браузер обращается к LangGraph через собственный прокси интерфейса:
`NEXT_PUBLIC_LANGGRAPH_API_URL=/api` → `ui/app/api/[..._path]/route.ts`
(белый список путей и методов) → `LANGGRAPH_API_URL`. Так одинаково
работают и `http://localhost:3000`, и публичная ссылка: браузеру не нужен
доступ к порту 2024 и не нужен CORS.

```dotenv
NEXT_PUBLIC_LANGGRAPH_API_URL=/api
NEXT_PUBLIC_LANGGRAPH_ASSISTANT_ID=audit_assistant
LANGGRAPH_API_URL=http://127.0.0.1:2024
```

> `NEXT_PUBLIC_*` встраивается в бандл при сборке: после изменения
> `ui/.env.local` перезапустите `npm run dev` (в production — пересоберите UI).

### Показать интерфейс по ссылке

Один туннель на порт 3000 — и ссылку можно открыть с другого компьютера:

```powershell
winget install --id Cloudflare.cloudflared   # один раз
powershell -ExecutionPolicy Bypass -File scripts\share_ui.ps1
```

Скрипт поднимает API и UI, открывает туннель и печатает адрес
`https://<...>.trycloudflare.com`. Пароль на ссылку обязателен: он задаётся
переменной `SHARE_BASIC_AUTH_PASSWORD` в `ui/.env.local` или скриптом
`scripts\share_auth.ps1 -On -Password '...'`. Без пароля `share_ui.ps1`
откажется поднимать туннель; осознанно открыть демо можно флагом `-NoAuth`.
Если нужен постоянный адрес и вход через Cloudflare Access (по email),
см. вариант 2 в `docs/share_ui.md` и запуск с
`-TunnelName <имя> -Hostname <домен> -NoAuth`: Access закрывает доступ,
поэтому локальный Basic Auth отключается осознанно. Если Cloudflare-туннель
в вашей сети не держит соединение (`530`/`1033`), запускайте с `-Serveo` —
тот же скрипт поднимет SSH-туннель.

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
src/telemetry.py          процессные метрики: LLM, tools, промпты, время
src/improvement.py        triage, diff и regression-gate бенчмарка
src/semantic/             каталог метрик, измерений и допустимых значений
src/query/                QueryPlan и детерминированный SQL-компилятор
src/capabilities/         typed template capabilities и deterministic matcher
src/dialogue_slots.py     слоты диалога: год, тема, тип, риск, код
db/migrations/          001–007: расширения, схема, views, история чата, as_of_date
scripts/generate_data.py  детерминированная генерация CSV и методичек
scripts/init_db.py        pgserver, миграции, read-only роль, загрузка CSV
scripts/qa_checks.py      проверки качества данных
scripts/demo_queries.py   демонстрационные read-only запросы
scripts/evaluate.py       оценка по test_cases.jsonl
scripts/benchmark.py      бенчмарк simple/medium/complex/chain + процессные метрики
scripts/benchmark_rescore.py пересчёт отчётов после правки бенчмарка
scripts/benchmark_triage.py backlog провалов и файлы-кандидаты
scripts/benchmark_diff.py сравнение прогонов и regression-gate
scripts/improve_agent.py  безопасное предложение по доработке
scripts/run_db.py         живой PostgreSQL для ручной проверки
scripts/run_analytics.py  CLI Analytics-агента
scripts/run_retrieval.py  CLI Retrieval-агента
scripts/run_report.py     CLI Report-агента
scripts/run_investigation.py CLI расследования (A7)
scripts/run_chat.py       интерактивный чат основного графа
scripts/build_index.py    построение RAG-индекса
scripts/share_ui.ps1      API + UI + туннель одной командой (docs/share_ui.md)
scripts/share_auth.ps1    включить/выключить пароль на лету
ui/                       assistant-ui (Next.js) поверх LangGraph API
data/benchmark_cases.jsonl  простые, средние, сложные и цепочечные кейсы
data/knowledge/           методические документы для RAG
data/seed/                сгенерированные CSV (не коммитятся)
data/pg/                  кластер PostgreSQL (не коммитится)
```

## Архитектура

```text
UI (assistant-ui, Next.js) ── /api (same-origin proxy) ── LangGraph API
                                                            │
                                    ┌───────────────────────┼───────────────────────┐
                                    ▼                       ▼                       ▼
                                 Router              Guardrails              Memory (thread_id)
                                    │
        ┌───────────────┬───────────┼────────────┬──────────────────┐
        ▼               ▼           ▼            ▼                  ▼
   Analytics        Retrieval    Report +    Investigation      Smalltalk
   (NL→SQL,         (RAG,       Inspector    (ACL-раунды,
    шаблоны,         цитаты,      (проект      факт vs
    drill-down)      критик)      акта)        гипотеза)
        │               │           │            │
        └───────────────┴───────────┴────────────┘
                            │
                   PostgreSQL: audit.* + pgvector
```

Подграфы общаются ACL-конвертом (`src/acl.py`), а не прямыми вызовами
функций на уровне бизнес-логики. Подробнее: `docs/architecture.md`,
`docs/sql_safety.md`.

## Примеры

Типовые сценарии из набора оценки `data/test_cases.jsonl` (маршрут и
инструменты — ожидаемые значения, проверяемые `evaluate.py`):

| Запрос | Маршрут | Что делает система |
|---|---|---|
| «Сколько завершённых проверок по ипотеке в 2026 году?» | `analytics` | строит read-only SQL, показывает запрос и результат с evidence |
| «Найди отклонения по проверке AUD-2026-MORTGAGE-03 и похожие формулировки в других актах» | `analytics` | два инструмента в одном вызове (`get_act_items` + `search_acts`) |
| «Найди отклонения про просроченную актуализацию оценки залога» | `retrieval` | гибридный поиск, ответ с цитатами, критик проверяет обоснованность |
| «Сформируй проект раздела акта по AUD-2026-MORTGAGE-03» | `report` | факты из БД → черновик → Inspector; каждое утверждение со ссылкой на ID |
| «Почему в ипотеке в 2026 году выросла доля просроченных пунктов?» | `investigation` | два ACL-раунда Analytics + Retrieval, факт отделяется от гипотезы |
| «Я проверяю ипотеку, акт нужен в кратком формате» | `memory` | профиль сохраняется, в следующем отчёте подставляются тема и формат |
| «Удали все пункты из базы» | `unsafe` | guardrail отказывает: изменение данных запрещено |

Значения метрик по этим сценариям — в разделе «Результаты оценки» выше.
Полные команды запуска каждого агента — в разделе «Быстрый старт».

## Технологии

- **Backend:** Python 3.12, LangGraph 1.2, OpenAI-совместимый провайдер
  NeuralDeep (`qwen3.6-35b-a3b-noreason`, эмбеддинги `frida`), Pydantic 2.
- **Данные:** PostgreSQL 16 (встроенный `pgserver`), pgvector, полнотекстовый
  поиск `russian`, psycopg 3, sqlglot, миграции `db/migrations/001–007`.
- **Frontend:** Node.js 20+ (`ui/.nvmrc`), Next.js 16, React 19,
  `assistant-ui`, TypeScript, Tailwind CSS 4, ESLint.
- **Проверки:** pytest, `scripts/qa_checks.py`, `scripts/evaluate.py`,
  `scripts/benchmark.py`, `scripts/verify_clean_clone.py`, OpenSpec.

## Ограничения и безопасность

- **Синтетические данные.** Проект учебный; набор сгенерирован seed 42.
  Не подключайте реальные банковские данные и персональную информацию.
- **Демо-доступ.** Публичный туннель запускается только с паролем
  (Basic Auth) или с явным флагом `-NoAuth`. Пароль общий, персональных
  учётных записей нет.
- **Владение чатом.** Переименование и удаление проверяют `auditor_id`
  владельца в PostgreSQL, но сам `auditor_id` выбирается в настройках UI и
  не является аутентификацией. Это защита от случайных действий, а не от
  злоумышленника с доступом к демо.
- **Секреты.** Ключ LLM и DSN остаются на backend; `.env` и `ui/.env.local`
  не коммитятся. В браузерном bundle ключей нет.
- **SQL.** Только read-only `SELECT` по allowlist, роль `audit_ro`,
  `statement_timeout` 5 секунд и принудительный `LIMIT`.
- **Память.** Краткосрочная: `thread_id` + история в PostgreSQL и профиль
  аудитора. Долговременной семантической памяти нет.
- **Задержки.** Исторический p95 — около 72 секунд. Публичный туннель
  Cloudflare обрывает запрос на 100 секундах: долгий ответ может не дойти,
  вопрос придётся повторить.
- **Free-тариф LLM.** 400 chat-запросов за 3 часа и 20 запросов/мин;
  полный live-прогон расходует заметную часть лимита.

## Скринкаст

Сценарий на 10 минут: `docs/screencast_script.md` (аналитика, шаблон,
drill-down, multi-tool, retrieval, отчёт, investigation, память, guardrail,
метрики, тесты). Перед сдачей видео записывается по этому сценарию и
проверяется в режиме инкогнито; ссылка добавляется в этот раздел.

> Видео не входит в репозиторий: `*.mp4`, `*.mov` и архивы запрещены
> правилами сдачи и `.gitignore`.

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
| Скринкаст | ссылка из раздела выше в инкогнито | доступна без запроса |

Живой прогон `evaluate.py`/`benchmark.py` не входит в обязательные
офлайн-проверки: он требует ключ и расходует лимит провайдера. Если он
выполнен, обновите таблицу метрик выше, укажите дату и `run_id`, а отчёты
в `reports/` сохраните вне git.
