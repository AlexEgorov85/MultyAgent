"""Проверки спецификации conversation-memory: долгосрочный профиль."""

from __future__ import annotations

import pytest

from src import db_runtime
from src.memory import store


@pytest.fixture()
def memory_auditor(server):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.auditors "
            "(auditor_id, full_name, email, unit, position) "
            "VALUES ('MEM-001', 'Тест Память', 'mem@audit.local', 'Аудит', 'Аудитор') "
            "ON CONFLICT (auditor_id) DO NOTHING"
        )
        conn.execute("DELETE FROM audit.auditor_memory WHERE auditor_id = 'MEM-001'")
    yield "MEM-001"
    with db_runtime.connect(server) as conn:
        conn.execute("DELETE FROM audit.auditor_memory WHERE auditor_id = 'MEM-001'")
        conn.execute("DELETE FROM audit.auditors WHERE auditor_id = 'MEM-001'")


def test_profile_defaults(server, memory_auditor):
    profile = store.load_profile(server, memory_auditor)
    assert profile["default_format"] == "подробный"


def test_save_and_load_profile(server, memory_auditor):
    store.save_fact(server, memory_auditor, "focus_theme", "ипотека")
    store.save_fact(server, memory_auditor, "default_format", "краткий")

    profile = store.load_profile(server, memory_auditor)
    assert profile["focus_theme"] == "ипотека"
    assert profile["default_format"] == "краткий"
    assert "Формат: краткий" in store.profile_text(profile)


def test_profile_is_isolated_by_auditor(server, memory_auditor):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.auditors "
            "(auditor_id, full_name, email, unit, position) "
            "VALUES ('MEM-002', 'Другой Аудитор', 'mem2@audit.local', 'Аудит', 'Аудитор') "
            "ON CONFLICT (auditor_id) DO NOTHING"
        )
    try:
        store.save_fact(server, memory_auditor, "default_format", "краткий")
        other = store.load_profile(server, "MEM-002")
        assert other["default_format"] == "подробный"
    finally:
        with db_runtime.connect(server) as conn:
            conn.execute("DELETE FROM audit.auditor_memory WHERE auditor_id = 'MEM-002'")
            conn.execute("DELETE FROM audit.auditors WHERE auditor_id = 'MEM-002'")


def test_unknown_key_rejected(server, memory_auditor):
    with pytest.raises(store.MemoryError):
        store.save_fact(server, memory_auditor, "favourite_color", "синий")


def test_memory_intent_detection():
    assert store.infer_memory("Сколько проверок по ипотеке?") == {}
    facts = store.infer_memory("Я проверяю ипотеку, акт нужен в кратком формате")
    assert facts == {"focus_theme": "ипотека", "default_format": "краткий"}
