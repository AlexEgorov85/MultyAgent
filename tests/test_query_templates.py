"""Контракты готовых SQL-шаблонов."""

from __future__ import annotations

from src.query.plan import QueryFilter, QueryPlan
from src.query.templates import template_parameters, template_plan_problems


def test_status_summary_accepts_single_latest_year():
    plan = QueryPlan(
        metric="audit_count",
        dimensions=["status"],
        filters=[QueryFilter(field="year", value="last")],
    )

    assert template_plan_problems("status_summary", plan) == []
    assert template_parameters("status_summary", plan, 2026) == {"year": 2026}


def test_status_summary_rejects_last_n_years():
    for value in ("last_2", "last_2_years"):
        plan = QueryPlan(
            metric="audit_count",
            dimensions=["status"],
            filters=[QueryFilter(field="year", value=value)],
        )

        problems = template_plan_problems("status_summary", plan)

        assert any("диапазон лет" in problem for problem in problems)


def test_top_findings_rejects_last_n_years():
    plan = QueryPlan(
        metric="deviation_count",
        dimensions=["title"],
        filters=[QueryFilter(field="year", value="last_3")],
    )

    problems = template_plan_problems("top_findings", plan)

    assert any("диапазон лет" in problem for problem in problems)
