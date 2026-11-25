"""Выполнение read-only SQL и готовых шаблонов."""

from __future__ import annotations

from typing import Any, Mapping

from .. import config, db_runtime, telemetry
from .sql_guard import validate_readonly_sql, validate_readonly_sql_with_limit

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
audit.script_runs(run_id, script_id, run_at, status, rows_found, duration_ms,
  result_sample, error_message)
audit.deviations(deviation_id, item_id, script_id, entity_type, entity_id,
  detected_at, metric_name, metric_value, threshold_value, severity,
  description, payload)
audit.script_templates(template_id, template_key, title, description,
  sql_template, parameters, max_rows_default)
audit.auditors(auditor_id, full_name, unit, position, specializations)
audit.auditor_memory(auditor_id, memory_key, memory_value, updated_at)
audit.knowledge_chunks(chunk_id, source_type, source_id, title, content)
audit.dataset_metadata(metadata_id, as_of_date, seed, checksum)

Views with columns:
- audit.v_pocket_summary(pocket_id, pocket_year, theme_code, title, risk_level,
  planned_audit_count, audit_count, act_count, item_count, deviation_count,
  problem_count, critical_count, open_count, overdue_count)
- audit.v_audit_summary(audit_id, audit_code, title, status, audit_type,
  start_date, end_date, risk_level, pocket_id, pocket_year, theme_code,
  pocket_title, lead_auditor, act_id, act_number, act_status, act_date,
  item_count, deviation_count, problem_count, open_count)
- audit.v_act_item_details(item_id, item_number, item_type, test_type, title,
  test_description, condition, cause, effect, recommendation, risk_level,
  status, deadline, closed_at, is_repeat, repeat_of_item_id, act_id,
  act_number, act_date, audit_id, audit_code, audit_title, pocket_id,
  pocket_year, theme_code, script_count, rows_found_total, sql_script_count)
- audit.v_open_items(item_id, item_number, title, item_type, risk_level, status,
  deadline, act_number, audit_code, theme_code, is_overdue, days_overdue)
- audit.v_repeat_items(item_id, item_number, title, risk_level, status,
  repeat_of_item_id, previous_title, previous_number, act_number,
  previous_act_number, theme_code, pocket_year)
- audit.v_script_usage(language, script_count, scripts_with_findings,
  rows_found_total, rows_found_avg, execution_ms_avg)
- audit.v_theme_year_dynamics(theme_code, pocket_year, item_count,
  deviation_count, problem_count, critical_count, repeat_count, closed_count)
- audit.v_items_without_scripts(item_id, item_number, title, item_type,
  test_type, risk_level, status, act_number, audit_code)

Enum values:
- theme_code: ипотека, потребкредитование, платежи, карты, вклады
- risk_level: низкий, средний, высокий, критический
- audit_status: запланирована, в работе, завершена, отменена
- act_status: черновик, на согласовании, утверждён
- item_type: отклонение, проблема
- item_status: открыт, в работе, закрыт
- test_type: непрерывный, выборочный, аналитический, повторное выполнение, опрос
- script_run_status: успешно, частично, ошибка
- script_language: SQL, Python, R, Excel, Другое
- entity_type отклонения: договор, транзакция, карта, счёт

Связи (используй только их):
- audit.audits.audit_id → audit.acts.audit_id
- audit.acts.act_id → audit.act_items.act_id
- audit.act_items.item_id → audit.scripts.item_id
- audit.scripts.script_id → audit.script_runs.script_id
- audit.act_items.item_id → audit.deviations.item_id
- audit.audits.pocket_id → audit.audit_pockets.pocket_id
- audit.audits.lead_auditor_id → audit.auditors.auditor_id
- У audit.act_items нет audit_id: связь с проверкой только через audit.acts.

Domain terms:
- «карман» — это audit.audit_pockets (год + тема). «По годам и карманам» —
  GROUP BY pocket_year, theme_code (или pocket_id), без фильтра по теме,
  если тема не названа явно.
- «закрытая проверка» — audit.audits.status = 'завершена'.
- «закрытый пункт» — audit.act_items.status = 'закрыт'.
- «просроченный пункт» — status <> 'закрыт' и deadline < as_of_date
  (audit.dataset_metadata.as_of_date или audit.as_of_date()).
