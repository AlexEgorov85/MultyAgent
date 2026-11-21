"""Общие фикстуры: один PostgreSQL-сервер на тестовую сессию."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db_runtime  # noqa: E402


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    db_runtime.ensure_ascii_pg_install()
    pgdata = tmp_path_factory.mktemp("pgdata")
    srv = db_runtime.start_server(pgdata, cleanup_mode="delete")
    db_runtime.ensure_database(srv)
    db_runtime.apply_migrations(srv)
    db_runtime.ensure_roles(srv)
    yield srv
    srv.cleanup()
