"""Дополнение QueryPlan по доменным сигналам semantic layer."""

from __future__ import annotations

from src.graph.analytics_graph import missing_question_filters
from src.query import (
    QueryFilter,
    QueryPlan,
    complete_query_plan,
    template_parameters,
    template_plan_problems,
)



def _filter_pairs(plan: QueryPlan) -> set[tuple[str, object]]:
    return {(query_filter.field, query_filter.value) for query_filter in plan.filters}


def test_pocket_latest_year_and_closed_audit_are_completed():
    plan = QueryPlan(metric="audit_count")

    completed = complete_query_plan(
        "Сколько было закрыто проверок за последний год по каждому карману?",
        plan,
    )

    assert completed.dimensions == ["pocket"]
    assert ("year", "last") in _filter_pairs(completed)
    assert ("status", "завершена") in _filter_pairs(completed)


def test_multiple_statuses_are_a_breakdown_not_and_filters():
    plan = QueryPlan(metric="audit_count")

    completed = complete_query_plan(
        "Сколько проверок в 2026 году завершено, в работе, "
        "запланировано и отменено?",
        plan,
    )

    assert "status" in completed.dimensions
    assert ("year", 2026) in _filter_pairs(completed)
    status_filters = [
        query_filter
        for query_filter in completed.filters
        if query_filter.field == "status"
    ]
    assert status_filters == []


def test_multiple_years_are_a_breakdown_not_and_filters():
    plan = QueryPlan(metric="audit_count")

    completed = complete_query_plan(
        "Сколько проверок в 2025 и 2026 годах?",
        plan,
    )

    assert "year" in completed.dimensions
    assert all(
        query_filter.field != "year" for query_filter in completed.filters
    )


def test_specific_pocket_is_filter_not_breakdown():
    plan = QueryPlan(metric="audit_count")

    completed = complete_query_plan(
        "Сколько проверок в кармане 2026 года по ипотеке?", plan
    )

    assert "pocket" not in completed.dimensions
    assert ("year", 2026) in _filter_pairs(completed)


def test_kartina_is_not_a_pocket_breakdown():
    plan = QueryPlan(metric="deviation_count")

    completed = complete_query_plan("Покажи картину отклонений по годам", plan)

    assert "pocket" not in completed.dimensions
    assert "year" in completed.dimensions


def test_closed_item_uses_item_status_not_audit_status():
    plan = QueryPlan(metric="item_count")

    completed = complete_query_plan("Сколько закрытых пунктов в 2026 году?", plan)

    assert ("status", "закрыт") in _filter_pairs(completed)
    assert ("status", "завершена") not in _filter_pairs(completed)


def test_multiple_languages_are_a_breakdown():
    plan = QueryPlan(metric="script_count")

    completed = complete_query_plan(
        "Сколько скриптов на SQL, Python, R и Excel?", plan
    )

    assert "language" in completed.dimensions
    assert all(
        query_filter.field != "language" for query_filter in completed.filters
    )


def test_template_must_cover_question_dimensions():
    template_sql = (
        "SELECT status, count(*) AS cnt FROM audit.audits "
        "WHERE start_date >= make_date(%(year)s, 1, 1) "
        "GROUP BY status ORDER BY cnt DESC"
    )

    missing = missing_question_filters(
        "Сколько было закрыто проверок за последний год по каждому карману?",
        template_sql,
        {"year": 2026},
        metric_id="audit_count",
    )

    assert "разбивка по карманам" in missing
    assert "период «последний год»" in missing
    assert "статус «завершена»" in missing


def test_status_summary_covers_status_question():
    template_sql = (
        "SELECT status, count(*) AS cnt FROM audit.audits "
        "WHERE start_date >= make_date(%(year)s, 1, 1) "
        "GROUP BY status ORDER BY cnt DESC"
    )

    assert (
        missing_question_filters(
            "Покажи сводку по статусам проверок за 2026 год",
            template_sql,
            {"year": 2026},
            metric_id="audit_count",
        )
        == []
    )


def test_theme_dynamics_template_covers_theme_year_breakdown():
    template_sql = (
        "SELECT theme_code, pocket_year, item_count, critical_count, "
        "repeat_count FROM audit.v_theme_year_dynamics "
        "ORDER BY theme_code, pocket_year"
    )

    assert (
        missing_question_filters(
            "Покажи динамику по темам и годам",
            template_sql,
            metric_id="item_count",
        )
        == []
    )


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


def test_plan_does_not_duplicate_existing_filters():
    plan = QueryPlan(
        metric="audit_count",
        filters=[QueryFilter(field="year", value=2026)],
    )

    completed = complete_query_plan(
        "Сколько закрытых проверок по ипотеке в 2026 году?", plan
    )

    year_filters = [
        query_filter
        for query_filter in completed.filters
        if query_filter.field == "year"
    ]
    assert len(year_filters) == 1
    assert year_filters[0].value == 2026
