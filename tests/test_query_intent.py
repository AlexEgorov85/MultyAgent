"""Применение LLM-проверки плана к QueryPlan."""

from __future__ import annotations

from src.query import (
    PlanFilter,
    PlanGaps,
    QueryFilter,
    QueryPlan,
    apply_plan_gaps,
    template_parameters,
    template_plan_problems,
)


def _filter_pairs(plan: QueryPlan) -> set[tuple[str, object]]:
    return {(query_filter.field, query_filter.value) for query_filter in plan.filters}


def test_pocket_latest_year_and_closed_audit_are_added():
    plan = QueryPlan(metric="audit_count")
    gaps = PlanGaps(
        missing_dimensions=["pocket"],
        missing_filters=[PlanFilter(field="status", value="завершена")],
        period="last_year",
    )

    completed = apply_plan_gaps(plan, gaps)

    assert completed.dimensions == ["pocket"]
    assert ("year", "last") in _filter_pairs(completed)
    assert ("status", "завершена") in _filter_pairs(completed)


def test_multiple_statuses_become_dimension():
    plan = QueryPlan(metric="audit_count")
    gaps = PlanGaps(
        missing_filters=[
            PlanFilter(field="status", value="завершена"),
            PlanFilter(field="status", value="отменена"),
        ],
        period="year",
        year=2026,
    )

    completed = apply_plan_gaps(plan, gaps)

    assert "status" in completed.dimensions
    assert all(
        query_filter.field != "status" for query_filter in completed.filters
    )
    assert ("year", 2026) in _filter_pairs(completed)


def test_multiple_years_become_dimension():
    plan = QueryPlan(metric="audit_count")
    gaps = PlanGaps(
        missing_filters=[PlanFilter(field="year", value="2025, 2026")],
    )

    completed = apply_plan_gaps(plan, gaps)

    assert "year" in completed.dimensions
    assert all(
        query_filter.field != "year" for query_filter in completed.filters
    )


def test_specialization_uses_contains():
    plan = QueryPlan(metric="auditor_count")
    gaps = PlanGaps(
        missing_filters=[
            PlanFilter(field="specialization", value="ипотека")
        ]
    )

    completed = apply_plan_gaps(plan, gaps)

    specialization = [
        query_filter
        for query_filter in completed.filters
        if query_filter.field == "specialization"
    ]
    assert len(specialization) == 1
    assert specialization[0].value == "ипотека"
    assert specialization[0].op == "contains"


def test_invalid_dimension_and_value_are_ignored():
    plan = QueryPlan(metric="audit_count")
    gaps = PlanGaps(
        missing_dimensions=["severity", "unknown"],
        missing_filters=[
            PlanFilter(field="theme", value="криптовалюта"),
            PlanFilter(field="status", value="нет такого"),
        ],
    )

    completed = apply_plan_gaps(plan, gaps)

    assert completed.dimensions == []
    assert completed.filters == []


def test_last_n_years_period_adds_range_filter():
    plan = QueryPlan(metric="audit_count")
    gaps = PlanGaps(last_years=2, period="last_years")

    completed = apply_plan_gaps(plan, gaps)

    assert ("year", "last_2") in _filter_pairs(completed)


def test_chart_can_use_month_dimension():
    plan = QueryPlan(metric="audit_count")
    gaps = PlanGaps(
        missing_dimensions=["month"],
        missing_filters=[PlanFilter(field="status", value="завершена")],
        last_years=2,
    )

    completed = apply_plan_gaps(plan, gaps)

    assert "month" in completed.dimensions
    assert ("status", "завершена") in _filter_pairs(completed)
    assert ("year", "last_2") in _filter_pairs(completed)


def test_existing_filters_are_not_duplicated():
    plan = QueryPlan(
        metric="audit_count",
        filters=[QueryFilter(field="year", value=2026)],
    )
    gaps = PlanGaps(
        missing_filters=[PlanFilter(field="year", value="2026")],
        period="year",
        year=2026,
    )

    completed = apply_plan_gaps(plan, gaps)

    year_filters = [
        query_filter
        for query_filter in completed.filters
        if query_filter.field == "year"
    ]
    assert len(year_filters) == 1
    assert year_filters[0].value == 2026


def test_template_contract_accepts_matching_plan():
    plan = QueryPlan(
        metric="audit_count",
        dimensions=["status"],
        template_key="status_summary",
    )

    assert template_plan_problems("status_summary", plan) == []
    assert template_parameters("status_summary", plan, 2026) == {"year": 2026}


def test_template_contract_rejects_wrong_metric_and_dimensions():
    plan = QueryPlan(
        metric="item_count",
        dimensions=["pocket"],
        filters=[QueryFilter(field="status", value="завершена")],
        template_key="status_summary",
    )

    problems = template_plan_problems("status_summary", plan)

    assert any("метрику" in problem for problem in problems)
    assert any("разрезы" in problem for problem in problems)
    assert any("фильтры" in problem for problem in problems)


def test_query_plan_tolerates_llm_shape_noise():
    plan = QueryPlan.model_validate(
        {
            "metric": "item_count",
            "dimensions": None,
            "filters": None,
            "order_by": [{"field": "year", "direction": "asc"}],
            "limit": None,
            "template_key": None,
            "reason": None,
        }
    )

    assert plan.dimensions == []
    assert plan.filters == []
    assert plan.order_by == "none"
    assert plan.limit == 200
    assert plan.template_key == ""
    assert plan.reason == ""
