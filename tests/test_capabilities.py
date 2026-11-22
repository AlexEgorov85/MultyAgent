"""Deterministic capability matcher."""

from __future__ import annotations

from src.capabilities import match_capability


def _id(question, slots=None):
    match = match_capability(question, slots)
    return match.capability.id if match else None


def test_matches_explicit_template_questions():
    assert _id("Покажи сводку по статусам проверок за 2026 год") == "status_summary"
    assert _id("Покажи топ-5 видов отклонений") == "top_findings"
    assert _id("Покажи динамику по темам и годам") == "theme_dynamics"
    assert _id("Покажи пункты без приложенных скриптов") == "items_without_scripts"
    assert _id("Покажи просроченные открытые пункты") == "overdue_items"
    assert _id("Покажи риски по карманам") == "risk_by_pocket"


def test_does_not_confuse_counts_with_templates():
    assert _id("Сколько проверок по статусам?") is None
    assert _id("Сколько актов находятся в статусе черновик?") is None
    assert _id("Сколько пунктов с критическим риском в 2026 году?") is None
    assert _id("Сколько запусков скриптов завершились ошибкой?") is None
    assert _id("Сколько проверок в 2026 году завершено, в работе, запланировано?") is None


def test_parameters_are_extracted():
    match = match_capability("Покажи сводку по статусам проверок за 2025 год")
    assert match is not None
    assert match.parameters == {"year": 2025}

    match = match_capability("Покажи топ-3 видов отклонений")
    assert match is not None
    assert match.parameters["limit"] == 3
    assert match.parameters["date_from"].endswith("-01-01")

    match = match_capability("Покажи топ-5 видов отклонений за 2025 год")
    assert match is not None
    assert match.parameters["date_from"] == "2025-01-01"
    assert match.parameters["limit"] == 5


def test_slots_can_supply_year():
    match = match_capability(
        "Покажи сводку по статусам проверок",
        {"year": 2024},
    )
    assert match is not None
    assert match.parameters == {"year": 2024}
