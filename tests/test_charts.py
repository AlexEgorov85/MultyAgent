"""Спецификация диаграмм: данные предыдущего ответа → chart spec."""

from __future__ import annotations

from src.charts import build_chart_spec, chart_requested


def test_chart_request_detection():
    assert chart_requested("Построй диаграмму на основании этих данных")
    assert chart_requested("Покажи график по карманам")
    assert chart_requested("визуализируй результат")
    assert chart_requested("Build a chart for these rows")
    assert not chart_requested("Сколько проверок по карманам?")


def test_bar_chart_for_theme_counts():
    rows = [
        {"pocket_year": 2026, "theme_code": "платежи", "closed_audits_count": 9},
        {"pocket_year": 2026, "theme_code": "карты", "closed_audits_count": 7},
        {"pocket_year": 2026, "theme_code": "ипотека", "closed_audits_count": 5},
    ]

    spec = build_chart_spec(
        rows,
        ["pocket_year", "theme_code", "closed_audits_count"],
        question="Построй диаграмму на основании этих данных",
        previous_question="Сколько закрыто проверок по каждому карману?",
    )

    assert spec is not None
    assert spec["type"] == "bar"
    assert spec["value_field"] == "closed_audits_count"
    assert spec["data"][0] == {"label": "платежи", "value": 9.0}
    assert spec["title"].startswith("Диаграмма:")


def test_line_chart_for_year_dynamics():
    rows = [
        {"year": 2025, "cnt": 10},
        {"year": 2026, "cnt": 15},
    ]

    spec = build_chart_spec(
        rows,
        ["year", "cnt"],
        question="Покажи динамику по годам",
    )

    assert spec is not None
    assert spec["type"] == "line"
    assert [point["label"] for point in spec["data"]] == ["2025", "2026"]


def test_pie_chart_by_explicit_request():
    rows = [
        {"status": "завершена", "cnt": 28},
        {"status": "в работе", "cnt": 10},
    ]

    spec = build_chart_spec(
        rows,
        ["status", "cnt"],
        question="Построй круговую диаграмму",
    )

    assert spec is not None
    assert spec["type"] == "pie"
    assert spec["data"][0]["label"] == "завершена"


def test_multiple_categories_are_combined():
    rows = [
        {"theme_code": "ипотека", "pocket_year": 2025, "item_count": 41},
        {"theme_code": "ипотека", "pocket_year": 2026, "item_count": 23},
        {"theme_code": "карты", "pocket_year": 2025, "item_count": 52},
        {"theme_code": "карты", "pocket_year": 2026, "item_count": 74},
    ]

    spec = build_chart_spec(
        rows,
        ["theme_code", "pocket_year", "item_count"],
        question="Покажи динамику",
    )

    assert spec is not None
    assert spec["type"] == "line"
    assert spec["data"][0]["label"] == "ипотека · 2025"


def test_no_numeric_measure_returns_none():
    rows = [
        {"theme_code": "ипотека", "status": "завершена"},
        {"theme_code": "карты", "status": "в работе"},
    ]

    assert (
        build_chart_spec(
            rows,
            ["theme_code", "status"],
            question="Построй диаграмму",
        )
        is None
    )


def test_year_constant_is_not_a_measure():
    rows = [
        {"pocket": "2026. Ипотека", "pocket_year": 2026, "cnt": 5},
        {"pocket": "2026. Карты", "pocket_year": 2026, "cnt": 7},
    ]

    spec = build_chart_spec(
        rows,
        ["pocket", "pocket_year", "cnt"],
        question="Построй диаграмму",
    )

    assert spec is not None
    assert spec["value_field"] == "cnt"
    assert [point["label"] for point in spec["data"]] == [
        "2026. Карты",
        "2026. Ипотека",
    ]
