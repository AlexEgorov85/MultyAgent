"""Проверки подготовки БД при сборке графа.

Реальный PostgreSQL здесь не нужен: этапы подготовки и сама сборка
подменяются через monkeypatch.
"""

from __future__ import annotations

import os
import threading

# Модуль runtime прогревает сборку при импорте; в тестах pgserver не нужен.
os.environ.setdefault("AUDIT_SKIP_DB_PREWARM", "1")

import pytest  # noqa: E402

from src import db_runtime  # noqa: E402
from src.graph import runtime  # noqa: E402


@pytest.fixture()
def isolated_build(monkeypatch):
    """Изолирует глобальное состояние сборки и подменяет тяжёлые части."""
    monkeypatch.setattr(runtime, "_ready", threading.Event())
    monkeypatch.setattr(runtime, "_result", {})
    monkeypatch.setattr(runtime, "_error", {})
    monkeypatch.setattr(runtime, "_started", True)
    monkeypatch.setattr(runtime, "_start_db_server", lambda: object())
    monkeypatch.setattr(runtime, "prepare_database", lambda server: None)
    monkeypatch.setattr(db_runtime, "get_index_embedding_model", lambda server: "")
    monkeypatch.setattr(runtime, "OpenAILLM", lambda: object())
    monkeypatch.setattr(runtime, "OpenAIEmbeddings", lambda: object())
    monkeypatch.setattr(runtime, "build_main_graph", lambda *a, **k: "main-graph")
    monkeypatch.setattr(runtime, "build_admin_graph", lambda *a, **k: "admin-graph")
    return runtime


def test_prepare_database_runs_all_stages_in_order(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        db_runtime, "ensure_database", lambda server: calls.append("ensure_database")
    )
    monkeypatch.setattr(
        db_runtime, "apply_migrations", lambda server: calls.append("apply_migrations")
    )
    monkeypatch.setattr(
        db_runtime, "ensure_roles", lambda server: calls.append("ensure_roles")
    )

    runtime.prepare_database(object())

    assert calls == ["ensure_database", "apply_migrations", "ensure_roles"]


@pytest.mark.parametrize(
    "stage", ["ensure_database", "apply_migrations", "ensure_roles"]
)
def test_prepare_database_propagates_stage_error(monkeypatch, stage):
    calls: list[str] = []

    def fail(server):
        raise db_runtime.MigrationError("миграции сломаны")

    for name in ("ensure_database", "apply_migrations", "ensure_roles"):
        if name == stage:
            monkeypatch.setattr(db_runtime, name, fail)
        else:
            monkeypatch.setattr(
                db_runtime, name, lambda server, _name=name: calls.append(_name)
            )

    with pytest.raises(RuntimeError, match=stage):
        runtime.prepare_database(object())

    # Этапы после упавшего не выполняются.
    later = {
        "ensure_database": ["apply_migrations", "ensure_roles"],
        "apply_migrations": ["ensure_roles"],
        "ensure_roles": [],
    }[stage]
    assert not any(name in calls for name in later)


def test_build_worker_reports_prepare_failure(isolated_build, monkeypatch):
    def fail(server):
        raise RuntimeError("Не удалось подготовить БД")

    monkeypatch.setattr(runtime, "prepare_database", fail)

    runtime._build_worker()

    assert runtime._ready.is_set()
    assert isinstance(runtime._error.get("exc"), RuntimeError)
    assert "graph" not in runtime._result

    # Фабрика графа поднимает сохранённую ошибку наружу.
    with pytest.raises(RuntimeError, match="подготовить"):
        runtime._wait_result("graph")


def test_build_worker_builds_graphs_after_successful_prepare(isolated_build):
    runtime._build_worker()

    assert "exc" not in runtime._error
    assert runtime._ready.is_set()
    assert runtime._result == {"graph": "main-graph", "admin_graph": "admin-graph"}


def test_build_worker_uses_hash_embeddings_for_hash_index(
    isolated_build, monkeypatch
):
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        db_runtime, "get_index_embedding_model", lambda server: "hash"
    )
    monkeypatch.setattr(runtime, "HashEmbeddings", lambda: "hash-embeddings")

    def capture(*args, **kwargs):
        calls["embeddings"] = kwargs.get("embeddings")
        return "main-graph"

    monkeypatch.setattr(runtime, "build_main_graph", capture)

    runtime._build_worker()

    assert "exc" not in runtime._error
    assert calls["embeddings"] == "hash-embeddings"
