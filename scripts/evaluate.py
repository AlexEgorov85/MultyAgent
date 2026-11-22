"""Оценка качества и эффективности по фиксированному набору кейсов.

Запуск:
    .venv\\Scripts\\python.exe scripts\\evaluate.py --dry-run
    .venv\\Scripts\\python.exe scripts\\evaluate.py --limit 5
    .venv\\Scripts\\python.exe scripts\\evaluate.py --repeat 3

`--repeat N` выполняет каждый выбранный кейс N раз (независимые прогоны,
у каждого свой thread_id) и публикует mean/std метрик по прогонам. Это нужно
для оценки разброса при temperature 0: один прогон не показывает
нестабильность маршрутизации и латентности.

ВНИМАНИЕ: каждый повторный прогон — это реальные вызовы LLM и потраченный
лимит токенов. `--repeat 3` утраивает расход относительно обычного запуска,
`--dry-run` ничего не запускает и лимит не расходует.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
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


def run_case(graph, case: dict[str, Any], repeat: int = 1) -> dict[str, Any]:
    """Один прогон кейса. `repeat` — номер прогона (1..N) для агрегации."""
    thread = f"eval-{case['id']}"
    if repeat > 1:
        # Независимые повторы: разный thread_id, чтобы не тянуть историю
        # предыдущего прогона из памяти диалога.
        thread = f"{thread}-r{repeat}"
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
        "repeat": repeat,
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


def stddev(values: list[float]) -> float:
    """Population standard deviation (делитель N, ddof=0).

    Для пустого списка и одного значения возвращает 0.0.
    """
    data = [float(value) for value in values]
    if len(data) < 2:
        return 0.0
    avg = mean(data)
    return math.sqrt(sum((value - avg) ** 2 for value in data) / len(data))


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Сводка по всем строкам без учёта повторов (pooled).

    Набор ключей сохранён прежним: cases, route_accuracy, success_rate,
    sql_validity_rate, evidence_coverage, latency_mean_sec,
    latency_p50_sec, latency_p95_sec.
    """
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


def summarize_repeats(rows: list[dict[str, Any]], repeat: int = 1) -> dict[str, float]:
    """Сводка с учётом повторных прогонов.

    При `repeat <= 1` возвращает `summarize(rows)` без изменений — формат
    метрик обратно совместим.

    При `repeat > 1` строки группируются по полю `repeat` (номер прогона),
    для каждого прогона считается `summarize`, затем по прогонам публикуются:

    * `<metric>_mean` / `<metric>_std` для success_rate, route_accuracy,
      sql_validity_rate, evidence_coverage;
    * `latency_mean_sec` — среднее по средним латентностям прогонов,
      `latency_mean_sec_std` — std этих средних;
    * `latency_p50_sec` / `latency_p95_sec` — по всем строкам (pooled).

    std — population (делитель N, ddof=0), где N — число прогонов. Если
    прогонов меньше двух, std = 0.0. Дополнительно возвращаются `cases`
    (число уникальных кейсов), `repeat` (число прогонов) и `rows`
    (общее число строк).
    """
    if repeat <= 1:
        return summarize(rows)

    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        run_no = int(row.get("repeat", 1))
        grouped.setdefault(run_no, []).append(row)
    per_run = [summarize(grouped[run_no]) for run_no in sorted(grouped)]

    pooled = summarize(rows)
    summary: dict[str, float] = {
        "cases": len({row["id"] for row in rows}),
        "repeat": repeat,
        "rows": len(rows),
    }
    for metric in (
        "success_rate",
        "route_accuracy",
        "sql_validity_rate",
        "evidence_coverage",
    ):
        values = [run[metric] for run in per_run]
        summary[f"{metric}_mean"] = mean(values)
        summary[f"{metric}_std"] = stddev(values)

    latency_means = [run["latency_mean_sec"] for run in per_run]
    summary["latency_mean_sec"] = mean(latency_means)
    summary["latency_mean_sec_std"] = stddev(latency_means)
    summary["latency_p50_sec"] = pooled["latency_p50_sec"]
    summary["latency_p95_sec"] = pooled["latency_p95_sec"]
    return summary


