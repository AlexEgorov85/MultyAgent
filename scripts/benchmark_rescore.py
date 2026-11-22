"""Пересчитывает benchmark.json после исправления самого бенчмарка.

Пример:
    .venv\\Scripts\\python.exe scripts\\benchmark_rescore.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark import load_cases, rescore_report, write_reports  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Пересчёт benchmark.json")
    parser.add_argument(
        "--report",
        default=str(ROOT / "reports" / "benchmark.json"),
        help="исходный benchmark.json",
    )
    parser.add_argument(
        "--cases",
        default=str(ROOT / "data" / "benchmark_cases.jsonl"),
        help="набор кейсов",
    )
    parser.add_argument(
        "--report-dir",
        default=str(ROOT / "reports"),
        help="куда писать исправленные отчёты",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="сохранить исходный benchmark.json как benchmark_unresolved.json",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"[error] нет файла {report_path}", file=sys.stderr)
        return 2
    if args.backup:
        shutil.copy2(report_path, report_path.with_name("benchmark_unresolved.json"))

    report = json.loads(report_path.read_text(encoding="utf-8"))
    cases = load_cases(args.cases)
    rescored = rescore_report(report, cases)
    paths = write_reports(
        rescored["turns"],
        rescored["summary"],
        cases,
        args.report_dir,
        environment=rescored.get("environment") or {},
    )
    print(
        f"[ok] answer_success_rate={rescored['summary'].get('answer_success_rate', 0):.3f}, "
        f"success_rate={rescored['summary'].get('success_rate', 0):.3f}"
    )
    print(f"Отчёты: {paths['csv']}, {paths['json']}, {paths['md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
