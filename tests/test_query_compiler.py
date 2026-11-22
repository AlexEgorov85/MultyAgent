"""Semantic layer и детерминированный QueryPlan → SQL."""

from __future__ import annotations

import pytest

from src.query import QueryCompileError, QueryFilter, QueryPlan, compile_query_plan
from src.semantic.catalog import catalog_text, get_metric, metric_ids


def test_audit_count_with_filters_compiles_to_readonly_select():
    plan = QueryPlan(
        metric="audit_count",
        filters=[
            QueryFilter(field="year", value=2026),
            QueryFilter(field="theme", value="ипотека"),
            QueryFilter(field="status", value="завершена"),
        ],
    )
    sql = compile_query_plan(plan)
    assert "SELECT count(*) AS cnt" in sql
    assert "FROM audit.audits a" in sql
    assert "p.pocket_year = 2026" in sql
    assert "p.theme_code = 'ипотека'" in sql
    assert "a.status = 'завершена'" in sql
    assert "LIMIT 200" in sql
    assert "GROUP BY" not in sql


def test_item_count_by_item_type_groups_not_filters():
    plan = QueryPlan(
        metric="item_count",
        dimensions=["item_type"],
        filters=[QueryFilter(field="year", value=2026)],
    )
    sql = compile_query_plan(plan)
    assert "i.item_type AS item_type" in sql
    assert "GROUP BY i.item_type" in sql
    assert "ORDER BY cnt DESC" in sql


def test_deviation_count_by_severity():
    sql = compile_query_plan(
        QueryPlan(metric="deviation_count", dimensions=["severity"])
    )
    assert "d.severity AS severity" in sql
    assert "GROUP BY d.severity" in sql


def test_overdue_uses_dataset_as_of_date():
    sql = compile_query_plan(
        QueryPlan(
            metric="overdue_item_count",
            filters=[QueryFilter(field="theme", value="карты")],
        )
    )
    assert "audit.as_of_date()" in sql
    assert "i.status <> 'закрыт'" in sql
    assert "p.theme_code = 'карты'" in sql


def test_run_script_mismatch_condition():
    sql = compile_query_plan(QueryPlan(metric="run_script_mismatch_count"))
    assert "r.rows_found <> s.rows_found" in sql


def test_is_repeat_boolean_filter():
    sql = compile_query_plan(
        QueryPlan(
            metric="item_count",
            filters=[QueryFilter(field="is_repeat", value=True)],
        )
    )
    assert "i.is_repeat = TRUE" in sql


def test_auditor_specialization_contains_filter():
    sql = compile_query_plan(
        QueryPlan(
            metric="auditor_count",
            filters=[
                QueryFilter(
                    field="specialization", value="ипотека", op="contains"
                )
            ],
        )
    )
    assert "au.specializations @> ARRAY['ипотека']" in sql


def test_top_titles_group_by_title():
    sql = compile_query_plan(
        QueryPlan(
            metric="deviation_count",
            dimensions=["title"],
            limit=5,
        )
    )
    assert "i.title AS title" in sql
    assert "GROUP BY i.title" in sql
    assert "LIMIT 5" in sql


def test_invalid_metric_dimension_and_value_are_rejected():
    with pytest.raises(KeyError):
        compile_query_plan(QueryPlan(metric="unknown_metric"))
    with pytest.raises(QueryCompileError):
        compile_query_plan(QueryPlan(metric="audit_count", dimensions=["severity"]))
    with pytest.raises(QueryCompileError):
        compile_query_plan(
            QueryPlan(
                metric="audit_count",
                filters=[QueryFilter(field="status", value="нет такого")],
            )
        )
    with pytest.raises(QueryCompileError):
        compile_query_plan(
            QueryPlan(
                metric="audit_count",
                filters=[QueryFilter(field="year", value="не год")],
            )
        )


def test_catalog_contains_all_metrics_and_examples():
    text = catalog_text()
    for metric_id in metric_ids():
        assert metric_id in text
        assert get_metric(metric_id).title
    assert "не придумывай SQL" in text
    assert "dimensions" in text
