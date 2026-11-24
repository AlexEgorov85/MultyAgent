"""Проверка, что точки диаграммы LLM действительно есть в данных."""

from __future__ import annotations

from src.charts import ground_chart_points


def test_grounded_points_are_kept():
    rows = [
        {"pocket_year": 2026, "theme_code": "платежи", "cnt": 9},
        {"pocket_year": 2026, "theme_code": "карты", "cnt": 7},
    ]

    points = ground_chart_points(
        {
            "data": [
                {"label": "платежи", "value": 9},
                {"label": "карты", "value": 7},
            ]
        },
        rows,
        ["pocket_year", "theme_code", "cnt"],
    )

    assert points == [
        {"label": "платежи", "value": 9.0},
        {"label": "карты", "value": 7.0},
    ]


def test_hallucinated_points_are_removed():
    rows = [
        {"status": "завершена", "cnt": 28},
        {"status": "в работе", "cnt": 10},
    ]

    points = ground_chart_points(
        {
            "data": [
                {"label": "завершена", "value": 28},
                {"label": "выдумано", "value": 999},
                {"label": "в работе", "value": 10},
            ]
        },
        rows,
        ["status", "cnt"],
    )

    assert points == [
        {"label": "завершена", "value": 28.0},
        {"label": "в работе", "value": 10.0},
    ]


def test_less_than_two_grounded_points_is_rejected():
    rows = [
        {"status": "завершена", "cnt": 28},
        {"status": "в работе", "cnt": 10},
    ]

    assert (
        ground_chart_points(
            {"data": [{"label": "выдумано", "value": 999}]},
            rows,
            ["status", "cnt"],
        )
        is None
    )


def test_row_index_accepts_humanized_label():
    rows = [
        {"theme_code": "ипотека", "cnt": 9},
        {"theme_code": "карты", "cnt": 7},
    ]

    points = ground_chart_points(
        {
            "data": [
                {
                    "label": "Ипотека",
                    "value": 9,
                    "row_index": 0,
                    "measure": "cnt",
                },
                {"label": "Карты", "value": 7, "row_index": 1, "measure": "cnt"},
            ]
        },
        rows,
        ["theme_code", "cnt"],
    )

    assert points == [
        {"label": "Ипотека", "value": 9.0},
        {"label": "Карты", "value": 7.0},
    ]


def test_row_index_with_wrong_value_is_rejected():
    rows = [
        {"status": "завершена", "cnt": 28},
        {"status": "в работе", "cnt": 10},
    ]

    assert (
        ground_chart_points(
            {
                "data": [
                    {"label": "Завершена", "value": 28, "row_index": 0, "measure": "cnt"},
                    {"label": "В работе", "value": 999, "row_index": 1, "measure": "cnt"},
                ]
            },
            rows,
            ["status", "cnt"],
        )
        is None
    )


def test_row_index_to_unknown_measure_is_ignored():
    rows = [
        {"status": "завершена", "cnt": 28},
        {"status": "в работе", "cnt": 10},
    ]

    assert (
        ground_chart_points(
            {
                "data": [
                    {"label": "Завершена", "value": 28, "row_index": 0, "measure": "cnt"},
                    {"label": "В работе (10)", "value": 10, "row_index": 1, "measure": "missing"},
                ]
            },
            rows,
            ["status", "cnt"],
        )
        is None
    )


def test_category_value_is_returned_for_chronological_sort():
    rows = [
        {"month": "2026-01", "cnt": 3},
        {"month": "2025-12", "cnt": 5},
    ]

    points = ground_chart_points(
        {
            "category": "month",
            "data": [
                {"label": "Январь 2026", "value": 3, "row_index": 0, "measure": "cnt"},
                {"label": "Декабрь 2025", "value": 5, "row_index": 1, "measure": "cnt"},
            ],
        },
        rows,
        ["month", "cnt"],
    )

    assert points == [
        {"label": "Январь 2026", "value": 3.0, "_order_value": "2026-01"},
        {"label": "Декабрь 2025", "value": 5.0, "_order_value": "2025-12"},
    ]


def test_combined_category_is_grounded():
    rows = [
        {"theme_code": "ипотека", "pocket_year": 2025, "item_count": 41},
        {"theme_code": "ипотека", "pocket_year": 2026, "item_count": 23},
    ]

    points = ground_chart_points(
        {
            "data": [
                {"label": "ипотека · 2025", "value": 41},
                {"label": "ипотека · 2026", "value": 23},
            ]
        },
        rows,
        ["theme_code", "pocket_year", "item_count"],
    )

    assert points == [
        {"label": "ипотека · 2025", "value": 41.0},
        {"label": "ипотека · 2026", "value": 23.0},
    ]
