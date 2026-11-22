"""Проверки triage, diff и regression-gate."""

from __future__ import annotations

from src.improvement import (
    build_backlog,
    classify_turn,
    diff_runs,
    evaluate_gate,
    format_backlog_md,
    format_diff_md,
)


def _row(**overrides):
    row = {
        "case_id": "case",
        "step": 1,
        "tier": "simple",
        "query": "Вопрос?",
        "expected_route": "analytics",
        "route": "analytics",
        "success": True,
        "answer_success": True,
        "process_success": True,
        "route_ok": True,
        "context_applicable": False,
        "context_resolved_ok": True,
        "context_answer_ok": True,
        "tools_ok": True,
        "strategy_ok": True,
        "forbidden_tools_ok": True,
        "steps_ok": True,
        "max_steps_ok": True,
        "sql_ok": True,
        "sql_retries": 0,
        "sql_retries_ok": True,
        "evidence_ok": True,
        "citations_ok": True,
        "numbers_ok": True,
        "include_ok": True,
        "exclude_ok": True,
        "llm_calls_ok": True,
        "tool_calls_ok": True,
        "tokens_ok": True,
        "cost_ok": True,
        "latency_ok": True,
        "acl_rounds_ok": True,
        "llm_errors": 0,
        "total_tokens": 100,
        "latency_sec": 1.0,
        "llm_calls": 1,
        "tool_calls": 1,
        "prompts": "router@v1:abc",
        "error": "",
    }
    row.update(overrides)
    return row


def _report(rows, summary=None):
    return {
        "environment": {"run_id": "run-1", "model": "test"},
        "summary": summary or {},
        "turns": rows,
    }


def test_classify_turn_categories():
    assert classify_turn(_row(route_ok=False, success=False, answer_success=False)) == [
        "routing"
    ]
    assert classify_turn(
        _row(
            context_applicable=True,
            context_resolved_ok=False,
            success=False,
            answer_success=False,
        )
    ) == ["context"]
    assert classify_turn(
        _row(tools_ok=False, success=False, process_success=False)
    ) == ["tool_policy"]
    assert classify_turn(
        _row(sql_ok=False, success=False, answer_success=False)
    ) == ["sql"]
    assert classify_turn(
        _row(llm_errors=1, success=False, process_success=False, answer_success=False)
    ) == ["provider"]
    assert classify_turn(
        _row(tokens_ok=False, success=False, process_success=False)
    ) == ["efficiency"]


def test_backlog_prioritizes_and_excludes_provider():
    rows = [
        _row(),
        _row(
            case_id="routing",
            route_ok=False,
            success=False,
            answer_success=False,
        ),
        _row(
            case_id="provider",
            llm_errors=2,
            success=False,
            answer_success=False,
            process_success=False,
        ),
        _row(case_id="tool", tools_ok=False, success=False, process_success=False),
    ]
    backlog = build_backlog(_report(rows))
    assert [item["category"] for item in backlog] == [
        "routing",
        "tool_policy",
        "provider",
    ]
    no_provider = build_backlog(_report(rows), include_provider=False)
    assert all(item["category"] != "provider" for item in no_provider)
    assert backlog[0]["validation"].startswith(
        ".venv\\Scripts\\python.exe scripts\\benchmark.py"
    )


def test_diff_detects_improvements_and_regressions():
    baseline = _report(
        [
            _row(case_id="a", success=False, answer_success=False),
            _row(case_id="b"),
        ],
        summary={"success_rate": 0.5, "total_tokens_total": 100},
    )
    candidate = _report(
        [
            _row(case_id="a"),
            _row(case_id="b", success=False, answer_success=False),
        ],
        summary={"success_rate": 0.5, "total_tokens_total": 120},
    )
    diff = diff_runs(baseline, candidate)
    assert diff["improvement_count"] == 1
    assert diff["regression_count"] == 1
    assert diff["summary_delta"]["total_tokens_total"] == 20
    assert diff["improvements"][0]["key"] == "a.1"
    assert diff["regressions"][0]["key"] == "b.1"


def test_gate_passes_on_improvement_and_fails_on_regression():
    baseline = _report(
        [_row(case_id="a", success=False, answer_success=False)],
        summary={
            "success_rate": 0.0,
            "answer_success_rate": 0.0,
            "process_success_rate": 1.0,
            "total_tokens_total": 100,
            "latency_p95_sec": 10,
            "cost_usd_total": 1,
        },
    )
    candidate = _report(
        [_row(case_id="a")],
        summary={
            "success_rate": 1.0,
            "answer_success_rate": 1.0,
            "process_success_rate": 1.0,
            "total_tokens_total": 105,
            "latency_p95_sec": 10.5,
            "cost_usd_total": 1.05,
        },
    )
    gate = evaluate_gate(baseline, candidate)
    assert gate["passed"]

    baseline_ok = _report(
        [_row(case_id="a")],
        summary={
            "success_rate": 1.0,
            "answer_success_rate": 1.0,
            "process_success_rate": 1.0,
            "total_tokens_total": 100,
            "latency_p95_sec": 10,
            "cost_usd_total": 1,
        },
    )
    regression = _report(
        [_row(case_id="a", success=False, answer_success=False)],
        summary={**baseline_ok["summary"], "success_rate": 0.0, "answer_success_rate": 0.0},
    )
    gate = evaluate_gate(baseline_ok, regression)
    assert not gate["passed"]
    assert gate["reasons"]


def test_markdown_formatters_contain_sections():
    backlog = build_backlog(
        _report([_row(success=False, answer_success=False, route_ok=False)])
    )
    md = format_backlog_md(backlog)
    assert "# Backlog доработок" in md
    assert "Маршрутизация" in md
    assert "Проверка" in md

    diff = diff_runs(
        _report([_row(success=False, answer_success=False)]),
        _report([_row()]),
    )
    md = format_diff_md(diff, evaluate_gate(
        _report([_row(success=False, answer_success=False)], summary={"success_rate": 0}),
        _report([_row()], summary={"success_rate": 1}),
    ))
    assert "# Сравнение прогонов" in md
    assert "Gate" in md
