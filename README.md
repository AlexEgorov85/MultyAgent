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
| PostgreSQL + миграции | ✅ `db/migrations/001–003` |
| Генератор данных | ✅ детерминированный, `random.Random(42)` |
| QA-проверки данных | ✅ `scripts/qa_checks.py` (требует усиления по спецификации) |
| LangGraph-агенты | ⏳ следующий этап |
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
- **95 проверок**, **80 актов**, **581 пункт**, **826 скриптов**,
  **826 запусков**, **2 387 отклонений** — промежуточный baseline seed 42.
- Находки двух типов: `отклонение` (количественное, есть скрипт и `rows_found > 0`)
  и `проблема` (качественная, скрипт может отсутствовать).
- 12–15% пунктов 2026 года — повторные находки со ссылкой на пункт 2025 года.
- Ловушки для демонстрации: отменённая проверка без акта, акт на согласовании,
  пункт без скрипта, просроченный открытый пункт, запуск со статусом `ошибка`,
  трёхуровневый номер пункта (`5.2.1`).

Текущий baseline **не является финальной приёмкой**: по спецификации
`data-generation` ещё нужно устранить пересечения расписания и неразличимые
дубли находок, затем перегенерировать набор и обновить manifest.

**Языковая политика:** предметные и пользовательские значения в БД — на русском.
Технические идентификаторы (`PKT-2025-MORTGAGE`, `AUD-2026-CARDS-03`), email,
SQL и код скриптов — латиницей и не выдаются за пользовательские подписи.

## Быстрый старт

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
.venv\Scripts\python.exe scripts\init_db.py --reset --seed
.venv\Scripts\python.exe scripts\qa_checks.py
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
db/migrations/          001_extensions.sql, 002_schema.sql, 003_views.sql
scripts/generate_data.py  детерминированная генерация CSV и методичек
scripts/init_db.py        pgserver, миграции, read-only роль, загрузка CSV
scripts/qa_checks.py      проверки качества данных
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
