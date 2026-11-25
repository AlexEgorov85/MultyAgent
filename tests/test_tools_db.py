"""Проверки спецификации sql-safety: выполнение и шаблоны."""

from __future__ import annotations

import pytest

from src import db_runtime
from src.tools import db as db_tools
from src.tools.sql_guard import UnsafeSQLError


@pytest.fixture()
def sample_data(server):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.auditors "
            "(auditor_id, full_name, email, unit, position) "
            "VALUES ('SQL-001', 'Тест SQL', 'sql@audit.local', 'Аудит', 'Аудитор') "
            "ON CONFLICT (auditor_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.audit_pockets "
            "(pocket_id, pocket_year, theme_code, title, owner_unit, "
            " period_start, period_end, planned_audit_count) "
            "VALUES ('PKT-TEST-SQL', 2026, 'ипотека', 'Тестовый карман', "
            "        'Аудит', '2026-01-01', '2026-12-31', 5) "
            "ON CONFLICT (pocket_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.audits "
            "(audit_id, pocket_id, audit_code, title, audit_type, start_date, "
            " end_date, status, lead_auditor_id, team_size) "
            "VALUES ('AUD-TEST-SQL', 'PKT-TEST-SQL', 'AUD-TEST-SQL', "
            "        'Тестовая проверка', 'плановая', '2026-02-01', "
            "        '2026-02-20', 'завершена', 'SQL-001', 2) "
            "ON CONFLICT (audit_id) DO NOTHING"
        )
    yield
    with db_runtime.connect(server) as conn:
        conn.execute("DELETE FROM audit.audits WHERE audit_id = 'AUD-TEST-SQL'")
        conn.execute("DELETE FROM audit.audit_pockets WHERE pocket_id = 'PKT-TEST-SQL'")
        conn.execute("DELETE FROM audit.auditors WHERE auditor_id = 'SQL-001'")


def test_run_readonly_sql(server, sample_data):
    result = db_tools.run_readonly_sql(
        server,
        "SELECT audit_id, status FROM audit.audits WHERE audit_id = 'AUD-TEST-SQL'",
    )
    assert result["columns"] == ["audit_id", "status"]
    assert result["rows"] == [{"audit_id": "AUD-TEST-SQL", "status": "завершена"}]
    assert result["row_count"] == 1
    assert result["truncated"] is False
    assert "LIMIT" in result["sql"].upper()


def test_run_readonly_sql_rejects_write(server, sample_data):
    with pytest.raises(UnsafeSQLError):
        db_tools.run_readonly_sql(server, "DELETE FROM audit.audits")


def test_run_readonly_sql_honours_max_rows(server, sample_data):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.audits "
            "(audit_id, pocket_id, audit_code, title, audit_type, start_date, "
            " end_date, status, lead_auditor_id, team_size) "
            "VALUES ('AUD-TEST-SQL-2', 'PKT-TEST-SQL', 'AUD-TEST-SQL-2', "
            "        'Вторая проверка', 'плановая', '2026-03-01', "
            "        '2026-03-20', 'завершена', 'SQL-001', 2) "
            "ON CONFLICT (audit_id) DO NOTHING"
        )
    try:
        result = db_tools.run_readonly_sql(
            server, "SELECT audit_id FROM audit.audits", max_rows=1
        )
        assert result["row_count"] == 1
        assert result["truncated"] is True
        assert "LIMIT 1" in result["sql"].upper()
    finally:
        with db_runtime.connect(server) as conn:
            conn.execute(
                "DELETE FROM audit.audits WHERE audit_id = 'AUD-TEST-SQL-2'"
            )


def test_statement_timeout_is_set(server, sample_data):
    result = db_tools.run_readonly_sql(
        server, "SELECT current_setting('statement_timeout') AS timeout"
    )
    assert result["rows"][0]["timeout"] in {"5s", "5000ms"}


