"""Проверка чисел в LLM-ответе по строкам результата."""

from __future__ import annotations

from src.graph.analytics_graph import _summary_numbers_supported


def test_llm_numbers_outside_rows_are_rejected():
    rows = [
        {"pocket_year": 2025, "theme_code": "ипотека", "closed_audits_count": 8},
        {"pocket_year": 2026, "theme_code": "ипотека", "closed_audits_count": 5},
    ]
    columns = ["pocket_year", "theme_code", "closed_audits_count"]

    assert _summary_numbers_supported("В 2025 году — 8, в 2026 — 5.", rows, columns)
    assert not _summary_numbers_supported("Всего закрыто 31 проверка.", rows, columns)
