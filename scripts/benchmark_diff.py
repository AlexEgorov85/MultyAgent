"""Сравнивает два benchmark.json и при --gate проверяет regressions.

Пример:
    .venv\\Scripts\\python.exe scripts\\benchmark_diff.py ^
        reports\\benchmark_baseline.json reports\\benchmark.json --gate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.improvement import (  # noqa: E402
    diff_runs,
    evaluate_gate,
    format_diff_md,
    load_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff двух прогонов бенчмарка")
    parser.add_argument("baseline", help="benchmark.json до изменений")
    parser.add_argument("candidate", help="benchmark.json после изменений")
    parser.add_argument(
        "--out",
        default=str(ROOT / "reports" / "benchmark_diff.md"),
        help="Markdown-отчёт",
    )
    parser.add_argument(
        "--json-out",
        default=str(ROOT / "reports" / "benchmark_diff.json"),
        help="JSON-отчёт",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="вернуть код 1, если regression-gate не пройден",
    )
    parser.add_argument("--max-success-drop", type=float, default=0.0)
    parser.add_argument("--max-token-increase", type=float, default=0.10)
    parser.add_argument("--max-latency-increase", type=float, default=0.10)
    parser.add_argument("--max-cost-increase", type=float, default=0.10)
    parser.add_argument("--max-regressions", type=int, default=0)
    args = parser.parse_args()

    for path in (args.baseline, args.candidate):
        if not Path(path).exists():
            print(f"[error] нет файла {path}", file=sys.stderr)
            return 2

    baseline = load_report(args.baseline)
    candidate = load_report(args.candidate)
    diff = diff_runs(baseline, candidate)
    gate = evaluate_gate(
        baseline,
        candidate,
        max_success_drop=args.max_success_drop,
        max_token_increase=args.max_token_increase,
        max_latency_increase=args.max_latency_increase,
        max_cost_increase=args.max_cost_increase,
        max_regressions=args.max_regressions,
    )

    Path(args.out).write_text(
        format_diff_md(diff, gate if args.gate else None), encoding="utf-8"
    )
    Path(args.json_out).write_text(
        json.dumps({"diff": diff, "gate": gate}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"[ok] улучшений: {diff['improvement_count']}, "
        f"регрессий: {diff['regression_count']}"
    )
    if args.gate:
        print(f"[{'PASS' if gate['passed'] else 'FAIL'}] regression-gate")
        for reason in gate["reasons"]:
            print(f"  - не прошло: {reason}")
    print(f"\nОтчёты: {args.out}, {args.json_out}")
    return 0 if not args.gate or gate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