def test_template_with_parameters(server, sample_data):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.script_templates "
            "(template_id, template_key, title, description, sql_template, "
            " parameters, max_rows_default, is_active) "
            "VALUES ('TPL-TEST', 'test_status', 'Тест', 'Описание', "
            "        'SELECT count(*) AS cnt FROM audit.audits "
            "         WHERE status = %(status)s', "
            "        '{\"status\": \"завершена\"}', 50, true) "
            "ON CONFLICT (template_id) DO UPDATE SET sql_template = EXCLUDED.sql_template"
        )
    try:
        result = db_tools.run_script_template(
            server, "test_status", {"status": "завершена"}
        )
        assert result["rows"][0]["cnt"] >= 1
    finally:
        with db_runtime.connect(server) as conn:
            conn.execute(
                "DELETE FROM audit.script_templates WHERE template_id = 'TPL-TEST'"
            )


def test_template_missing_parameters(server, sample_data):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.script_templates "
            "(template_id, template_key, title, description, sql_template, "
            " parameters, max_rows_default, is_active) "
            "VALUES ('TPL-TEST2', 'test_required', 'Тест', 'Описание', "
            "        'SELECT count(*) FROM audit.audits WHERE status = %(status)s', "
            "        '{\"status\": \"завершена\"}', 50, true) "
            "ON CONFLICT (template_id) DO NOTHING"
        )
    try:
        with pytest.raises(db_tools.ExecutionError, match="Не хватает параметров"):
            db_tools.run_script_template(server, "test_required", {})
    finally:
        with db_runtime.connect(server) as conn:
            conn.execute(
                "DELETE FROM audit.script_templates WHERE template_id = 'TPL-TEST2'"
            )


def test_script_templates_use_readonly_role(server, monkeypatch):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.script_templates "
            "(template_id, template_key, title, description, sql_template, "
            " parameters, max_rows_default, is_active) "
            "VALUES ('TPL-RO', 'test_readonly_role', 'Тест', 'Описание', "
            "        'SELECT count(*) AS cnt FROM audit.audits', '{}', 50, true) "
            "ON CONFLICT (template_id) DO UPDATE "
            "SET sql_template = EXCLUDED.sql_template, is_active = true"
        )

    roles: list[str] = []
    original_connect = db_runtime.connect

    def recording_connect(server_, **kwargs):
        roles.append(kwargs.get("role", db_runtime.ADMIN_ROLE))
        return original_connect(server_, **kwargs)

    monkeypatch.setattr(db_runtime, "connect", recording_connect)
    try:
        listed = db_tools.list_script_templates(server)
        assert any(row["template_key"] == "test_readonly_role" for row in listed)

        result = db_tools.run_script_template(server, "test_readonly_role")
        assert result["rows"][0]["cnt"] >= 0
    finally:
        with original_connect(server) as conn:
            conn.execute(
                "DELETE FROM audit.script_templates WHERE template_id = 'TPL-RO'"
            )

    assert roles, "tools did not open a connection"
    assert set(roles) == {db_runtime.READ_ONLY_ROLE}
    assert db_runtime.ADMIN_ROLE not in roles


def test_tool_plan_accepts_string_calls_and_missing_arguments():
    from src.schemas import ToolPlan

    plan = ToolPlan.model_validate(
        {"calls": ["get_act_items", {"name": "search_acts", "arguments": None}]}
    )

    assert [call.name for call in plan.calls] == ["get_act_items", "search_acts"]
    assert plan.calls[0].arguments.as_call_arguments() == {}
    assert plan.calls[1].arguments.as_call_arguments() == {}


def test_tool_call_parses_arguments_from_name():
    from src.graph.analytics_graph import _split_tool_call

    name, arguments = _split_tool_call(
        "get_act_items(audit_code=AUD-2025-DEPOSITS-06, item_type=проблема)"
    )

    assert name == "get_act_items"
    assert arguments == {
        "audit_code": "AUD-2025-DEPOSITS-06",
        "item_type": "проблема",
    }


def test_display_sql_substitutes_template_parameters():
    from src.tools.db import _display_sql

    sql = (
        "SELECT count(*) FROM audit.audits "
        "WHERE start_date >= MAKE_DATE(%(year)s, 1, 1)"
    )

    displayed = _display_sql(sql, {"year": 2026})

    assert "2026" in displayed
    assert "%(year)s" not in displayed

def test_schema_documents_date_arithmetic():
    from src.tools.db import get_schema

    schema = get_schema()

    assert "date - date" in schema
    assert "EXTRACT(EPOCH FROM closed_at - deadline)" in schema