def _summary_label(key: str, repeat: int) -> str:
    """Понятное имя метрики для metrics.md (mean/std подписываются)."""
    if repeat <= 1:
        return key
    if key == "latency_mean_sec":
        return "latency_mean_sec (mean по прогонам)"
    if key.endswith("_mean"):
        return f"{key[: -len('_mean')]} (mean)"
    if key.endswith("_std"):
        return f"{key[: -len('_std')]} (std)"
    return key


def write_reports(rows: list[dict[str, Any]], summary: dict[str, float]) -> None:
    """Пишет metrics.csv (построчно, с полем repeat) и metrics.md."""
    repeat = int(summary.get("repeat", 1) or 1)
    REPORTS_DIR.mkdir(exist_ok=True)
    csv_path = REPORTS_DIR / "metrics.csv"
    fieldnames = list(rows[0].keys())
    if "repeat" not in fieldnames:
        fieldnames.insert(1, "repeat")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "repeat": row.get("repeat", 1)})

    md_path = REPORTS_DIR / "metrics.md"
    lines = [
        "# Метрики оценки",
        "",
    ]
    if repeat > 1:
        lines += [
            f"Повторных прогонов на кейс: {repeat}. "
            f"std — population (делитель N={repeat}).",
            "",
        ]
    lines += [
        "| Метрика | Значение |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        label = _summary_label(key, repeat)
        if isinstance(value, float) and key != "cases":
            lines.append(f"| `{label}` | {value:.3f} |")
        else:
            lines.append(f"| `{label}` | {value} |")

    lines += ["", "## Кейсы", ""]
    if repeat > 1:
        lines += [
            "| ID | Прогон | Маршрут | Успех | SQL | Evidence | Latency |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for row in rows:
            lines.append(
                f"| {row['id']} | {row.get('repeat', 1)} | {row['route']} | "
                f"{'✅' if row['success'] else '❌'} | "
                f"{'✅' if row['sql_ok'] else '❌'} | "
                f"{'✅' if row['evidence_ok'] else '❌'} | "
                f"{row['latency_sec']} |"
            )
    else:
        lines += [
            "| ID | Маршрут | Успех | SQL | Evidence | Latency |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for row in rows:
            lines.append(
                f"| {row['id']} | {row['route']} | "
                f"{'✅' if row['success'] else '❌'} | "
                f"{'✅' if row['sql_ok'] else '❌'} | "
                f"{'✅' if row['evidence_ok'] else '❌'} | "
                f"{row['latency_sec']} |"
            )
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Оценка ассистента")
    parser.add_argument("--dry-run", action="store_true", help="только проверить кейсы")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", nargs="*", default=[], help="ID конкретных кейсов")
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="сколько раз выполнить каждый кейс (>=1); расходует лимит LLM",
    )
    args = parser.parse_args(argv)

    if args.repeat < 1:
        parser.error("--repeat должен быть >= 1")

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
        if args.repeat > 1:
            print(
                f"  прогонов на кейс: {args.repeat}, "
                f"всего запусков: {len(cases) * args.repeat}"
            )
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
        for repeat_no in range(1, args.repeat + 1):
            for case in selected:
                row = run_case(graph, case, repeat=repeat_no)
                rows.append(row)
                label = row["id"]
                if args.repeat > 1:
                    label = f"{label} [прогон {repeat_no}/{args.repeat}]"
                print(
                    f"[{'OK  ' if row['success'] else 'FAIL'}] {label}: "
                    f"route={row['route']} latency={row['latency_sec']}s"
                )
    finally:
        server.cleanup()

    summary = summarize_repeats(rows, args.repeat)
    write_reports(rows, summary)
    print("\nИтог:")
    if args.repeat > 1:
        print(
            f"  success_rate: {summary['success_rate_mean']:.3f} "
            f"± {summary['success_rate_std']:.3f}"
        )
        print(
            f"  latency_mean_sec: {summary['latency_mean_sec']:.3f} "
            f"± {summary['latency_mean_sec_std']:.3f} s"
        )
        for key, value in summary.items():
            if key in {
                "success_rate_mean",
                "success_rate_std",
                "latency_mean_sec",
                "latency_mean_sec_std",
            }:
                continue
            print(f"  {key}: {value:.3f}" if isinstance(value, float) else f"  {key}: {value}")
    else:
        for key, value in summary.items():
            print(f"  {key}: {value:.3f}" if isinstance(value, float) else f"  {key}: {value}")
    print(f"\nОтчёты: {REPORTS_DIR / 'metrics.csv'}, {REPORTS_DIR / 'metrics.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
