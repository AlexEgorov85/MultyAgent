"""Проверки спецификации data-platform."""

from __future__ import annotations

import json
from datetime import date
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
    checksum = db_runtime.seed_checksum(seed)
    (seed / "manifest.json").write_text(
        json.dumps(
            {
                "seed": 42,
                "sha256": checksum,
                "as_of_date": "2026-11-21",
            },
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
    assert stored == ("2026-11-21", 42, checksum)

    db_runtime.set_index_embedding_model(server, "hash")
    assert db_runtime.get_index_embedding_model(server) == "hash"
    db_runtime.set_index_embedding_model(server, "")
    assert db_runtime.get_index_embedding_model(server) == ""


def test_seed_checksum_mismatch_is_rejected_and_can_be_forced(
    server, tmp_path
):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "script_templates.csv").write_text(
        "template_id,template_key,title,description,sql_template,parameters,"
        "max_rows_default,is_active\n"
        'TPL-C1,checksum_one,"Шаблон","Описание","SELECT 1",{},200,true\n',
        encoding="utf-8",
    )
    (seed / "manifest.json").write_text(
        json.dumps(
            {
                "seed": 42,
                "sha256": "0" * 64,
                "as_of_date": "2026-11-21",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(db_runtime.SeedChecksumError, match="manifest"):
        db_runtime.seed_from_csv(
            server, seed, tables=("audit.script_templates",)
        )

    counts = db_runtime.seed_from_csv(
        server,
        seed,
        tables=("audit.script_templates",),
        allow_checksum_mismatch=True,
    )
    assert counts["audit.script_templates"] == 1

    (seed / "manifest.json").write_text(
        json.dumps(
            {
                "seed": 42,
                "sha256": db_runtime.seed_checksum(seed),
                "as_of_date": "2026-11-21",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    counts = db_runtime.seed_from_csv(
        server, seed, tables=("audit.script_templates",)
    )
    assert counts["audit.script_templates"] == 1

    with (seed / "script_templates.csv").open("a", encoding="utf-8") as fh:
        fh.write(
            'TPL-C2,checksum_two,"Шаблон 2","Описание","SELECT 2",{},200,true\n'
        )
    with pytest.raises(db_runtime.SeedChecksumError, match="manifest"):
        db_runtime.seed_from_csv(
            server, seed, tables=("audit.script_templates",)
        )
    counts = db_runtime.seed_from_csv(
        server,
        seed,
        tables=("audit.script_templates",),
        allow_checksum_mismatch=True,
    )
    assert counts["audit.script_templates"] == 2


def _insert_asof_chain(conn) -> None:
    conn.execute(
        "INSERT INTO audit.auditors "
        "(auditor_id, full_name, email, unit, position) "
        "VALUES ('ASOF-AUD', 'Тест Среза', 'asof@audit.local', "
        "'Управление аудита', 'Аудитор') "
        "ON CONFLICT (auditor_id) DO NOTHING"
    )
    conn.execute(
        "INSERT INTO audit.audit_pockets "
        "(pocket_id, pocket_year, theme_code, title, owner_unit, "
        " period_start, period_end, planned_audit_count) "
        "VALUES ('ASOF-PKT', 2026, 'ипотека', 'Карман среза', "
        "        'Управление аудита', '2026-01-01', '2026-12-31', 5) "
        "ON CONFLICT (pocket_id) DO NOTHING"
    )
    conn.execute(
        "INSERT INTO audit.audits "
        "(audit_id, pocket_id, audit_code, title, audit_type, start_date, "
        " end_date, status, lead_auditor_id, team_size) "
        "VALUES ('ASOF-AUDIT', 'ASOF-PKT', 'ASOF-AUDIT', 'Проверка среза', "
        "        'плановая', '2026-01-10', '2026-01-20', 'завершена', "
        "        'ASOF-AUD', 2) "
        "ON CONFLICT (audit_id) DO NOTHING"
    )
    conn.execute(
        "INSERT INTO audit.acts "
        "(act_id, audit_id, act_number, act_date, status) "
        "VALUES ('ASOF-ACT', 'ASOF-AUDIT', 'ASOF-ACT', '2026-01-25', "
        "        'черновик') "
        "ON CONFLICT (act_id) DO NOTHING"
    )
    conn.execute(
        "INSERT INTO audit.act_items "
        "(item_id, act_id, item_number, item_type, test_type, title, "
        " test_description, risk_level, status, deadline, order_index, "
        " finding_template_key, finding_scope) "
        "VALUES ('ASOF-ITEM', 'ASOF-ACT', '1.1', 'отклонение', 'опрос', "
        "        'Пункт среза', 'Проверка даты среза', 'высокий', "
        "        'открыт', DATE '2021-01-01', 1, 'ASOF-TPL', 'срез') "
        "ON CONFLICT (item_id) DO NOTHING"
    )


def _drop_asof_chain(conn) -> None:
    conn.execute("DELETE FROM audit.audits WHERE audit_id = 'ASOF-AUDIT'")
    conn.execute("DELETE FROM audit.audit_pockets WHERE pocket_id = 'ASOF-PKT'")
    conn.execute("DELETE FROM audit.auditors WHERE auditor_id = 'ASOF-AUD'")
    conn.execute("DELETE FROM audit.act_items WHERE item_id = 'ASOF-ITEM'")


def test_overdue_uses_dataset_as_of_date_not_system_clock(server):
    with db_runtime.connect(server) as conn:
        previous = conn.execute(
            "SELECT as_of_date, seed, checksum FROM audit.dataset_metadata "
            "WHERE metadata_id = 1"
        ).fetchone()
        _drop_asof_chain(conn)
        _insert_asof_chain(conn)

    try:
        with db_runtime.connect(server) as conn:
            conn.execute(
                "INSERT INTO audit.dataset_metadata "
                "(metadata_id, as_of_date, seed, checksum) "
                "VALUES (1, DATE '2020-01-01', 42, 'test') "
                "ON CONFLICT (metadata_id) DO UPDATE "
                "SET as_of_date = EXCLUDED.as_of_date"
            )
            assert conn.execute("SELECT audit.as_of_date()").fetchone()[0] == date(
                2020, 1, 1
            )
            overdue, days = conn.execute(
                "SELECT is_overdue, days_overdue FROM audit.v_open_items "
                "WHERE item_id = 'ASOF-ITEM'"
            ).fetchone()
            assert overdue is False
            assert days < 0
            pocket_overdue = conn.execute(
                "SELECT overdue_count FROM audit.v_pocket_summary "
                "WHERE pocket_id = 'ASOF-PKT'"
            ).fetchone()[0]
            assert pocket_overdue == 0

            conn.execute(
                "UPDATE audit.dataset_metadata SET as_of_date = DATE '2022-01-01' "
                "WHERE metadata_id = 1"
            )
            overdue, days = conn.execute(
                "SELECT is_overdue, days_overdue FROM audit.v_open_items "
                "WHERE item_id = 'ASOF-ITEM'"
            ).fetchone()
            assert overdue is True
            assert days > 0
            pocket_overdue = conn.execute(
                "SELECT overdue_count FROM audit.v_pocket_summary "
                "WHERE pocket_id = 'ASOF-PKT'"
            ).fetchone()[0]
            assert pocket_overdue == 1

            conn.execute("DELETE FROM audit.dataset_metadata")
            fallback = conn.execute("SELECT audit.as_of_date()").fetchone()[0]
            assert fallback == date(2026, 11, 21)

        with db_runtime.connect(
            server, role=db_runtime.READ_ONLY_ROLE
        ) as ro_conn:
            fallback = ro_conn.execute("SELECT audit.as_of_date()").fetchone()[0]
            assert fallback == date(2026, 11, 21)
            overdue = ro_conn.execute(
                "SELECT is_overdue FROM audit.v_open_items "
                "WHERE item_id = 'ASOF-ITEM'"
            ).fetchone()[0]
            assert overdue is True
    finally:
        with db_runtime.connect(server) as conn:
            _drop_asof_chain(conn)
            conn.execute("DELETE FROM audit.dataset_metadata")
            if previous is not None:
                conn.execute(
                    "INSERT INTO audit.dataset_metadata "
                    "(metadata_id, as_of_date, seed, checksum) "
                    "VALUES (1, %s, %s, %s)",
                    previous,
                )
