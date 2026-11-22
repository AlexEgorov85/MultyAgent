"""Тесты оценки: повторные прогоны, сводки и отчёты (без вызовов LLM)."""

from __future__ import annotations

import csv
import json

import pytest

import scripts.evaluate as evaluate

SUMMARY_KEYS = {
    "cases",
    "route_accuracy",
    "success_rate",
    "sql_validity_rate",
    "evidence_coverage",
    "latency_mean_sec",
    "latency_p50_sec",
    "latency_p95_sec",
}


def _row(
    case_id: str,
    repeat: int,
    *,
    success: bool,
    route_ok: bool,
    evidence_ok: bool,
    latency: float,
    sql_ok: bool = True,
) -> dict:
    return {
        "id": case_id,
        "repeat": repeat,
        "route": "analytics",
        "expected_route": "analytics",
        "route_ok": route_ok,
        "answer": "ok",
        "include_ok": True,
        "exclude_ok": True,
        "sql_ok": sql_ok,
        "tools_ok": True,
        "evidence_ok": evidence_ok,
        "success": success,
        "latency_sec": latency,
        "llm_calls": 1,
    }


def _two_run_rows() -> list[dict]:
    """3 кейса × 2 прогона.

    Прогон 1: успех 2/3, средняя латентность 2.0.
    Прогон 2: успех 1/3, средняя латентность 4.0.
    """
    return [
        _row("a", 1, success=True, route_ok=True, evidence_ok=True, latency=1.0),
        _row("b", 1, success=True, route_ok=True, evidence_ok=True, latency=2.0),
        _row("c", 1, success=False, route_ok=False, evidence_ok=False, latency=3.0),
        _row("a", 2, success=True, route_ok=True, evidence_ok=True, latency=2.0),
        _row("b", 2, success=False, route_ok=False, evidence_ok=False, latency=4.0),
        _row("c", 2, success=False, route_ok=False, evidence_ok=False, latency=6.0),
    ]


def test_summarize_single_run_keeps_legacy_keys():
    rows = _two_run_rows()[:3]
    summary = evaluate.summarize(rows)

    assert set(summary) == SUMMARY_KEYS
    assert summary["cases"] == 3
    assert summary["success_rate"] == pytest.approx(2 / 3)
    assert summary["route_accuracy"] == pytest.approx(2 / 3)
    assert summary["sql_validity_rate"] == pytest.approx(1.0)
    assert summary["evidence_coverage"] == pytest.approx(2 / 3)
    assert summary["latency_mean_sec"] == pytest.approx(2.0)


def test_summarize_repeats_repeat_one_is_legacy_summary():
    rows = _two_run_rows()[:3]

    assert evaluate.summarize_repeats(rows, 1) == evaluate.summarize(rows)


def test_summarize_repeats_mean_and_population_std():
    summary = evaluate.summarize_repeats(_two_run_rows(), 2)

    assert summary["cases"] == 3
    assert summary["repeat"] == 2
    assert summary["rows"] == 6

    # (2/3 + 1/3) / 2 = 0.5, population std = 1/6.
    for metric in ("success_rate", "route_accuracy", "evidence_coverage"):
        assert summary[f"{metric}_mean"] == pytest.approx(0.5)
        assert summary[f"{metric}_std"] == pytest.approx(1 / 6)

    assert summary["sql_validity_rate_mean"] == pytest.approx(1.0)
    assert summary["sql_validity_rate_std"] == pytest.approx(0.0)

    # Средние латентности прогонов: [2.0, 4.0] -> mean 3.0, population std 1.0.
    assert summary["latency_mean_sec"] == pytest.approx(3.0)
    assert summary["latency_mean_sec_std"] == pytest.approx(1.0)
    assert summary["latency_p50_sec"] == pytest.approx(2.5)


def test_summarize_repeats_identical_runs_have_zero_std():
    first_run = _two_run_rows()[:3]
    rows = [
        {**row, "repeat": 1} for row in first_run
    ] + [
        {**row, "repeat": 2} for row in first_run
    ]

    summary = evaluate.summarize_repeats(rows, 2)

    assert summary["success_rate_mean"] == pytest.approx(2 / 3)
    assert summary["success_rate_std"] == pytest.approx(0.0)
    assert summary["latency_mean_sec_std"] == pytest.approx(0.0)


