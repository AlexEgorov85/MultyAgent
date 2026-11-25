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


def test_declared_numbers_must_be_in_rows():
    rows = [
        {"pocket_year": 2025, "closed_audits_count": 8},
        {"pocket_year": 2026, "closed_audits_count": 5},
    ]
    columns = ["pocket_year", "closed_audits_count"]

    assert _summary_numbers_supported(
        "В 2025 — 8, в 2026 — 5.",
        rows,
        columns,
        claims=[2025, 8, 2026, 5],
    )
    assert not _summary_numbers_supported(
        "Всего 31 проверка.",
        rows,
        columns,
        claims=[31],
    )


def test_undeclared_digit_is_rejected():
    """Если модель не объявила число, проверка не должна проходить вхолостую."""
    rows = [
        {"pocket_year": 2025, "closed_audits_count": 8},
        {"pocket_year": 2026, "closed_audits_count": 5},
    ]
    columns = ["pocket_year", "closed_audits_count"]

    assert not _summary_numbers_supported(
        "В 2025 — 8, в 2026 — 5.",
        rows,
        columns,
        claims=[2025, 8],
    )


def test_negative_median_is_grounded():
    rows = [{"theme_code": "ипотека", "median": -7}]
    columns = ["theme_code", "median"]

    assert _summary_numbers_supported("Медиана: -7 дней.", rows, columns)
    assert not _summary_numbers_supported("Медиана: -9 дней.", rows, columns)


def test_rounded_percentage_is_grounded():
    rows = [{"critical_share": 0.074626}]
    columns = ["critical_share"]

    assert _summary_numbers_supported("Доля: 7,5%.", rows, columns)
