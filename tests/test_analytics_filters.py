"""Проверка покрытия условий вопроса в SQL аналитика."""

from __future__ import annotations

from src.graph.analytics_graph import missing_question_filters

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