- «пункт без скрипта/доказательства» — нет строки в audit.scripts по item_id.
- «повторная находка» — audit.act_items.is_repeat = true.
- «черновик», «на согласовании», «утверждён» — статусы акта.
- «скрипт с ошибкой» — audit.script_runs.status = 'ошибка'.
- «критическое отклонение» — audit.deviations.severity = 'критический'.
- Не использовать CURRENT_DATE: дата среза задана в audit.dataset_metadata.as_of_date
  и доступна через audit.as_of_date().
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


@telemetry.timed_tool("get_pocket")
def get_pocket(server, pocket_id: str) -> dict[str, Any] | None:
    """Возвращает карман аудита по id или None, если его нет."""
    rows = _select(
        server,
        "SELECT pocket_id, pocket_year, theme_code, title, owner_unit, "
        "planned_audit_count, risk_level, period_start, period_end "
        "FROM audit.audit_pockets WHERE pocket_id = %s",
        (pocket_id,),
    )
    return rows[0] if rows else None


@telemetry.timed_tool("get_audit")
def get_audit(server, audit_code: str) -> dict[str, Any] | None:
    """Возвращает проверку с карманом, руководителем и актом по коду."""
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


@telemetry.timed_tool("get_act")
def get_act(server, audit_code: str) -> dict[str, Any] | None:
    """Возвращает акт проверки по коду проверки или None."""
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


@telemetry.timed_tool("get_act_items")
def get_act_items(
    server,
    audit_code: str,
    item_type: str | None = None,
    risk_level: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Возвращает пункты акта с необязательными фильтрами по типу/риску/статусу."""
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


@telemetry.timed_tool("search_acts")
def search_acts(server, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Полнотекстовый поиск по актам (russian) с релевантными фрагментами."""
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
    safe_sql, limit_added = validate_readonly_sql_with_limit(sql, max_rows)
    timeout_ms = int(config.SQL_TIMEOUT_SEC * 1000)
    metrics = telemetry.current()
    if metrics is not None:
        metrics.incr("sql_queries")

    with db_runtime.connect(server, role=db_runtime.READ_ONLY_ROLE) as conn:
        conn.execute(f"SET statement_timeout = {timeout_ms}")
        if params:
            cursor = conn.execute(safe_sql, dict(params))
        else:
            cursor = conn.execute(safe_sql)
        columns = [item.name for item in (cursor.description or [])]
        rows = cursor.fetchmany(max_rows) if columns else []

    # LIMIT добавлен guard'ом и строк ровно столько же, сколько разрешено:
    # возможно, за границей есть ещё строки. Помечаем консервативно.
    truncated = limit_added and len(rows) >= max_rows
    rows = rows[:max_rows]
    return {
        "sql": safe_sql,
        "columns": columns,
        "rows": [dict(zip(columns, row)) for row in rows],
        "row_count": len(rows),
        "max_rows": max_rows,
        "truncated": truncated,
    }


@telemetry.timed_tool("run_readonly_sql")
def run_readonly_sql(
    server,
    sql: str,
    params: Mapping[str, Any] | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Выполняет проверенный SELECT под ролью audit_ro."""
    cap = int(max_rows if max_rows is not None else config.MAX_ROWS)
    return _execute(server, sql, params, cap)


@telemetry.timed_tool("latest_pocket_year")
def latest_pocket_year(server) -> int:
    """Максимальный год карманов — для периода «последний год»."""
    rows = _select(
        server,
        "SELECT max(pocket_year) AS year FROM audit.audit_pockets",
    )
    value = rows[0]["year"] if rows else None
    return int(value) if value is not None else config.DEFAULT_AS_OF_DATE.year


@telemetry.timed_tool("list_script_templates")
def list_script_templates(server) -> list[dict[str, Any]]:
    """Возвращает активные шаблоны без выполнения."""
    with db_runtime.connect(server, role=db_runtime.READ_ONLY_ROLE) as conn:
        rows = conn.execute(
            "SELECT template_key, title, description, sql_template, parameters, "
            "max_rows_default "
            "FROM audit.script_templates WHERE is_active ORDER BY template_key"
        ).fetchall()
    return [
        {
            "template_key": key,
            "title": title,
            "description": description,
            "sql_template": sql_template,
            "parameters": params,
            "max_rows_default": max_rows,
        }
        for key, title, description, sql_template, params, max_rows in rows
    ]


@telemetry.timed_tool("run_script_template")
def run_script_template(
    server,
    template_key: str,
    params: Mapping[str, Any] | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Выполняет готовый шаблон с bind-параметрами и SQL-guard."""
    with db_runtime.connect(server, role=db_runtime.READ_ONLY_ROLE) as conn:
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
