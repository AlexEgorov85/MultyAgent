# Ассистент внутреннего аудитора

Мультиагентная аналитическая система на LangGraph для внутреннего аудита
банка. Аудитор задаёт вопрос на русском языке — система строит безопасный
SQL, ищет похожие находки в актах и методичках и готовит проект раздела
акта со ссылками на источники.

> Учебный проект. Все данные синтетические (seed 42), совпадения
> с реальными организациями и людьми случайны.

## Возможности

- **Analytics** — числа из БД: типизированные шаблоны, Query IR → SQL,
  drill-down, несколько инструментов в одном ходе, самокоррекция SQL.
- **Retrieval** — гибридный поиск (pgvector + FTS) по методичкам и актам,
  ответ с цитатами, LLM-критик.
- **Report** — проект раздела акта по фактам из БД, Inspector проверяет
  каждое утверждение (до 2 исправлений).
- **Investigation** — Coordinator ведёт до двух ACL-раундов
  Analytics + Retrieval и отделяет факт от гипотезы.
- **Память** — контекст диалога, уточнения («а за 2025 год?»),
  профиль аудитора между чатами.
- **Guardrails** — отказ на изменение данных, PII и prompt injection;
  только read-only SQL по allowlist.
- **Веб-чат** — assistant-ui (Next.js) поверх LangGraph API, RU/EN.

## Архитектура

```mermaid
flowchart LR
    UI["assistant-ui"] --> API["LangGraph API"] --> MAIN["Основной граф<br/>Router · Guardrails · Память"]
    MAIN <-->|FIPA-ACL| AN["Analytics"]
    MAIN <-->|FIPA-ACL| RE["Retrieval"]
    MAIN <-->|FIPA-ACL| RP["Report + Inspector"]
    MAIN <-->|FIPA-ACL| IN["Investigation"]
    IN <-->|FIPA-ACL| AN
    IN <-->|FIPA-ACL| RE
    AN & RE & RP & MAIN --> PG[("PostgreSQL 16 + pgvector")]
```

Вопрос проходит цепочку: память → переформулировка уточнения →
guardrails → LLM-маршрутизация → агент → финальная проверка → ответ
с evidence. Подагенты — отдельные LangGraph-графы, общаются только
FIPA-ACL-конвертами (`src/acl.py`).

**Подробно, с диаграммами всех графов и описанием работы:
[docs/architecture.md](docs/architecture.md).**

## Быстрый старт

Нужен Python 3.12 (pgserver не поддерживает 3.13+) и Node.js 20+ для UI.
LLM-провайдер — NeuralDeep (OpenAI-совместимый): чат
`qwen3.6-35b-a3b-noreason`, эмбеддинги `frida`.

```powershell
# 1. окружение (если Python 3.12 нет — через uv)
python -m pip install --user uv
python -m uv python install 3.12
python -m uv venv --python 3.12 .venv
python -m uv pip install --python .venv\Scripts\python.exe -r requirements.txt

# 2. ключ LLM
Copy-Item .env.example .env
# вписать OPENAI_API_KEY=sk-... в .env

# 3. данные, БД, индекс, проверки
.venv\Scripts\python.exe scripts\generate_data.py --deviations
.venv\Scripts\python.exe scripts\init_db.py --reset-db --yes --seed
.venv\Scripts\python.exe scripts\build_index.py --hash
.venv\Scripts\python.exe scripts\qa_checks.py
.venv\Scripts\python.exe -m pytest -q
```

`init_db.py` поднимает встроенный PostgreSQL 16 (`pgserver`), применяет
миграции `db/migrations/001–007` и создаёт read-only роль `audit_ro`.
Особенности Windows (кириллица в пути, кодировка `.env`) —
[docs/ui_guide.md](docs/ui_guide.md).

### Запуск веб-интерфейса

```powershell
# терминал 1: API графа
.venv\Scripts\langgraph.exe dev --port 2024 --no-browser

# терминал 2: интерфейс
Copy-Item ui\.env.local.example ui\.env.local
npm --prefix ui install
npm --prefix ui run dev
```

Откройте `http://localhost:3000` (не LangGraph Studio). Настройки,
прокси, публичная ссылка с паролем — [docs/ui_guide.md](docs/ui_guide.md)
и [docs/share_ui.md](docs/share_ui.md).

### CLI агентов

Нужен `OPENAI_API_KEY` в `.env` и построенный индекс.

```powershell
.venv\Scripts\python.exe scripts\run_analytics.py --question "Сколько завершённых проверок по ипотеке в 2026 году?"
.venv\Scripts\python.exe scripts\run_retrieval.py --question "Что сказано про просроченную оценку залога?"
.venv\Scripts\python.exe scripts\run_report.py --question "Сформируй раздел акта по AUD-2026-MORTGAGE-03"
.venv\Scripts\python.exe scripts\run_investigation.py --question "Почему в ипотеке в 2026 году выросла доля просроченных пунктов?"
.venv\Scripts\python.exe scripts\run_chat.py --auditor-id AUD-001 --thread-id demo-001
```

## Примеры

