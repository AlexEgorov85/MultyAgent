"""Проверки структуры и скоринга многоуровневого бенчмарка."""

from __future__ import annotations

from pathlib import Path

from src.benchmark import (
    answer_has_number,
    evaluate_turn,
    extract_agent_state,
    failed_turn_row,
    load_cases,
    rescore_report,
    summarize,
    summarize_prompts,
    summarize_table_coverage,
    validate_cases,
    write_reports,
)

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "data" / "benchmark_cases.jsonl"


def test_benchmark_cases_are_valid():
    cases = load_cases(CASES_PATH)
    assert len(cases) == 51
    assert sum(len(case["turns"]) for case in cases) == 67
    assert not validate_cases(cases)

    tiers = [case["tier"] for case in cases]
    assert tiers.count("simple") == 15
    assert tiers.count("medium") == 18
    assert tiers.count("complex") == 10
    assert tiers.count("chain") == 8

    for case in cases:
        if case["id"] not in {"simple_out_of_domain", "simple_unsafe_delete"}:
            assert case["tables"]
        if case["tier"] == "chain":
            assert len(case["turns"]) >= 2
            assert any(turn.get("expected_context") for turn in case["turns"])


def test_every_seed_table_is_covered():
    coverage = summarize_table_coverage(load_cases(CASES_PATH))
    uncovered = [item["table"] for item in coverage if item["cases"] == 0]
    assert not uncovered
    by_table = {item["table"]: item for item in coverage}
    assert by_table["auditors"]["cases"] >= 2
    assert by_table["script_runs"]["cases"] >= 2
    assert by_table["deviations"]["cases"] >= 2
    assert by_table["auditor_memory"]["cases"] >= 1
    assert by_table["dataset_metadata"]["cases"] >= 1


def test_validate_cases_reports_structural_errors():
    cases = [
        {
            "id": "bad_chain",
            "tier": "chain",
            "title": "Без контекста",
            "auditor_id": "AUD-004",
            "turns": [{"query": "Первый?", "expected_route": "analytics"}],
        },
        {
            "id": "bad_chain",
            "tier": "simple",
            "title": "Дубликат",
            "auditor_id": "AUD-004",
            "turns": [{"query": "Вопрос?", "expected_route": "nonsense"}],
        },
    ]
    errors = validate_cases(cases)
    assert any("дубликат id" in error for error in errors)
    assert any("минимум 2" in error for error in errors)
    assert any("нет ни одного expected_context" in error for error in errors)
    assert any("неизвестный маршрут" in error for error in errors)


def test_answer_has_number_ignores_years_and_item_numbers():
    assert answer_has_number("Всего 5 завершённых проверок", 5)
    assert answer_has_number("В 2025 году завершено 8 проверок", 8)
    assert answer_has_number("Всего 273.", 273)
    assert answer_has_number("Отклонений: 104, проблем: 25", 104)
    assert not answer_has_number("В 2025 году завершено 8 проверок", 5)
    assert not answer_has_number("Пункт 5.1 закрыт", 5)
    assert not answer_has_number("Значение 1,5", 1)


def _result(
    *,
    route: str = "analytics",
    resolved: str = "",
    answer: str = "",
    strategy: str = "generated",
    evidence: list[dict] | None = None,
) -> dict:
    return {
        "route": route,
        "resolved_query": resolved,
        "final_answer": answer,
        "acl_response": {
            "content": {
                "strategy": strategy,
                "answer": answer,
                "sql": "SELECT 1",
                "evidence": evidence or [{"type": "sql_result", "query_id": "q-1"}],
            }
        },
    }


def test_evaluate_turn_accepts_context_in_resolved_query():
    case = {
        "id": "chain_test",
        "tier": "chain",
        "title": "Тест",
        "auditor_id": "AUD-004",
    }
    turn = {
        "query": "А за 2025 год?",
        "expected_route": "analytics",
        "expected_context": ["2025", "ипотек"],
        "expected_numbers": [8],
        "expected_tools": ["run_readonly_sql"],
        "expected_evidence": ["sql_result"],
        "min_evidence": 1,
    }
    row = evaluate_turn(
        case,
        turn,
        _result(
            resolved="Сколько завершённых проверок по ипотеке в 2025 году?",
            answer="В 2025 году завершено 8 проверок по ипотеке.",
        ),
        latency_sec=1.25,
        step=2,
    )

    assert row["success"]
    assert row["context_ok"]
    assert row["context_resolved_ok"]
    assert row["numbers_ok"]
    assert row["tools_ok"]
    assert row["evidence_ok"]
    assert row["tools_actual"] == "run_readonly_sql"


