"""Выполнение read-only SQL и готовых шаблонов."""

from __future__ import annotations

from typing import Any, Mapping

from .. import config, db_runtime
from .sql_guard import validate_readonly_sql

SCHEMA_TEXT = """
audit.audit_pockets(pocket_id, pocket_year, theme_code, title, owner_unit,
  planned_audit_count, risk_level, period_start, period_end)
audit.audits(audit_id, pocket_id, audit_code, title, audit_type, start_date,
  end_date, status, lead_auditor_id, team_size, scope, risk_level)
audit.acts(act_id, audit_id, act_number, act_date, status, approved_by,
  summary, full_text)
audit.act_items(item_id, act_id, item_number, item_type, test_type,
  finding_template_key, finding_scope, title, test_description, criterion,
  condition, cause, effect, recommendation, risk_level, status, deadline,
  responsible_unit, closed_at, is_repeat, repeat_of_item_id)
audit.scripts(script_id, item_id, name, language, code, population_size,
  rows_found, result_summary)
audit.script_templates(template_id, template_key, title, description,
  sql_template, parameters, max_rows_default)
audit.auditors(auditor_id, full_name, unit, position, specializations)

Views: audit.v_pocket_summary, audit.v_audit_summary, audit.v_act_item_details,
audit.v_open_items, audit.v_repeat_items, audit.v_script_usage,
audit.v_theme_year_dynamics, audit.v_items_without_scripts.

Enum values:
- risk_level: низкий, средний, высокий, критический
- audit_status: запланирована, в работе, завершена, отменена
- act_status: черновик, на согласовании, утверждён
- item_type: отклонение, проблема
- item_status: открыт, в работе, закрыт
- test_type: непрерывный, выборочный, аналитический, повторное выполнение, опрос
""".strip()


def get_schema() -> str:
    """Краткое описание схемы для промпта LLM."""
    return SCHEMA_TEXT


def _rows(cursor) -> list[dict[str, Any]]:
    columns = [item.name for item in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _select(server, sql: str, params: Any = None) -> list[dict[str, Any]]:
    with db_runtime.connect(server, role=db_runtime.READ_ONLY_ROLE) as conn:
        if params is None:
            return _rows(conn.execute(sql))
        return _rows(conn.execute(sql, params))


def get_pocket(server, pocket_id: str) -> dict[str, Any] | None:
    rows = _select(
        server,
        "SELECT pocket_id, pocket_year, theme_code, title, owner_unit, "
        "planned_audit_count, risk_level, period_start, period_end "
        "FROM audit.audit_pockets WHERE pocket_id = %s",
        (pocket_id,),
    )
    return rows[0] if rows else None


def get_audit(server, audit_code: str) -> dict[str, Any] | None:
    rows = _select(
        server,
        "SELECT a.audit_id, a.audit_code, a.title, a.audit_type, a.start_date, "
        "a.end_date, a.status, a.risk_level, a.scope, "
        "p.pocket_id, p.title AS pocket_title, p.theme_code, "
        "au.full_name AS lead_auditor, ac.act_id, ac.act_number, "
        "ac.status AS act_status, ac.act_date, ac.summary "
        "FROM audit.audits a "
        "JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id "
        "JOIN audit.auditors au ON au.auditor_id = a.lead_auditor_id "
        "LEFT JOIN audit.acts ac ON ac.audit_id = a.audit_id "
        "WHERE a.audit_code = %s",
        (audit_code,),
    )
    return rows[0] if rows else None


def get_act(server, audit_code: str) -> dict[str, Any] | None:
    rows = _select(
        server,
        "SELECT ac.act_id, ac.act_number, ac.act_date, ac.status, ac.summary, "
        "ac.full_text, a.audit_code "
        "FROM audit.acts ac "
        "JOIN audit.audits a ON a.audit_id = ac.audit_id "
        "WHERE a.audit_code = %s",
        (audit_code,),
    )
    return rows[0] if rows else None


def get_act_items(
    server,
    audit_code: str,
    item_type: str | None = None,
    risk_level: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses = ["a.audit_code = %(audit_code)s"]
    params: dict[str, Any] = {"audit_code": audit_code, "limit": int(limit)}
    if item_type:
        clauses.append("i.item_type = %(item_type)s")
        params["item_type"] = item_type
    if risk_level:
        clauses.append("i.risk_level = %(risk_level)s")
        params["risk_level"] = risk_level
    if status:
        clauses.append("i.status = %(status)s")
        params["status"] = status
    where = " AND ".join(clauses)
    return _select(
        server,
        "SELECT i.item_id, i.item_number, i.item_type, i.test_type, i.title, "
        "i.condition, i.risk_level, i.status, i.deadline, i.is_repeat "
        "FROM audit.act_items i "
        "JOIN audit.acts ac ON ac.act_id = i.act_id "
        "JOIN audit.audits a ON a.audit_id = ac.audit_id "
        f"WHERE {where} ORDER BY i.order_index LIMIT %(limit)s",
        params,
    )


def search_acts(server, query: str, limit: int = 5) -> list[dict[str, Any]]:
    return _select(
        server,
        "SELECT a.audit_code, ac.act_number, ac.act_date, "
        "left(ac.full_text, 400) AS fragment, "
        "ts_rank(to_tsvector('russian', a.title || ' ' || ac.full_text), "
        "        plainto_tsquery('russian', %(query)s)) AS rank "
        "FROM audit.acts ac "
        "JOIN audit.audits a ON a.audit_id = ac.audit_id "
        "WHERE to_tsvector('russian', a.title || ' ' || ac.full_text) "
        "      @@ plainto_tsquery('russian', %(query)s) "
        "ORDER BY rank DESC LIMIT %(limit)s",
        {"query": query, "limit": int(limit)},
    )


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