def test_run_case_adds_repeat_and_isolates_threads():
    calls: list[tuple[dict, dict]] = []

    class FakeGraph:
        def invoke(self, state, config):
            calls.append((state, config))
            return {
                "route": "analytics",
                "final_answer": "готово",
                "acl_response": {
                    "content": {"evidence": [{"id": 1}], "metrics": {"tool_calls": 1}}
                },
            }

    case = {
        "id": "an_01",
        "auditor_id": "auditor",
        "query": "сколько операций",
        "expected_route": "analytics",
    }
    graph = FakeGraph()

    first = evaluate.run_case(graph, case, repeat=1)
    second = evaluate.run_case(graph, case, repeat=2)

    assert first["repeat"] == 1
    assert second["repeat"] == 2
    assert first["success"] is True
    thread_1 = calls[0][1]["configurable"]["thread_id"]
    thread_2 = calls[1][1]["configurable"]["thread_id"]
    assert thread_1 != thread_2


def _write_cases(tmp_path):
    cases = [
        {
            "id": "an_01",
            "auditor_id": "auditor",
            "query": "сколько операций",
            "expected_route": "analytics",
        },
        {
            "id": "ret_01",
            "auditor_id": "auditor",
            "query": "найди регламент",
            "expected_route": "retrieval",
        },
    ]
    path = tmp_path / "cases.jsonl"
    path.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases),
        encoding="utf-8",
    )
    return path


def test_dry_run_does_not_touch_db_or_llm(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(evaluate, "CASES_PATH", _write_cases(tmp_path))

    def boom(*args, **kwargs):
        raise AssertionError("--dry-run не должен запускать БД/LLM")

    monkeypatch.setattr(evaluate.db_runtime, "start_server", boom)

    assert evaluate.main(["--dry-run", "--repeat", "2"]) == 0

    out = capsys.readouterr().out
    assert "[ok] кейсов: 2" in out
    assert "analytics: 1" in out
    assert "retrieval: 1" in out
    assert "всего запусков: 4" in out


def test_repeat_must_be_positive(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(evaluate, "CASES_PATH", _write_cases(tmp_path))

    with pytest.raises(SystemExit):
        evaluate.main(["--dry-run", "--repeat", "0"])

    assert "--repeat должен быть >= 1" in capsys.readouterr().err


def test_write_reports_with_repeats(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate, "REPORTS_DIR", tmp_path)
    rows = _two_run_rows()
    summary = evaluate.summarize_repeats(rows, 2)

    evaluate.write_reports(rows, summary)

    with (tmp_path / "metrics.csv").open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert "repeat" in (reader.fieldnames or [])
        data = list(reader)
    assert len(data) == 6
    assert {row["repeat"] for row in data} == {"1", "2"}
    assert [row["repeat"] for row in data] == ["1", "1", "1", "2", "2", "2"]

    md = (tmp_path / "metrics.md").read_text(encoding="utf-8")
    assert "| ID | Прогон |" in md
    assert "`success_rate (mean)`" in md
    assert "`success_rate (std)`" in md
    assert "`latency_mean_sec (mean по прогонам)`" in md
    assert "`latency_mean_sec (std)`" in md
    assert md.count("| a |") == 2


def test_write_reports_adds_repeat_for_legacy_rows(tmp_path, monkeypatch):
    """Старые строки без поля repeat получают repeat=1 в CSV."""
    monkeypatch.setattr(evaluate, "REPORTS_DIR", tmp_path)
    rows = [
        {key: value for key, value in row.items() if key != "repeat"}
        for row in _two_run_rows()[:3]
    ]

    evaluate.write_reports(rows, evaluate.summarize(rows))

    with (tmp_path / "metrics.csv").open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert "repeat" in (reader.fieldnames or [])
        data = list(reader)
    assert len(data) == 3
    assert {row["repeat"] for row in data} == {"1"}


def test_write_reports_single_run_has_no_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate, "REPORTS_DIR", tmp_path)
    rows = _two_run_rows()[:3]
    summary = evaluate.summarize(rows)

    evaluate.write_reports(rows, summary)

    with (tmp_path / "metrics.csv").open(encoding="utf-8", newline="") as fh:
        data = list(csv.DictReader(fh))
    assert len(data) == 3
    assert {row["repeat"] for row in data} == {"1"}

    md = (tmp_path / "metrics.md").read_text(encoding="utf-8")
    assert "| ID | Прогон |" not in md
    assert "(mean)" not in md
    assert "(std)" not in md
    assert md.count("| a |") == 1