def test_evaluate_turn_accepts_context_in_answer_when_query_is_not_rewritten():
    case = {
        "id": "chain_test",
        "tier": "chain",
        "title": "Тест",
        "auditor_id": "AUD-004",
    }
    turn = {
        "query": "А сколько из них устранено?",
        "expected_route": "analytics",
        "expected_context": ["AUD-2026-MORTGAGE-02"],
        "min_evidence": 1,
    }
    row = evaluate_turn(
        case,
        turn,
        _result(
            resolved="А сколько из них устранено?",
            answer="По проверке AUD-2026-MORTGAGE-02 закрыт 1 пункт.",
            strategy="drilldown",
            evidence=[{"type": "item", "item_id": "ITM-1"}],
        ),
        latency_sec=0.5,
        step=2,
    )

    assert row["success"]
    assert row["context_ok"]
    assert row["context_answer_ok"]
    assert not row["context_resolved_ok"]


def test_evaluate_turn_checks_citations_for_retrieval():
    case = {
        "id": "retrieval_test",
        "tier": "simple",
        "title": "Тест",
        "auditor_id": "AUD-004",
        "tables": ["knowledge_chunks"],
    }
    turn = {
        "query": "Какие сроки установлены для критического риска?",
        "expected_route": "retrieval",
        "min_citations": 1,
        "min_evidence": 1,
    }
    result = _result(
        route="retrieval",
        answer="Для критического риска — до 30 календарных дней.",
        strategy="",
        evidence=[{"type": "методика", "source_id": "сроки_устранения"}],
    )
    result["acl_response"]["content"]["citations"] = ["сроки_устранения"]
    row = evaluate_turn(case, turn, result, 1.0, 1)
    assert row["success"]
    assert row["citations_ok"]
    assert row["citations_count"] == 1

    result["acl_response"]["content"]["citations"] = []
    row = evaluate_turn(case, turn, result, 1.0, 1)
    assert not row["success"]
    assert not row["citations_ok"]


def test_evaluate_turn_records_process_and_enforces_budget():
    case = {
        "id": "process_test",
        "tier": "simple",
        "title": "Тест процесса",
        "auditor_id": "AUD-004",
    }
    turn = {
        "query": "Сколько проверок?",
        "expected_route": "analytics",
        "expected_steps": ["route", "sql", "sql_result"],
        "max_llm_calls": 3,
        "max_tool_calls": 2,
        "max_total_tokens": 1000,
        "max_sql_retries": 1,
    }
    result = _result(
        resolved="Сколько проверок?",
        answer="Всего 5 проверок.",
    )
    result["trace"] = [
        {"step": "route", "agent": "Orchestrator"},
        {"step": "sql", "agent": "Analytics"},
        {"step": "sql_result", "agent": "Analytics"},
    ]
    process = {
        "llm_calls": 2,
        "tool_calls": 1,
        "tokens": {"input_tokens": 400, "output_tokens": 100},
        "cost_usd": 0.001,
        "llm_latency_sec": 1.5,
        "tool_latency_sec": 0.5,
        "tool_events": [{"name": "run_readonly_sql"}],
        "prompts": [{"id": "router", "version": 1, "hash": "abc123"}],
    }
    row = evaluate_turn(case, turn, result, 3.0, 1, process=process)
    assert row["success"]
    assert row["process_success"]
    assert row["answer_success"]
    assert row["total_tokens"] == 500
    assert row["llm_calls"] == 2
    assert row["tool_calls"] == 1
    assert row["llm_latency_sec"] == 1.5
    assert row["tool_latency_sec"] == 0.5
    assert row["overhead_sec"] == 1.0
    assert "router@v1:abc123" in row["prompts"]
    assert row["state"]["route"] == "analytics"
    assert row["state"]["fingerprint"]

    too_expensive = dict(process)
    too_expensive["llm_calls"] = 4
    row = evaluate_turn(case, turn, result, 3.0, 1, process=too_expensive)
    assert not row["llm_calls_ok"]
    assert not row["process_success"]
    assert not row["success"]


def test_extract_agent_state_is_compact_and_stable():
    result = _result(
        resolved="Сколько проверок по ипотеке?",
        answer="5 проверок.",
    )
    result["route"] = "analytics"
    result["route_reason"] = "количество"
    result["route_confidence"] = 0.9
    result["conversation_id"] = "thread-1"
    result["turn_id"] = "turn-1"
    result["guardrail"] = {"safe": True, "reason": ""}
    result["answer_guardrail"] = {"safe": True, "reason": ""}
    result["trace"] = [
        {"step": "route", "agent": "Orchestrator", "status": "ok"},
        {"step": "sql", "agent": "Analytics", "status": "ok"},
    ]
    state = extract_agent_state(
        result,
        {"prompts": [{"id": "router", "version": 1, "hash": "abc123"}]},
    )
    assert state["route"] == "analytics"
    assert state["resolved_query"] == "Сколько проверок по ипотеке?"
    assert state["guardrail"]["safe"] is True
    assert [item["step"] for item in state["steps"]] == ["route", "sql"]
    assert state["answer_chars"] == len("5 проверок.")
    assert len(state["fingerprint"]) == 16


