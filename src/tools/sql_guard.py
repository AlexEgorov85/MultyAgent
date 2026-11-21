"""Read-only валидация SQL (спецификация sql-safety).

Правила:
- ровно один statement;
- корень — SELECT (включая WITH ... SELECT);
- только схема audit и разрешённые таблицы/views;
- запрещены DDL/DML, COPY/CALL/DO и опасные системные функции;
- принудительный LIMIT.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from .. import config

ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "auditors",
        "audit_pockets",
        "audits",
        "acts",
        "act_items",
        "scripts",
        "script_runs",
        "deviations",
        "script_templates",
        "auditor_memory",
        "knowledge_chunks",
        "dataset_metadata",
        "v_pocket_summary",
        "v_audit_summary",
        "v_act_item_details",
        "v_open_items",
        "v_repeat_items",
        "v_script_usage",
        "v_theme_year_dynamics",
        "v_items_without_scripts",
    }
)

ALLOWED_SCHEMAS: frozenset[str] = frozenset({"audit"})

FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,  # COPY, CALL, DO и другие служебные команды
    exp.Copy,
    exp.Merge,
    exp.TruncateTable,
)

FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset(
    {
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_sleep",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "dblink",
        "lo_import",
        "lo_export",
        "set_config",
    }
)


class UnsafeSQLError(ValueError):
    """SQL не прошёл проверку безопасности."""


def _limit_value(tree: exp.Select) -> int | None:
    limit = tree.args.get("limit")
    if limit is None:
        return None
    expression = limit.expression
    try:
        return int(expression.name)
    except (AttributeError, TypeError, ValueError):
        return None


def validate_readonly_sql(sql: str, max_rows: int | None = None) -> str:
    """Проверяет SQL и возвращает безопасный вариант с LIMIT.

    Raises:
        UnsafeSQLError: если запрос не является одиночным read-only SELECT
            по разрешённой схеме.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise UnsafeSQLError("Пустой SQL-запрос.")

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.ParseError as exc:
        raise UnsafeSQLError(f"Не удалось разобрать SQL: {exc}") from exc

    if len(statements) != 1:
        raise UnsafeSQLError("Разрешён ровно один SQL-запрос.")

    tree = statements[0]
    if not isinstance(tree, exp.Select):
        raise UnsafeSQLError("Разрешён только SELECT.")

    if tree.args.get("into") is not None:
        raise UnsafeSQLError("SELECT INTO запрещён: он создаёт таблицу.")

    if tree.args.get("locks"):
        raise UnsafeSQLError("Блокирующие конструкции (FOR UPDATE/SHARE) запрещены.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}

    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeSQLError(f"Запрещённая операция: {type(node).__name__}")

        if isinstance(node, exp.Table):
            schema = (node.db or "").lower()
            if schema and schema not in ALLOWED_SCHEMAS:
                raise UnsafeSQLError(f"Схема вне allowlist: {schema}")
            table = node.name.lower()
            if table not in ALLOWED_TABLES and table not in cte_names:
                raise UnsafeSQLError(f"Таблица вне allowlist: {table}")

        if isinstance(node, exp.Anonymous):
            name = node.name.lower()
            if name in FORBIDDEN_FUNCTIONS:
                raise UnsafeSQLError(f"Запрещённая функция: {name}")

        if isinstance(node, exp.Func):
            name = getattr(node, "sql_name", lambda: "")().lower()
            if name in FORBIDDEN_FUNCTIONS:
                raise UnsafeSQLError(f"Запрещённая функция: {name}")

    cap = int(max_rows if max_rows is not None else config.MAX_ROWS)
    current = _limit_value(tree)
    if current is None or current > cap:
        tree = tree.limit(cap)

    return tree.sql(dialect="postgres")