| Запрос | Маршрут | Что делает система |
|---|---|---|
| «Сколько завершённых проверок по ипотеке в 2026 году?» | `analytics` | read-only SQL, запрос и результат с evidence |
| «Найди отклонения по AUD-2026-MORTGAGE-03 и похожие формулировки в других актах» | `analytics` | два инструмента в одном вызове |
| «Найди отклонения про просроченную актуализацию оценки залога» | `retrieval` | гибридный поиск, цитаты, критик |
| «Сформируй проект раздела акта по AUD-2026-MORTGAGE-03» | `report` | факты из БД → черновик → Inspector |
| «Почему в ипотеке в 2026 году выросла доля просроченных пунктов?» | `investigation` | два ACL-раунда, факт vs гипотеза |
| «Я проверяю ипотеку, акт нужен в кратком формате» | `memory` | профиль сохраняется для следующих отчётов |
| «Какой у меня профиль?» / «Забудь мой профиль» | `memory` | просмотр и сброс в Настройках → Данные |
| «Удали все пункты из базы» | `unsafe` | guardrail отказывает |

## Проверки

```powershell
.venv\Scripts\python.exe -m pytest -q            # тесты
.venv\Scripts\python.exe scripts\qa_checks.py    # качество данных
openspec validate --specs --strict               # спецификации
npm --prefix ui run lint                         # UI
npm --prefix ui run build
```

Оценка качества: `scripts/evaluate.py` (26 кейсов) и `scripts/benchmark.py`
(51 кейс / 67 реплик, процессные метрики). Оба поддерживают `--dry-run`
без LLM; живой прогон расходует лимит free-тарифа. Метрики и результаты
прогонов — [docs/metrics.md](docs/metrics.md),
[docs/benchmark.md](docs/benchmark.md). Проверка чистого клона
(`scripts/verify_clean_clone.py`) и чек-лист перед сдачей —
[docs/qa.md](docs/qa.md).

## Структура

```text
src/graph/        основной граф и подагенты (analytics, retrieval, report, investigation)
src/acl.py        FIPA-ACL-протокол и журнал сообщений
src/tools/        sql_guard, доступ к БД, инструменты
src/semantic/     каталог метрик и измерений (Query IR)
src/query/        QueryPlan и детерминированный SQL-компилятор
src/capabilities/ typed templates и deterministic matcher
src/rag/          индекс и гибридный поиск
db/migrations/    миграции PostgreSQL 001–007
scripts/          генерация данных, БД, индекс, CLI агентов, оценка, QA
data/knowledge/   методические документы для RAG
data/*.jsonl      наборы оценки и бенчмарка
ui/               assistant-ui (Next.js)
openspec/specs/   спецификации поведения (источник истины)
docs/             документация
tests/            pytest
```

## Технологии

- **Backend:** Python 3.12, LangGraph 1.2, Pydantic 2, NeuralDeep
  (OpenAI-совместимый: `qwen3.6-35b-a3b-noreason`, эмбеддинги `frida`).
- **Данные:** PostgreSQL 16 (`pgserver`), pgvector, FTS `russian`,
  psycopg 3, sqlglot.
- **Frontend:** Next.js 16, React 19, assistant-ui, TypeScript,
  Tailwind CSS 4.
- **Качество:** pytest, OpenSpec, evaluate/benchmark с телеметрией.

## Ограничения и безопасность

- **Синтетические данные.** Не подключайте реальные банковские данные
  и персональную информацию. Состав набора — [docs/data.md](docs/data.md).
- **SQL.** Только read-only `SELECT` по allowlist, роль `audit_ro`,
  `statement_timeout` 5 с, принудительный `LIMIT`.
- **Память краткосрочная.** `thread_id` + история в PostgreSQL + профиль
  аудитора; долговременной семантической памяти нет. `InMemorySaver`
  не переживает перезапуск backend, контекст восстанавливается из БД.
- **Секреты** только на backend; `.env` и `ui/.env.local` не коммитятся.
- **Демо-доступ.** Публичный туннель — только с паролем; `auditor_id`
  в UI — не аутентификация. `pgserver` — не production.
- **Задержки и лимиты.** Ответ может идти 20–70 с; Cloudflare-туннель
  обрывает запрос на 100 с. Free-тариф LLM: 400 запросов / 3 часа.

## Скринкаст

Сценарий на 10 минут — [docs/screencast_script.md](docs/screencast_script.md).
Ссылка на видео добавляется сюда после записи; видео не коммитится.

## Документация

| Документ | О чём |
|---|---|
| [architecture.md](docs/architecture.md) | архитектура агента: диаграммы графов, ACL, память, как проходит вопрос |
| [query_ir.md](docs/query_ir.md) | семантический каталог и компилятор SQL |
| [sql_safety.md](docs/sql_safety.md) | правила SQL-guard |
| [data.md](docs/data.md) | синтетический набор: состав, инварианты, ловушки |
| [ui_guide.md](docs/ui_guide.md) | интерфейс: запуск, настройки, прокси, Windows |
| [share_ui.md](docs/share_ui.md) | публичная ссылка: туннели, пароль, Cloudflare Access |
| [metrics.md](docs/metrics.md) | метрики и прогоны evaluate.py |
| [benchmark.md](docs/benchmark.md) | бенчмарк: уровни, процессные метрики, результаты |
| [improvement_loop.md](docs/improvement_loop.md) | цикл доработки по бенчмарку |
| [qa.md](docs/qa.md) | чистый клон, OpenSpec, чек-лист сдачи |
| [screencast_script.md](docs/screencast_script.md) | сценарий демонстрации |
