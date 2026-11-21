"""Выполнение read-only SQL и готовых шаблонов."""

from __future__ import annotations

from typing import Any, Mapping

from .. import config, db_runtime
from .sql_guard import validate_readonly_sql


class ExecutionError(RuntimeError):
    """Запрос не выполнен или вернул некорректный результат."""


def _execute(
    server,
    sql: str,
    params: Mapping[str, Any] | None,
    max_rows: int,
) -> dict[str, Any]:
    safe_sql = validate_readonly_sql(sql, max_rows)
    timeout_ms = int(config.SQL_TIMEOUT_SEC * 1000)

    with db_runtime.connect(server, role=db_runtime.READ_ONLY_ROLE) as conn:
        conn.execute(f"SET statement_timeout = {timeout_ms}")
        if params:
            cursor = conn.execute(safe_sql, dict(params))
        else:
            cursor = conn.execute(safe_sql)
        columns = [item.name for item in (cursor.description or [])]
        rows = cursor.fetchmany(max_rows) if columns else []

    return {
        "sql": safe_sql,
        "columns": columns,
        "rows": [dict(zip(columns, row)) for row in rows],
        "row_count": len(rows),
        "max_rows": max_rows,
    }


def run_readonly_sql(
    server,
    sql: str,
    params: Mapping[str, Any] | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Выполняет проверенный SELECT под ролью audit_ro."""
    cap = int(max_rows if max_rows is not None else config.MAX_ROWS)
    return _execute(server, sql, params, cap)


def list_script_templates(server) -> list[dict[str, Any]]:
    """Возвращает активные шаблоны без выполнения."""
    with db_runtime.connect(server) as conn:
        rows = conn.execute(
            "SELECT template_key, title, description, parameters, max_rows_default "
            "FROM audit.script_templates WHERE is_active ORDER BY template_key"
        ).fetchall()
    return [
        {
            "template_key": key,
            "title": title,
            "description": description,
            "parameters": params,
            "max_rows_default": max_rows,
        }
        for key, title, description, params, max_rows in rows
    ]


def run_script_template(
    server,
    template_key: str,
    params: Mapping[str, Any] | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Выполняет готовый шаблон с bind-параметрами и SQL-guard."""
    with db_runtime.connect(server) as conn:
        row = conn.execute(
            "SELECT sql_template, parameters, max_rows_default "
            "FROM audit.script_templates "
            "WHERE template_key = %s AND is_active",
            (template_key,),
        ).fetchone()

    if row is None:
        raise ExecutionError(f"Шаблон не найден: {template_key}")

    sql, declared, default_limit = row
    declared = declared or {}
    provided = dict(params or {})

    missing = [name for name in declared if name not in provided]
    unknown = [name for name in provided if name not in declared]
    if missing:
        raise ExecutionError(f"Не хватает параметров: {', '.join(missing)}")
    if unknown:
        raise ExecutionError(f"Неизвестные параметры: {', '.join(unknown)}")

    cap = int(max_rows or default_limit or config.MAX_ROWS)
    return _execute(server, sql, provided, cap)