def test_rescore_report_recomputes_numbers_after_matcher_fix():
    case = {
        "id": "rescore",
        "tier": "simple",
        "title": "Пересчёт",
        "auditor_id": "AUD-004",
        "turns": [{"query": "Сколько?", "expected_route": "analytics", "expected_numbers": [273]}],
    }
    row = {
        "case_id": "rescore",
        "step": 1,
        "tier": "simple",
        "query": "Сколько?",
        "expected_route": "analytics",
        "route": "analytics",
        "success": False,
        "answer_success": False,
        "process_success": True,
        "route_ok": True,
        "context_ok": True,
        "numbers_applicable": True,
        "numbers_ok": False,
        "include_ok": True,
        "exclude_ok": True,
        "evidence_ok": True,
        "rounds_ok": True,
        "citations_ok": True,
        "sql_ok": True,
        "answer_ok": True,
        "answer": "Всего 273.",
    }
    report = {"summary": {}, "turns": [row]}
    rescored = rescore_report(report, [case])
    assert rescored["turns"][0]["numbers_ok"]
    assert rescored["turns"][0]["answer_success"]
    assert rescored["turns"][0]["success"]


def test_failed_turn_row_keeps_structure():
    case = {
        "id": "chain_test",
        "tier": "chain",
        "title": "Тест",
        "auditor_id": "AUD-004",
    }
    turn = {
        "query": "А за 2025 год?",
        "expected_route": "analytics",
        "expected_context": ["2025"],
    }
    row = failed_turn_row(case, turn, 2, RuntimeError("LLM timeout"), 3.0)
    assert not row["success"]
    assert row["error"] == "LLM timeout"
    assert row["tier"] == "chain"
    assert row["context_applicable"]


def test_summarize_prompts_parses_versions():
    rows = [
        {"prompts": "router@v1:abc;report_draft@v2:def"},
        {"prompts": "router@v1:abc"},
    ]
    result = summarize_prompts(rows)
    by_name = {item["prompt"]: item for item in result}
    assert by_name["router"]["version"] == "v1"
    assert by_name["router"]["hash"] == "abc"
    assert by_name["router"]["turns"] == 2
    assert by_name["report_draft"]["version"] == "v2"
    assert by_name["report_draft"]["turns"] == 1


def test_summarize_and_write_reports(tmp_path):
    case = {
        "id": "chain_test",
        "tier": "chain",
        "title": "Тест",
        "auditor_id": "AUD-004",
    }
    ok = evaluate_turn(
        case,
        {
            "query": "А за 2025 год?",
            "expected_route": "analytics",
            "expected_context": ["2025"],
            "expected_numbers": [8],
            "min_evidence": 1,
        },
        _result(
            resolved="Сколько проверок по ипотеке в 2025 году?",
            answer="8 проверок",
        ),
        1.0,
        2,
    )
    failed = failed_turn_row(
        case,
        {"query": "Ошибка?", "expected_route": "analytics"},
        3,
        "boom",
        2.0,
    )

    summary = summarize([ok, failed])
    assert summary["turns"] == 2
    assert summary["success_rate"] == 0.5
    assert summary["context_retention_rate"] == 1.0
    assert summary["chain_success_rate"] == 0.5
    assert "answer_success_rate" in summary
    assert "process_success_rate" in summary
    assert "latency_total_sec" in summary
    assert "llm_calls_total" in summary
    assert "tool_calls_total" in summary

    paths = write_reports([ok, failed], summary, [case], tmp_path)
    assert paths["csv"].exists()
    assert paths["json"].exists()
    assert paths["md"].exists()
    markdown = paths["md"].read_text(encoding="utf-8")
    assert "Бенчмарк ассистента аудитора" in markdown
    assert "chain_test" in markdown
    assert "boom" in markdown


def test_summary_counts_sql_queries():
    rows = [
        {
            "case_id": "sql_queries_case",
            "tier": "simple",
            "success": True,
            "latency_sec": 1.0,
            "sql_queries": 3,
        }
    ]
    summary = summarize(rows)
    assert summary["sql_queries_total"] == 3
