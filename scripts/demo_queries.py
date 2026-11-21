"""Демонстрационные read-only запросы к подготовленной базе.

Запуск:
    .venv\\Scripts\\python.exe scripts\\demo_queries.py
    .venv\\Scripts\\python.exe scripts\\demo_queries.py --json reports/demo_queries.json

Скрипт поднимает PostgreSQL, выполняет запросы через тот же sql_guard и
read-only роль, что и агент, и проверяет блокировку опасного SQL.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db_runtime  # noqa: E402
from src.tools import db as db_tools  # noqa: E402
from src.tools.sql_guard import UnsafeSQLError  # noqa: E402

QUERIES = [
    (
        "Роль и база",
        "SELECT current_user AS role, current_database() AS db",
        5,
    ),
    (
        "Проверки по статусам",
        "SELECT status, count(*) AS cnt FROM audit.audits "
        "GROUP BY status ORDER BY cnt DESC",
        10,
    ),
    (
        "Динамика по темам",
        "SELECT theme_code, pocket_year, item_count, critical_count, repeat_count "
        "FROM audit.v_theme_year_dynamics ORDER BY theme_code, pocket_year",
        12,
    ),
    (
        "Просроченные пункты",
        "SELECT item_id, title, risk_level, deadline "
        "FROM audit.v_open_items WHERE is_overdue "
        "ORDER BY days_overdue DESC",
        5,
    ),
    (
        "Топ отклонений",
        "SELECT title, count(*) AS cnt FROM audit.act_items "
        "WHERE item_type = 'отклонение' GROUP BY title ORDER BY cnt DESC",
        5,
    ),
]


def _print_table(title: str, result: dict) -> None:
    print(f"\n=== {title} ===")
    print(f"SQL: {result['sql']}")
    if not result["rows"]:
        print("(нет строк)")
        return
    columns = result["columns"]
    print(" | ".join(columns))
    for row in result["rows"]:
        print(" | ".join(str(row[column]) for column in columns))
    print(f"строк: {result['row_count']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Демонстрационные запросы")
    parser.add_argument("--json", type=Path, help="сохранить результаты в JSON")
    args = parser.parse_args()

    server = db_runtime.start_server()
    payload: dict = {"queries": [], "templates": [], "unsafe": None}
    try:
        for title, sql, limit in QUERIES:
            result = db_tools.run_readonly_sql(server, sql, max_rows=limit)
            _print_table(title, result)
            payload["queries"].append({"title": title, **result})

        template = db_tools.run_script_template(
            server, "risk_by_pocket", {}, max_rows=12
        )
        _print_table("Готовый шаблон: риски по карманам", template)
        payload["template"] = template
        payload["templates"] = [
            item["template_key"] for item in db_tools.list_script_templates(server)
        ]

        try:
            db_tools.run_readonly_sql(server, "DELETE FROM audit.acts")
            payload["unsafe"] = "НЕ ЗАБЛОКИРОВАНО"
            print("\n[FAIL] DELETE не заблокирован")
        except UnsafeSQLError as exc:
            payload["unsafe"] = f"заблокировано: {exc}"
            print(f"\n[OK] DELETE заблокирован: {exc}")
    finally:
        server.cleanup()

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\nJSON: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
