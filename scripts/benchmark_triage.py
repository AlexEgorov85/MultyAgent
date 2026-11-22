"""Строит backlog доработок по результатам benchmark.json.

Пример:
    .venv\\Scripts\\python.exe scripts\\benchmark_triage.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.improvement import (  # noqa: E402
    build_backlog,
    format_backlog_md,
    load_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage провалов бенчмарка")
    parser.add_argument(
        "--report",
        default=str(ROOT / "reports" / "benchmark.json"),
        help="входной benchmark.json",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "reports" / "benchmark_backlog.md"),
        help="Markdown-backlog",
    )
    parser.add_argument(
        "--json-out",
        default=str(ROOT / "reports" / "benchmark_backlog.json"),
        help="JSON-backlog",
    )
    parser.add_argument(
        "--exclude-provider",
        action="store_true",
        help="не включать провалы провайдера/429",
    )
    parser.add_argument("--top", type=int, default=0, help="оставить top-N кластеров")
    args = parser.parse_args()

    path = Path(args.report)
    if not path.exists():
        print(f"[error] нет файла {path}", file=sys.stderr)
        return 2

    report = load_report(path)
    backlog = build_backlog(report, include_provider=not args.exclude_provider)
    if args.top > 0:
        backlog = backlog[: args.top]

    Path(args.out).write_text(
        format_backlog_md(backlog, source=str(path)), encoding="utf-8"
    )
    Path(args.json_out).write_text(
        json.dumps(backlog, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[ok] кластеров: {len(backlog)}")
    for index, item in enumerate(backlog[:10], start=1):
        print(
            f"  {index}. [{item['severity']}] {item['title']}: "
            f"{item['count']} репл., кейсов {len(item['cases'])}"
        )
    print(f"\nОтчёты: {args.out}, {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
