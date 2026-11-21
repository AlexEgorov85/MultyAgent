"""Проверки спецификации data-platform."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import db_runtime


def test_data_uri_recovers_missing_postmaster_info():
    class FakeServer:
        _postmaster_info = None

        def ensure_postgres_running(self):
            self.called = True
            self._postmaster_info = True

        def get_uri(self, database=None):
            assert self._postmaster_info is not None
            return f"postgresql://postgres:@127.0.0.1:1/{database or 'audit'}"

    server = FakeServer()
    db_runtime.data_uri(server)
    assert server.called is True
    assert "audit_app:@" in db_runtime.data_uri(
        server, role=db_runtime.APP_ROLE
    )


def test_repeated_migrations_keep_data(server):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.auditors "
            "(auditor_id, full_name, email, unit, position) "
            "VALUES ('TST-001', 'Тестовый Аудитор', 'tst@audit.local', "
            "'Управление аудита', 'Аудитор') "
            "ON CONFLICT (auditor_id) DO NOTHING"
        )

    result = db_runtime.apply_migrations(server)

    assert result.applied == []
    with db_runtime.connect(server) as conn:
        count = conn.execute(
            "SELECT count(*) FROM audit.auditors WHERE auditor_id = 'TST-001'"
        ).fetchone()[0]
    assert count == 1


def test_changed_migration_is_rejected(server, tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    path = migrations / "998_pytest_migration.sql"
    path.write_text("CREATE TABLE IF NOT EXISTS audit.pytest_tmp (id int);", encoding="utf-8")

    first = db_runtime.apply_migrations(server, migrations)
    assert first.applied == ["998_pytest_migration.sql"]

    path.write_text(
        "CREATE TABLE IF NOT EXISTS audit.pytest_tmp (id int, note text);",
        encoding="utf-8",
    )
    with pytest.raises(db_runtime.MigrationError, match="изменена"):
        db_runtime.apply_migrations(server, migrations)


def test_read_only_role_cannot_write(server):
    import psycopg

    with db_runtime.connect(server, role=db_runtime.READ_ONLY_ROLE) as conn:
        assert conn.execute("SELECT count(*) FROM audit.act_items").fetchone()[0] >= 0
        with pytest.raises(psycopg.Error):
            conn.execute(
                "INSERT INTO audit.auditors "
                "(auditor_id, full_name, email, unit, position) "
                "VALUES ('TST-RO', 'X', 'ro@audit.local', 'X', 'X')"
            )


def test_app_role_writes_only_memory(server):
    import psycopg

    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.auditors "
            "(auditor_id, full_name, email, unit, position) "
            "VALUES ('TST-APP', 'Тест', 'app@audit.local', 'Аудит', 'Аудитор') "
            "ON CONFLICT (auditor_id) DO NOTHING"
        )

    with db_runtime.connect(server, role=db_runtime.APP_ROLE) as conn:
        conn.execute(
            "INSERT INTO audit.auditor_memory (auditor_id, memory_key, memory_value) "
            "VALUES ('TST-APP', 'default_format', 'краткий') "
            "ON CONFLICT (auditor_id, memory_key) DO UPDATE "
            "SET memory_value = EXCLUDED.memory_value"
        )
        value = conn.execute(
            "SELECT memory_value FROM audit.auditor_memory "
            "WHERE auditor_id = 'TST-APP' AND memory_key = 'default_format'"
        ).fetchone()[0]
        assert value == "краткий"

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO audit.auditors "
                "(auditor_id, full_name, email, unit, position) "
                "VALUES ('TST-APP-2', 'X', 'app2@audit.local', 'X', 'X')"
            )


def test_seed_is_idempotent(server, tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "script_templates.csv").write_text(
        "template_id,template_key,title,description,sql_template,parameters,"
        "max_rows_default,is_active\n"
        'TPL-T1,test_one,"Тестовый шаблон","Описание","SELECT 1",{},200,true\n'
        'TPL-T2,test_two,"Второй шаблон","Описание","SELECT 2",{},200,true\n',
        encoding="utf-8",
    )
    (seed / "manifest.json").write_text(
        json.dumps(
            {"seed": 42, "sha256": "abc", "as_of_date": "2026-11-21"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    first = db_runtime.seed_from_csv(
        server, seed, tables=("audit.script_templates",)
    )
    second = db_runtime.seed_from_csv(
        server, seed, tables=("audit.script_templates",)
    )

    assert first["audit.script_templates"] == 2
    assert second["audit.script_templates"] == 2
    with db_runtime.connect(server) as conn:
        count = conn.execute(
            "SELECT count(*) FROM audit.script_templates"
        ).fetchone()[0]
    assert count == 2

    meta = db_runtime.upsert_dataset_metadata(server, seed)
    assert meta["as_of_date"] == "2026-11-21"
    with db_runtime.connect(server) as conn:
        stored = conn.execute(
            "SELECT as_of_date::text, seed, checksum FROM audit.dataset_metadata"
        ).fetchone()
    assert stored == ("2026-11-21", 42, "abc")
