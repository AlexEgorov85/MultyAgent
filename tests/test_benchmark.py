"""Проверки структуры и скоринга многоуровневого бенчмарка."""

from __future__ import annotations

from pathlib import Path

from src.benchmark import (
    answer_has_number,
    evaluate_turn,
    failed_turn_row,
    load_cases,
    summarize,
    validate_cases,
    write_reports,
)

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "data" / "benchmark_cases.jsonl"


def test_benchmark_cases_are_valid():
    cases = load_cases(CASES_PATH)
    assert len(cases) == 18
    assert sum(len(case["turns"]) for case in cases) == 28
    assert not validate_cases(cases)

    tiers = [case["tier"] for case in cases]
    assert tiers.count("simple") == 8
    assert tiers.count("complex") == 5
    assert tiers.count("chain") == 5

    for case in cases:
        if case["tier"] == "chain":
            assert len(case["turns"]) >= 2
            assert any(turn.get("expected_context") for turn in case["turns"])


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
    assert not answer_has_number("В 2025 году завершено 8 проверок", 5)
    assert not answer_has_number("Пункт 5.1 закрыт", 5)


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

    paths = write_reports([ok, failed], summary, [case], tmp_path)
    assert paths["csv"].exists()
    assert paths["json"].exists()
    assert paths["md"].exists()
    markdown = paths["md"].read_text(encoding="utf-8")
    assert "Бенчмарк ассистента аудитора" in markdown
    assert "chain_test" in markdown
    assert "boom" in markdown
