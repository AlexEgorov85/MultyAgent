"""Генерирует безопасное предложение по доработке агента из benchmark.json.

Скрипт не меняет код и не вызывает LLM. Он выбирает топ-кластер провалов,
собирает гипотезу, файлы, команду проверки и ограничения. Дальше изменение
применяет человек или coding-agent в отдельной ветке/worktree.

Пример:
    .venv\\Scripts\\python.exe scripts\\improve_agent.py --index 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.improvement import build_backlog, load_report  # noqa: E402


def _proposal(item: dict, report: dict) -> str:
    environment = report.get("environment") or {}
    lines = [
        "# Предложение по доработке агента",
        "",
        f"- Категория: **{item['title']}** (`{item['category']}`)",
        f"- Приоритет: **{item['severity']}**, риск: `{item['risk']}`",
        f"- Уровень: `{item['tier'] or '—'}`, маршрут: `{item['route'] or '—'}`",
        f"- Реплик: {item['count']}, кейсов: {len(item['cases'])}",
        f"- Run: `{environment.get('run_id', '—')}`",
        f"- Модель: `{environment.get('model', '—')}`",
        "",
        "## Гипотеза",
        "",
        item["action"],
        "",
        "## Почему бенчмарк считает это проблемой",
        "",
    ]
    if item.get("exclude_from_quality"):
        lines.append(
            "Это провал окружения/провайдера. Сначала устраните лимит или "
            "сетевую ошибку, иначе изменение агента нельзя оценить."
        )
    else:
        lines.append(
            f"Кластер объединяет {item['count']} провальных реплик. "
            "Ожидаемый эффект — рост answer/process success без ухудшения "
            "токенов, latency и стоимости."
        )
    lines += ["", "## Что менять", ""]
    for path in item.get("target_files") or []:
        lines.append(f"- `{path}`")
    if not item.get("target_files"):
        lines.append("- определить по `state` и `trace` вручную")
    lines += ["", "## Кейсы", ""]
    for case in item["cases"]:
        lines.append(f"- `{case}`")
    if item.get("queries"):
        lines += ["", "## Примеры запросов", ""]
        for query in item["queries"]:
            lines.append(f"- {query}")
    if item.get("prompts"):
        lines += ["", "## Затронутые промпты", ""]
        for prompt in item["prompts"]:
            lines.append(f"- `{prompt}`")
    lines += [
        "",
        "## Проверка",
        "",
        "```powershell",
        item["validation"],
        "```",
        "",
        "После целевого прогона сравните baseline и candidate:",
        "",
        "```powershell",
        "Copy-Item reports\\benchmark.json reports\\benchmark_baseline.json",
        "# применить изменение и прогнать benchmark",
        ".venv\\Scripts\\python.exe scripts\\benchmark_diff.py "
        "reports\\benchmark_baseline.json reports\\benchmark.json --gate",
        "```",
        "",
        "## Ограничения",
        "",
        "- Не менять `data/benchmark_cases.jsonl` и ожидаемые значения.",
        "- Не ослаблять guardrails и SQL-allowlist.",
        "- Не менять больше одного слоя за эксперимент.",
        "- Поднимать версию изменённого промпта.",
        "- При провале gate откатить изменение, а не подгонять метрики.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Предложение по улучшению агента")
    parser.add_argument(
        "--report",
        default=str(ROOT / "reports" / "benchmark.json"),
        help="входной benchmark.json",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "reports" / "improvement_proposal.md"),
        help="Markdown-предложение",
    )
    parser.add_argument(
        "--json-out",
        default=str(ROOT / "reports" / "improvement_proposal.json"),
        help="JSON-предложение",
    )
    parser.add_argument("--index", type=int, default=1, help="номер кластера, с 1")
    parser.add_argument(
        "--exclude-provider",
        action="store_true",
        help="не выбирать провалы провайдера",
    )
    args = parser.parse_args()

    path = Path(args.report)
    if not path.exists():
        print(f"[error] нет файла {path}", file=sys.stderr)
        return 2
    report = load_report(path)
    backlog = build_backlog(report, include_provider=not args.exclude_provider)
    if not backlog:
        print("[ok] провалов нет — предложение не требуется")
        return 0
    if args.index < 1 or args.index > len(backlog):
        print(f"[error] index должен быть 1..{len(backlog)}", file=sys.stderr)
        return 2

    item = backlog[args.index - 1]
    Path(args.out).write_text(_proposal(item, report), encoding="utf-8")
    Path(args.json_out).write_text(
        json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ok] предложение: {item['title']} ({item['count']} репл.)")
    print(f"Файлы: {args.out}, {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
