"""Проверка покрытия условий вопроса в SQL аналитика."""

from __future__ import annotations

from src.graph.analytics_graph import (
    _aggregate_summary,
    _summary_numbers_supported,
    missing_question_filters,
)

THEMES = ["ипотека", "карты", "вклады", "расчёты"]


def test_detects_missing_theme_in_sql():
    sql = (
        "SELECT COUNT(*) AS audit_count FROM audit.audits "
        "WHERE pocket_year = 2026 AND status = 'завершена'"
    )
    missing = missing_question_filters(
        "Сколько завершённых проверок по ипотеке в 2026 году?",
        sql,
        THEMES,
    )
    assert "тема «ипотека»" in missing


def test_detects_missing_year_and_status():
    sql = "SELECT COUNT(*) FROM audit.audits WHERE theme_code = 'ипотека'"
    missing = missing_question_filters(
        "Сколько завершённых проверок по ипотеке в 2026 году?",
        sql,
        THEMES,
    )
    assert "год 2026" in missing
    assert "статус «завершена»" in missing


def test_complete_sql_has_no_missing_filters():
    sql = (
        "SELECT COUNT(*) AS audit_count FROM audit.audits AS a "
        "JOIN audit.audit_pockets AS p ON a.pocket_id = p.pocket_id "
        "WHERE p.pocket_year = 2026 AND p.theme_code = 'ипотека' "
        "AND a.status = 'завершена'"
    )
    assert (
        missing_question_filters(
            "Сколько завершённых проверок по ипотеке в 2026 году?",
            sql,
            THEMES,
        )
        == []
    )


def test_template_parameters_count_as_filters():
    sql = "SELECT * FROM audit.v_pocket_summary WHERE 1 = 1"
    parameters = {"theme_code": "ипотека", "year": 2026}
    assert (
        missing_question_filters(
            "Сколько завершённых проверок по ипотеке в 2026 году?",
            sql,
            THEMES,
            parameters,
        )
        == ["статус «завершена»"]
    )


def test_case_and_inflection_are_handled():
    sql = "SELECT 1 WHERE theme_code = 'ипотека' AND year = 2026"
    assert (
        missing_question_filters(
            "Сколько проверок по ипотеке в 2026 году?",
            sql,
            THEMES,
        )
        == []
    )


def test_detects_extra_theme_filter_not_mentioned_in_question():
    sql = (
        "SELECT p.pocket_year, p.pocket_id, count(*) AS audit_count "
        "FROM audit.audit_pockets AS p "
        "JOIN audit.audits AS a ON a.pocket_id = p.pocket_id "
        "WHERE p.theme_code = 'ипотека' "
        "GROUP BY p.pocket_year, p.pocket_id"
    )
    missing = missing_question_filters(
        "Сделай аналитику по годам и карманам",
        sql,
        THEMES,
    )
    assert "лишний фильтр темы «ипотека»" in missing


def test_closed_audit_requires_completed_status():
    sql = (
        "SELECT p.pocket_year, p.pocket_id, count(*) AS audit_count "
        "FROM audit.audit_pockets AS p "
        "JOIN audit.audits AS a ON a.pocket_id = p.pocket_id "
        "GROUP BY p.pocket_year, p.pocket_id"
    )
    missing = missing_question_filters(
        "Сделай аналитику по годам и карманам: сколько проверок было закрыто",
        sql,
        THEMES,
    )
    assert "статус «завершена» (закрытая проверка)" in missing


def test_year_and_pocket_dimensions_are_required():
    sql = "SELECT count(*) AS audit_count FROM audit.audits WHERE status = 'завершена'"
    missing = missing_question_filters(
        "Сколько закрытых проверок по годам и карманам?",
        sql,
        THEMES,
    )
    assert "разбивка по карманам" in missing
    assert "разбивка по годам" in missing


def test_complete_year_and_pocket_breakdown_is_accepted():
    sql = (
        "SELECT p.pocket_year, p.theme_code, count(*) AS completed_count "
        "FROM audit.audit_pockets AS p "
        "JOIN audit.audits AS a ON a.pocket_id = p.pocket_id "
        "WHERE a.status = 'завершена' "
        "GROUP BY p.pocket_year, p.theme_code "
        "ORDER BY p.pocket_year, p.theme_code"
    )
    assert (
        missing_question_filters(
            "Сделай аналитику по годам и карманам: сколько проверок было закрыто",
            sql,
            THEMES,
        )
        == []
    )


def test_aggregate_summary_counts_all_rows_without_llm():
    rows = [
        {"pocket_year": 2025, "theme_code": "ипотека", "closed_audits_count": 8},
        {"pocket_year": 2026, "theme_code": "ипотека", "closed_audits_count": 5},
    ]
    columns = ["pocket_year", "theme_code", "closed_audits_count"]

    summary = _aggregate_summary(rows, columns)

    assert "По годам: 2025 — 8, 2026 — 5." in summary
    assert "Всего: 13." in summary


def test_llm_numbers_outside_rows_are_rejected():
    rows = [
        {"pocket_year": 2025, "theme_code": "ипотека", "closed_audits_count": 8},
        {"pocket_year": 2026, "theme_code": "ипотека", "closed_audits_count": 5},
    ]
    columns = ["pocket_year", "theme_code", "closed_audits_count"]

    assert _summary_numbers_supported("В 2025 году — 8, в 2026 — 5.", rows, columns)
    assert not _summary_numbers_supported("Всего закрыто 31 проверка.", rows, columns)
