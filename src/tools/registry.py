"""Реестр инструментов, доступных агенту."""

from __future__ import annotations

from typing import Any

from . import db as db_tools

TOOL_SPECS = """
- get_audit(audit_code: str) — проверка, карман, руководитель и акт.
- get_act(audit_code: str) — акт: статус, summary, full_text.
- get_act_items(audit_code: str, item_type?: str, risk_level?: str,
  status?: str, limit?: int) — пункты проверки.
- search_acts(query: str, limit?: int) — полнотекстовый поиск по актам.
- get_pocket(pocket_id: str) — карман и его показатели.
- list_script_templates() — готовые SQL-шаблоны.
- run_readonly_sql(sql: str, max_rows?: int) — безопасный SELECT.
""".strip()

ALLOWED_TOOLS = {
    "get_audit",
    "get_act",
    "get_act_items",
    "search_acts",
    "get_pocket",
    "list_script_templates",
    "run_readonly_sql",
}


class ToolExecutionError(RuntimeError):
    """Инструмент вызван с неверными аргументами или упал."""


def execute_tool(server, name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Выполняет инструмент по имени. Аргументы проверяются по сигнатуре."""
    args = dict(arguments or {})
    if name not in ALLOWED_TOOLS:
        raise ToolExecutionError(f"Инструмент не разрешён: {name}")

    if name == "get_audit":
        return db_tools.get_audit(server, args["audit_code"])
    if name == "get_act":
        return db_tools.get_act(server, args["audit_code"])
    if name == "get_act_items":
        return db_tools.get_act_items(
            server,
            args["audit_code"],
            item_type=args.get("item_type"),
            risk_level=args.get("risk_level"),
            status=args.get("status"),
            limit=int(args.get("limit", 50)),
        )
    if name == "search_acts":
        return db_tools.search_acts(
            server, args["query"], limit=int(args.get("limit", 5))
        )
    if name == "get_pocket":
        return db_tools.get_pocket(server, args["pocket_id"])
    if name == "list_script_templates":
        return db_tools.list_script_templates(server)
    if name == "run_readonly_sql":
        return db_tools.run_readonly_sql(
            server,
            args["sql"],
            max_rows=int(args.get("max_rows", 200)),
        )
    raise ToolExecutionError(f"Инструмент не реализован: {name}")
