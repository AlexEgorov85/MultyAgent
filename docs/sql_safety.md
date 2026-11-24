# Безопасность SQL

## Слои защиты

1. **Промпт** — только `SELECT`, только схема `audit`, не более 200 строк.
2. **sqlglot** — ровно один statement; корень `SELECT`; запрет DDL/DML,
   `COPY`, `CALL`, `DO`, `SELECT INTO`, `FOR UPDATE`.
3. **Allowlist** — схемы `audit`, таблицы и views проекта.
4. **Опасные функции** — `pg_read_file`, `pg_sleep`, `dblink`, `lo_import` и др.
5. **LIMIT** — добавляется автоматически, превышение урезается; если
   сработал `MAX_ROWS`, Analytics добавляет в ответ пометку об ограничении.
6. **Роль `audit_ro`** — только `SELECT`, `default_transaction_read_only`.
7. **Таймаут** — `statement_timeout` (5 секунд).
8. **Финальный guardrail** — повторная проверка SQL перед показом.

## Шаблоны

`script_templates` выполняются с bind-параметрами драйвера
(`%(name)s`), без конкатенации строки, и проходят тот же guard.

## Тесты

`tests/test_sql_guard.py`, `tests/test_tools_db.py`:
`DELETE`, `DROP`, `TRUNCATE`, `COPY ... FROM PROGRAM`, `pg_read_file`,
`pg_sleep`, `information_schema`, `pg_catalog`, чужая схема, `SELECT INTO`,
`FOR UPDATE` — блокируются; корректный `SELECT` проходит.
