"""Проверка структурных условий вопроса в SQL аналитика."""

from __future__ import annotations

from src.graph.analytics_graph import (
    _summary_numbers_supported,
    missing_question_filters,
)


def test_theme_words_are_not_inferred_by_code():
    sql = (
        "SELECT COUNT(*) AS audit_count FROM audit.audits "
        "WHERE pocket_year = 2026 AND status = 'завершена'"
    )
    # Тема «ипотека» есть в вопросе, но это семантика: LLM-планировщик
    # отвечает за фильтр, код не угадывает его по словам.
    assert (
        missing_question_filters(
            "Сколько завершённых проверок по ипотеке в 2026 году?",
            sql,
        )
        == []
    )


def test_detects_missing_year_only():
    sql = "SELECT COUNT(*) FROM audit.audits WHERE theme_code = 'ипотека'"
    missing = missing_question_filters(
        "Сколько завершённых проверок по ипотеке в 2026 году?",
        sql,
    )
    assert missing == ["год 2026"]


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
            parameters,
        )
        == []
    )


def test_case_and_inflection_are_handled():
    sql = "SELECT 1 WHERE theme_code = 'ипотека' AND year = 2026"
    assert (
        missing_question_filters(
            "Сколько проверок по ипотеке в 2026 году?",
            sql,
        )
        == []
    )


def test_theme_homonyms_do_not_trigger_repairs():
    """«Картина отклонений» — не повод требовать фильтр темы «карты»."""
    sql = (
        "SELECT p.pocket_year, count(*) AS audit_count "
        "FROM audit.audit_pockets AS p "
        "GROUP BY p.pocket_year"
    )
    assert (
        missing_question_filters(
            "Покажи картину отклонений по годам",
            sql,
        )
        == []
    )


def test_status_words_are_not_checked_by_code():
    sql = (
        "SELECT p.pocket_year, p.pocket_id, count(*) AS audit_count "
        "FROM audit.audit_pockets AS p "
        "JOIN audit.audits AS a ON a.pocket_id = p.pocket_id "
        "GROUP BY p.pocket_year, p.pocket_id"
    )
    # «Закрыто» — семантика: код не требует конкретного status в SQL.
    assert (
        missing_question_filters(
            "Сделай аналитику по годам и карманам: сколько проверок было закрыто",
            sql,
        )
        == []
    )


def test_year_and_pocket_dimensions_are_required():
    sql = "SELECT count(*) AS audit_count FROM audit.audits WHERE status = 'завершена'"
    missing = missing_question_filters(
        "Сколько закрытых проверок по годам и карманам?",
        sql,
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
        )
        == []
    )


def test_llm_numbers_outside_rows_are_rejected():
    rows = [
        {"pocket_year": 2025, "theme_code": "ипотека", "closed_audits_count": 8},
        {"pocket_year": 2026, "theme_code": "ипотека", "closed_audits_count": 5},
    ]
    columns = ["pocket_year", "theme_code", "closed_audits_count"]

    assert _summary_numbers_supported("В 2025 году — 8, в 2026 — 5.", rows, columns)
    assert not _summary_numbers_supported("Всего закрыто 31 проверка.", rows, columns)
