"""Запуск многоуровневого бенчмарка: simple, complex и chain.

Примеры:
    .venv\\Scripts\\python.exe scripts\\benchmark.py --dry-run
    .venv\\Scripts\\python.exe scripts\\benchmark.py --tier simple
    .venv\\Scripts\\python.exe scripts\\benchmark.py --only chain_year_theme
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config, db_runtime, telemetry  # noqa: E402
from src.benchmark import (  # noqa: E402
    TIERS,
    evaluate_turn,
    failed_turn_row,
    load_cases,
    select_cases,
    summarize,
    summarize_table_coverage,
    validate_cases,
    write_reports,
)
from src.graph.main_graph import build_main_graph  # noqa: E402
from src.llm import OpenAILLM  # noqa: E402
from src.prompts import prompt_versions  # noqa: E402
from src.rag.embeddings import OpenAIEmbeddings  # noqa: E402

CASES_PATH = ROOT / "data" / "benchmark_cases.jsonl"
REPORTS_DIR = ROOT / "reports"


def _print_row(row: dict[str, Any]) -> None:
    status = "OK  " if row.get("success") else "FAIL"
    context = ""
    if row.get("context_applicable"):
        context = (
            f" context={'ok' if row.get('context_ok') else 'FAIL'}"
            f"(query={'ok' if row.get('context_resolved_ok') else 'FAIL'}, "
            f"answer={'ok' if row.get('context_answer_ok') else 'FAIL'})"
        )
    print(
        f"[{status}] {row['case_id']}.{row['step']}: "
        f"route={row.get('route') or 'n/a'} "
        f"llm={row.get('llm_calls', 0)} tools={row.get('tool_calls', 0)} "
        f"tokens={row.get('total_tokens', 0)} "
        f"latency={row.get('latency_sec', 0)}s{context}"
    )
    if not row.get("success"):
        details = []
        for key, label in (
            ("route_ok", "route"),
            ("numbers_ok", "numbers"),
            ("tools_ok", "tools"),
            ("strategy_ok", "strategy"),
            ("evidence_ok", "evidence"),
            ("rounds_ok", "acl_rounds"),
            ("include_ok", "must_include"),
            ("exclude_ok", "must_not_include"),
            ("sql_ok", "sql"),
            ("steps_ok", "steps"),
            ("llm_calls_ok", "max_llm_calls"),
            ("llm_errors_ok", "max_llm_errors"),
            ("tool_calls_ok", "max_tool_calls"),
            ("tokens_ok", "max_tokens"),
            ("cost_ok", "max_cost"),
            ("latency_ok", "max_latency"),
            ("forbidden_tools_ok", "forbidden_tools"),
            ("sql_retries_ok", "max_sql_retries"),
            ("acl_rounds_ok", "max_acl_rounds"),
            ("max_steps_ok", "max_steps"),
        ):
            if row.get(key) is False:
                details.append(label)
        if row.get("error"):
            details.append(f"error={row['error']}")
        if details:
            print(f"       не прошло: {', '.join(details)}")
        answer = str(row.get("answer") or "").strip()
        if answer:
            print(f"       ответ: {answer[:240]}")


def run_case(
    graph,
    case: dict[str, Any],
    *,
    verbose: bool = True,
    run_id: str = "",
) -> list[dict[str, Any]]:
    """Прогоняет один кейс; цепочка идёт в одной нити.

    ``run_id`` делает thread_id уникальным для запуска: история диалога
    хранится в PostgreSQL и не должна протекать из предыдущего прогона.
    """
    case_id = str(case["id"])
    prefix = f"bench-{run_id}-{case_id}" if run_id else f"bench-{case_id}"
    thread_id = prefix
    client_history: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []

    for step, turn in enumerate(case["turns"], start=1):
        if turn.get("reset_thread") and step > 1:
            thread_id = f"{prefix}-r{step}"

        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": turn["query"]}],
            "auditor_id": case["auditor_id"],
            "conversation_id": thread_id,
        }
        if turn.get("reset_thread"):
            payload["client_history"] = list(client_history)

        telemetry.start_run()
        started = time.perf_counter()
        try:
            result = graph.invoke(
                payload,
                config={"configurable": {"thread_id": thread_id}},
            )
        except Exception as exc:  # noqa: BLE001 - один кейс не должен рвать прогон
            latency = time.perf_counter() - started
            row = failed_turn_row(case, turn, step, exc, latency)
            row["process"] = telemetry.snapshot()
            telemetry.stop_run()
            rows.append(row)
            if verbose:
                _print_row(row)
            client_history.append({"role": "user", "text": turn["query"]})
            client_history.append({"role": "assistant", "text": ""})
            continue

        latency = time.perf_counter() - started
        process = telemetry.snapshot()
        telemetry.stop_run()
        row = evaluate_turn(case, turn, result, latency, step, process=process)
        rows.append(row)
        if verbose:
            _print_row(row)
        client_history.append({"role": "user", "text": turn["query"]})
        client_history.append(
            {"role": "assistant", "text": str(result.get("final_answer", "") or "")}
        )

    return rows


def _server_alive(server) -> bool:
    """Проверяет, что PostgreSQL отвечает, иначе прогон бессмысленно продолжать."""
    try:
        with db_runtime.connect(server) as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception:  # noqa: BLE001
        return False


def _dry_run(cases: list[dict[str, Any]]) -> None:
    turns = sum(len(case["turns"]) for case in cases)
    print(f"[ok] кейсов: {len(cases)}, реплик: {turns}")
    for tier in TIERS:
        tier_cases = [case for case in cases if case.get("tier") == tier]
        tier_turns = sum(len(case["turns"]) for case in tier_cases)
        print(f"  {tier}: {len(tier_cases)} кейсов / {tier_turns} реплик")
    coverage = summarize_table_coverage(cases)
    print("\nПокрытие таблиц:")
    for item in coverage:
        print(f"  {item['table']}: {item['cases']} кейсов / {item['turns']} реплик")
    print("\nСостав:")
    for case in cases:
        print(
            f"  {case['id']} [{case['tier']}]: {case['title']} "
            f"({len(case['turns'])} репл.)"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Бенчмарк ассистента аудитора")
    parser.add_argument("--dry-run", action="store_true", help="только проверить набор")
    parser.add_argument("--tier", choices=TIERS, help="только один уровень")
    parser.add_argument("--only", nargs="*", default=[], help="ID конкретных кейсов")
    parser.add_argument("--limit", type=int, default=0, help="ограничить число кейсов")
    parser.add_argument(
        "--report-dir",
        default=str(REPORTS_DIR),
        help="каталог для benchmark.csv/json/md",
    )
    parser.add_argument("--no-write", action="store_true", help="не писать отчёты")
    parser.add_argument("--quiet", action="store_true", help="без прогресса по ходам")
    args = parser.parse_args()

    all_cases = load_cases(CASES_PATH)
    errors = validate_cases(all_cases)
    if errors:
        print("[error] проблемы в бенчмарке:", file=sys.stderr)
        for error in errors:
            print(" -", error, file=sys.stderr)
        return 2

    cases = select_cases(
        all_cases,
        tier=args.tier,
        only=args.only,
        limit=args.limit,
    )
    if not cases:
        print("[error] после фильтров не осталось кейсов", file=sys.stderr)
        return 2

    if args.dry_run:
        _dry_run(cases)
        return 0

    try:
        llm = OpenAILLM()
        embeddings = OpenAIEmbeddings()
    except Exception as exc:  # noqa: BLE001
        print(
            f"[error] LLM недоступна: {exc}. Задайте OPENAI_API_KEY в .env.",
            file=sys.stderr,
        )
        return 2

    server = db_runtime.start_server()
    rows: list[dict[str, Any]] = []
    run_id = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
    try:
        graph = build_main_graph(server, llm, embeddings=embeddings)
        for case in cases:
            if not _server_alive(server):
                print(
                    "[error] PostgreSQL перестал отвечать: прогон остановлен, "
                    "частичные результаты сохранены.",
                    file=sys.stderr,
                )
                break
            rows.extend(
                run_case(
                    graph,
                    case,
                    verbose=not args.quiet,
                    run_id=run_id,
                )
            )
    finally:
        server.cleanup()

    summary = summarize(rows)
    print("\nИтог:")
    for key, value in summary.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")

    if not args.no_write:
        environment = {
            "run_id": run_id,
            "model": getattr(llm, "model", ""),
            "embedding_model": getattr(embeddings, "model", ""),
            "seed": 42,
            "as_of": config.DEFAULT_AS_OF_DATE.isoformat(),
            "prompt_versions": prompt_versions(),
        }
        paths = write_reports(
            rows,
            summary,
            cases,
            args.report_dir,
            environment=environment,
        )
        print(
            "\nОтчёты: "
            f"{paths['csv']}, {paths['json']}, {paths['md']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
