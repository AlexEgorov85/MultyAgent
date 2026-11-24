"""Проверка агента на отложенных сложных вопросах (не из бенчмарка).

Запуск:
    .venv\\Scripts\\python.exe scripts\\check_agent_questions.py
    .venv\\Scripts\\python.exe scripts\\check_agent_questions.py --only problems_filter

Скрипт не участвует в бенчмарке: вопросы и ожидания заданы отдельно, чтобы
изменения промптов проверялись на обобщение, а не на знакомых кейсах.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config, db_runtime  # noqa: E402
from src.benchmark import answer_has_number  # noqa: E402
from src.graph.main_graph import build_main_graph  # noqa: E402
from src.llm import OpenAILLM  # noqa: E402
from src.rag.embeddings import HashEmbeddings, OpenAIEmbeddings  # noqa: E402

CASES: list[dict] = [
    {
        "id": "critical_theme_year",
        "query": "Сравни количество критических пунктов по темам за 2025 и 2026 годы",
        "route": "analytics",
        "row_column": "critical_count",
        "row_values": [4, 4, 10, 5, 5, 6, 11, 5, 10, 4],
    },
    {
        "id": "draft_no_scripts",
        "query": "Сколько пунктов без скриптов в черновиках актов?",
        "route": "analytics",
        "numbers": [10],
    },
    {
        "id": "report_approved",
        "query": "Сформируй проект раздела акта по AUD-2026-CARDS-12",
        "route": "report",
        "must_include": ["AUD-2026-CARDS-12", "утвержд"],
    },
    {
        "id": "problems_filter",
        "query": (
            "Найди проблемы по проверке AUD-2025-DEPOSITS-06 "
            "и похожие формулировки в других актах"
        ),
        "route": "analytics",
        "numbers": [3],
        "must_not_include": ["8 проблем"],
    },
    {
        "id": "deposits_investigation",
        "query": (
            "Почему по вкладам в 2026 году выросло число критических пунктов? "
            "Сопоставь с 2025 годом."
        ),
        "route": "investigation",
        "numbers": [4],
        "must_not_include": ["причина установлена"],
    },
    {
        "id": "chart_months_2025",
        "query": (
            "Покажи по месяцам количество завершённых проверок за 2025 год "
            "в виде линейного графика"
        ),
        "route": "analytics",
        "chart_type": "line",
        "chart_values": [2, 7, 4, 7, 5, 5, 5, 6],
    },
]


def _evaluate(case: dict, result: dict) -> list[str]:
    problems: list[str] = []
    answer = str(result.get("final_answer") or "")
    content = (result.get("acl_response") or {}).get("content") or {}

    if case.get("route") and result.get("route") != case["route"]:
        problems.append(f"route={result.get('route')} вместо {case['route']}")
    for number in case.get("numbers") or []:
        if not answer_has_number(answer, number):
            problems.append(f"в ответе нет числа {number}")
    for text in case.get("must_include") or []:
        if text.lower() not in answer.lower():
            problems.append(f"в ответе нет {text!r}")
    for text in case.get("must_not_include") or []:
        if text.lower() in answer.lower():
            problems.append(f"в ответе лишнее {text!r}")

    column = case.get("row_column")
    if column:
        rows = content.get("rows") or []
        values = sorted(
            int(row[column])
            for row in rows
            if isinstance(row, dict) and row.get(column) is not None
        )
        if values != sorted(case["row_values"]):
            problems.append(f"{column}={values} вместо {sorted(case['row_values'])}")

    chart = content.get("chart") or (result.get("presentation") or {}).get("chart")
    if case.get("chart_values"):
        if not isinstance(chart, dict):
            problems.append("диаграмма не построена")
        else:
            if chart.get("type") != case.get("chart_type"):
                problems.append(f"тип диаграммы {chart.get('type')}")
            values = [float(point["value"]) for point in chart.get("data") or []]
            if values != [float(item) for item in case["chart_values"]]:
                problems.append(f"точки диаграммы {values}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Отложенные сложные вопросы")
    parser.add_argument("--only", nargs="*", default=[], help="ID вопросов")
    args = parser.parse_args()

    cases = [case for case in CASES if not args.only or case["id"] in args.only]
    if not cases:
        print("[error] нет подходящих вопросов", file=sys.stderr)
        return 2

    server = db_runtime.start_server()
    try:
        db_runtime.ensure_database(server)
        db_runtime.apply_migrations(server)
        db_runtime.ensure_roles(server)
        model = db_runtime.get_index_embedding_model(server)
        embeddings = (
            HashEmbeddings() if model == "hash" else OpenAIEmbeddings()
        )
        graph = build_main_graph(server, OpenAILLM(), embeddings=embeddings)

        failed = 0
        for case in cases:
            thread = f"held-out-{case['id']}"
            result = graph.invoke(
                {
                    "messages": [{"role": "user", "content": case["query"]}],
                    "auditor_id": "AUD-004",
                    "conversation_id": thread,
                },
                config={"configurable": {"thread_id": thread}},
            )
            problems = _evaluate(case, result)
            status = "OK  " if not problems else "FAIL"
            print(f"[{status}] {case['id']}: {case['query']}")
            print(
                "       route="
                f"{result.get('route')} answer={str(result.get('final_answer'))[:180]!r}"
            )
            for problem in problems:
                print(f"       - {problem}")
            failed += bool(problems)
        return 1 if failed else 0
    finally:
        server.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
