"""Оценка качества и эффективности по фиксированному набору кейсов.

Запуск:
    .venv\\Scripts\\python.exe scripts\\evaluate.py --dry-run
    .venv\\Scripts\\python.exe scripts\\evaluate.py --limit 5
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db_runtime  # noqa: E402
from src.graph.main_graph import build_main_graph  # noqa: E402
from src.llm import OpenAILLM  # noqa: E402
from src.metrics import mean, percentile  # noqa: E402
from src.rag.embeddings import OpenAIEmbeddings  # noqa: E402
from src.tools.sql_guard import UnsafeSQLError, validate_readonly_sql  # noqa: E402

CASES_PATH = ROOT / "data" / "test_cases.jsonl"
REPORTS_DIR = ROOT / "reports"


def load_cases() -> list[dict[str, Any]]:
    cases = []
    with CASES_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def validate_cases(cases: list[dict[str, Any]]) -> list[str]:
    errors = []
    seen = set()
    for case in cases:
        for field in ("id", "auditor_id", "query", "expected_route"):
            if not case.get(field):
                errors.append(f"{case.get('id', '?')}: нет поля {field}")
        if case.get("id") in seen:
            errors.append(f"дубликат id: {case.get('id')}")
        seen.add(case.get("id"))
    return errors


def _evidence(result: dict[str, Any]) -> list[dict[str, Any]]:
    content = result.get("acl_response", {}).get("content", {})
    return content.get("evidence", []) or result.get("evidence", [])


def run_case(graph, case: dict[str, Any]) -> dict[str, Any]:
    thread = f"eval-{case['id']}"
    started = time.perf_counter()
    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": case["query"]}],
            "auditor_id": case["auditor_id"],
            "conversation_id": thread,
        },
        config={"configurable": {"thread_id": thread}},
    )
    latency = time.perf_counter() - started

    route = result.get("route", "")
    answer = result.get("final_answer", "") or ""
    content = result.get("acl_response", {}).get("content", {}) or {}
    sql = content.get("sql")
    evidence = _evidence(result)

    route_ok = route == case["expected_route"]
    include_ok = all(str(item).lower() in answer.lower() for item in case.get("must_include", []))
    exclude_ok = all(
        str(item).lower() not in answer.lower()
        for item in case.get("must_not_include", [])
    )

    sql_ok = True
    if sql:
        try:
            validate_readonly_sql(sql)
        except UnsafeSQLError:
            sql_ok = False

    expected_tools = case.get("expected_tools", [])
    tool_count = int(content.get("metrics", {}).get("tool_calls", 0))
    tools_ok = True
    if len(expected_tools) >= 2:
        tools_ok = tool_count >= 2 or len(evidence) >= 2

    evidence_ok = bool(evidence) if case["expected_route"] in (
        "analytics",
        "retrieval",
        "report",
        "investigation",
    ) else True

    return {
        "id": case["id"],
        "route": route,
        "expected_route": case["expected_route"],
        "route_ok": route_ok,
        "answer": answer.replace("\n", " ")[:300],
        "include_ok": include_ok,
        "exclude_ok": exclude_ok,
        "sql_ok": sql_ok,
        "tools_ok": tools_ok,
        "evidence_ok": evidence_ok,
        "success": route_ok and include_ok and exclude_ok and sql_ok and tools_ok and evidence_ok,
        "latency_sec": round(latency, 3),
        "llm_calls": int(content.get("metrics", {}).get("llm_calls", 0)),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    total = len(rows) or 1
    latencies = [row["latency_sec"] for row in rows]
    return {
        "cases": len(rows),
        "route_accuracy": sum(row["route_ok"] for row in rows) / total,
        "success_rate": sum(row["success"] for row in rows) / total,
        "sql_validity_rate": sum(row["sql_ok"] for row in rows) / total,
        "evidence_coverage": sum(row["evidence_ok"] for row in rows) / total,
        "latency_mean_sec": mean(latencies),
        "latency_p50_sec": percentile(latencies, 0.5),
        "latency_p95_sec": percentile(latencies, 0.95),
    }


def write_reports(rows: list[dict[str, Any]], summary: dict[str, float]) -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    csv_path = REPORTS_DIR / "metrics.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    md_path = REPORTS_DIR / "metrics.md"
    lines = [
        "# Метрики оценки",
        "",
        "| Метрика | Значение |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        if isinstance(value, float) and key != "cases":
            lines.append(f"| `{key}` | {value:.3f} |")
        else:
            lines.append(f"| `{key}` | {value} |")
    lines += ["", "## Кейсы", "", "| ID | Маршрут | Успех | SQL | Evidence | Latency |", "|---|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['route']} | "
            f"{'✅' if row['success'] else '❌'} | "
            f"{'✅' if row['sql_ok'] else '❌'} | "
            f"{'✅' if row['evidence_ok'] else '❌'} | "
            f"{row['latency_sec']} |"
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Оценка ассистента")
    parser.add_argument("--dry-run", action="store_true", help="только проверить кейсы")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", nargs="*", default=[], help="ID конкретных кейсов")
    args = parser.parse_args()

    cases = load_cases()
    errors = validate_cases(cases)
    if errors:
        print("[error] проблемы в тест-наборе:")
        for error in errors:
            print(" -", error)
        return 2

    if args.dry_run:
        routes: dict[str, int] = {}
        for case in cases:
            routes[case["expected_route"]] = routes.get(case["expected_route"], 0) + 1
        print(f"[ok] кейсов: {len(cases)}")
        for route, count in sorted(routes.items()):
            print(f"  {route}: {count}")
        return 0

    selected = cases
    if args.only:
        selected = [case for case in cases if case["id"] in args.only]
    elif args.limit:
        selected = cases[: args.limit]
    server = db_runtime.start_server()
    try:
        llm = OpenAILLM()
        embeddings = OpenAIEmbeddings()
        graph = build_main_graph(server, llm, embeddings=embeddings)
        rows = []
        for case in selected:
            row = run_case(graph, case)
            rows.append(row)
            print(
                f"[{'OK  ' if row['success'] else 'FAIL'}] {row['id']}: "
                f"route={row['route']} latency={row['latency_sec']}s"
            )
    finally:
        server.cleanup()

    summary = summarize(rows)
    write_reports(rows, summary)
    print("\nИтог:")
    for key, value in summary.items():
        print(f"  {key}: {value:.3f}" if isinstance(value, float) else f"  {key}: {value}")
    print(f"\nОтчёты: {REPORTS_DIR / 'metrics.csv'}, {REPORTS_DIR / 'metrics.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
