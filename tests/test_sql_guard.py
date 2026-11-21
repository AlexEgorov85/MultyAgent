"""Проверки спецификации sql-safety: валидатор."""

from __future__ import annotations

import pytest

from src.tools.sql_guard import UnsafeSQLError, validate_readonly_sql


def test_simple_select_gets_limit():
    sql = validate_readonly_sql("SELECT audit_id FROM audit.audits", max_rows=200)
    assert "LIMIT 200" in sql.upper()


def test_cte_is_allowed():
    sql = "WITH recent AS (SELECT * FROM audit.audits) SELECT count(*) FROM recent"
    assert "LIMIT" in validate_readonly_sql(sql, max_rows=10).upper()


def test_unqualified_table_is_allowed():
    assert validate_readonly_sql("SELECT count(*) FROM acts", max_rows=5)


def test_large_limit_is_reduced():
    sql = validate_readonly_sql(
        "SELECT audit_id FROM audit.audits LIMIT 100000", max_rows=200
    )
    assert "LIMIT 200" in sql.upper()


def test_one_of_multiple_statements_rejected():
    with pytest.raises(UnsafeSQLError, match="ровно один"):
        validate_readonly_sql("SELECT 1; DROP TABLE audit.acts")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM audit.act_items",
        "UPDATE audit.acts SET status = 'закрыт'",
        "INSERT INTO audit.auditors (auditor_id) VALUES ('X')",
        "DROP TABLE audit.acts",
        "ALTER TABLE audit.acts ADD COLUMN x int",
        "CREATE TABLE audit.x (id int)",
        "TRUNCATE audit.acts",
        "COPY audit.acts FROM PROGRAM 'cmd'",
        "SELECT * INTO audit.copied FROM audit.acts",
        "SELECT * FROM audit.acts FOR UPDATE",
        "CALL audit.some_proc()",
        "DO $$ BEGIN END $$",
    ],
)
def test_write_operations_rejected(sql):
    with pytest.raises(UnsafeSQLError):
        validate_readonly_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM public.pg_authid",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM pg_catalog.pg_user",
        "SELECT * FROM other_schema.table1",
    ],
)
def test_foreign_schemas_rejected(sql):
    with pytest.raises(UnsafeSQLError, match="Схема вне allowlist"):
        validate_readonly_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_sleep(10)",
        "SELECT pg_ls_dir('.')",
        "SELECT dblink('host=evil', 'select 1')",
    ],
)
def test_dangerous_functions_rejected(sql):
    with pytest.raises(UnsafeSQLError):
        validate_readonly_sql(sql)


def test_unknown_table_rejected():
    with pytest.raises(UnsafeSQLError, match="вне allowlist"):
        validate_readonly_sql("SELECT * FROM audit.secret_table")


def test_empty_sql_rejected():
    with pytest.raises(UnsafeSQLError):
        validate_readonly_sql("   ")
