"""Единые подписи и форматирование без правил по имени колонки."""

from __future__ import annotations

from decimal import Decimal

from src.display import (
    display_label,
    format_value,
    headline_column,
    headline_label,
)


def test_headline_ignores_year_dimension():
    row = {
        "pocket_year": 2026,
        "theme_code": "ипотека",
        "status": "завершена",
        "audit_count": 5,
    }
    columns = ["pocket_year", "theme_code", "status", "audit_count"]

    assert headline_column(row, columns) == "audit_count"


def test_headline_is_not_chosen_from_alias_list():
    row = {"total_items": 67, "critical_items": 5, "critical_share": Decimal("0.0746")}

    assert headline_column(row, list(row)) is None


def test_metric_label_wins_over_generic_cnt():
    assert headline_label("cnt", "deviation_gap_max", "ru") == "Разрыв с порогом"
    assert headline_label("cnt", "", "ru") == "Всего"


def test_share_value_is_not_formatted_as_percent_by_column_name():
    assert format_value(Decimal("0.0746"), "critical_share", "ru") == "0,0746"


def test_unknown_column_is_humanized():
    assert display_label("items_without_scripts", "ru") == "Items without scripts"


def test_decimal_is_number_for_formatting():
    assert format_value(Decimal("67"), "total_items", "ru") == "67"
