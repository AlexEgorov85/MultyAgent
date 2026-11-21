"""Проверки метрик и тест-набора."""

from __future__ import annotations

import json
from pathlib import Path

from src.metrics import RequestMetrics, estimate_cost, mean, percentile, timer


def test_timer_and_merge():
    first = RequestMetrics()
    with timer(first, "llm"):
        pass
    first.incr("llm_calls")
    first.tokens["input_tokens"] = 100

    second = RequestMetrics()
    with timer(second, "llm"):
        pass
    second.incr("llm_calls")
    second.tokens["input_tokens"] = 50

    first.merge(second)
    assert first.counters["llm_calls"] == 2
    assert first.tokens["input_tokens"] == 150
    assert first.timings["llm"] >= 0


def test_cost_formula():
    cost = estimate_cost(
        1_000_000,
        1_000_000,
        input_price_per_1m=0.25,
        output_price_per_1m=2.0,
    )
    assert cost == 2.25


def test_percentile_and_mean():
    assert mean([1, 2, 3]) == 2
    assert percentile([1, 2, 3, 4], 0.5) == 2.5


def test_test_cases_are_valid():
    path = Path(__file__).resolve().parents[1] / "data" / "test_cases.jsonl"
    cases = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(cases) == 26
    assert len({case["id"] for case in cases}) == 26

    routes = {case["expected_route"] for case in cases}
    assert {"analytics", "retrieval", "report", "investigation", "out_of_domain", "unsafe"} <= routes

    for case in cases:
        assert case["auditor_id"]
        assert case["query"]
        assert isinstance(case.get("must_include", []), list)
        assert isinstance(case.get("must_not_include", []), list)
