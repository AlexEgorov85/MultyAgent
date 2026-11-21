"""Тесты служебного графа управления чатами."""

from __future__ import annotations

import pytest

from src import db_runtime, dialogue_store
from src.graph.admin_graph import build_admin_graph


def _seed_thread(
    server, conversation_id: str, auditor_id: str = "ADMIN-001"
) -> None:
    dialogue_store.append_turn(
        server,
        conversation_id=conversation_id,
        auditor_id=auditor_id,
        turn_id=f"{conversation_id}-turn-1",
        user_text="Сколько проверок?",
        assistant_text="Всего: 1.",
        trace=[],
        resolved_query="Сколько проверок?",
    )


def _thread_exists(server, conversation_id: str) -> bool:
    with db_runtime.connect(server) as conn:
        row = conn.execute(
            "SELECT 1 FROM audit.chat_threads WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()
    return row is not None


def _thread_title(server, conversation_id: str) -> str | None:
    with db_runtime.connect(server) as conn:
        row = conn.execute(
            "SELECT title FROM audit.chat_threads WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()
    return row[0] if row is not None else None


def test_admin_renames_and_deletes_thread_with_messages(server):
    conversation_id = "admin-chat-rename-delete"
    _seed_thread(server, conversation_id)
    graph = build_admin_graph(server)

    renamed = graph.invoke(
        {
            "action": "rename",
            "conversation_id": conversation_id,
            "title": "  Новое   название  ",
            "auditor_id": "ADMIN-001",
        }
    )
    assert renamed["ok"] is True

    assert _thread_title(server, conversation_id) == "Новое название"

    deleted = graph.invoke(
        {
            "action": "delete",
            "conversation_id": conversation_id,
            "auditor_id": "ADMIN-001",
        }
    )
    assert deleted["ok"] is True

    with db_runtime.connect(server) as conn:
        threads = conn.execute(
            "SELECT count(*) FROM audit.chat_threads WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()[0]
        messages = conn.execute(
            "SELECT count(*) FROM audit.chat_messages WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()[0]
    assert threads == 0
    assert messages == 0


def test_admin_rejects_bad_actions_and_empty_title(server):
    graph = build_admin_graph(server)

    assert (
        graph.invoke(
            {
                "action": "rename",
                "conversation_id": "admin-chat-empty",
                "title": "   ",
            }
        )["ok"]
        is False
    )
    assert graph.invoke({"action": "delete", "conversation_id": ""})["ok"] is False
    assert (
        graph.invoke(
            {"action": "unknown", "conversation_id": "admin-chat-empty"}
        )["ok"]
        is False
    )


def test_admin_rejects_delete_by_another_auditor(server):
    conversation_id = "admin-chat-foreign-delete"
    _seed_thread(server, conversation_id)
    graph = build_admin_graph(server)

    result = graph.invoke(
        {
            "action": "delete",
            "conversation_id": conversation_id,
            "auditor_id": "ADMIN-002",
        }
    )

    assert result["ok"] is False
    assert "another auditor" in result["error"]
    assert _thread_exists(server, conversation_id)


def test_admin_rejects_rename_by_another_auditor(server):
    conversation_id = "admin-chat-foreign-rename"
    _seed_thread(server, conversation_id)
    graph = build_admin_graph(server)

    result = graph.invoke(
        {
            "action": "rename",
            "conversation_id": conversation_id,
            "title": "Захваченное название",
            "auditor_id": "ADMIN-002",
        }
    )

    assert result["ok"] is False
    assert "another auditor" in result["error"]
    assert _thread_title(server, conversation_id) == "Сколько проверок?"


def test_admin_owner_can_rename_and_delete_own_chat(server):
    conversation_id = "admin-chat-owner-ops"
    _seed_thread(server, conversation_id)
    graph = build_admin_graph(server)

    renamed = graph.invoke(
        {
            "action": "rename",
            "conversation_id": conversation_id,
            "title": "Свой чат",
            "auditor_id": "ADMIN-001",
        }
    )
    assert renamed["ok"] is True
    assert _thread_title(server, conversation_id) == "Свой чат"

    deleted = graph.invoke(
        {
            "action": "delete",
            "conversation_id": conversation_id,
            "auditor_id": "ADMIN-001",
        }
    )
    assert deleted["ok"] is True
    assert _thread_exists(server, conversation_id) is False


@pytest.mark.parametrize("action", ["rename", "delete"])
def test_admin_rejects_empty_auditor_for_owned_chat(server, action):
    conversation_id = f"admin-chat-empty-auditor-{action}"
    _seed_thread(server, conversation_id)
    graph = build_admin_graph(server)

    payload = {"action": action, "conversation_id": conversation_id}
    if action == "rename":
        payload["title"] = "Без владельца"

    result = graph.invoke(payload)

    assert result["ok"] is False
    assert "another auditor" in result["error"]
    assert _thread_exists(server, conversation_id)


def test_admin_rename_creates_thread_with_owner(server):
    conversation_id = "admin-chat-rename-new"
    graph = build_admin_graph(server)

    result = graph.invoke(
        {
            "action": "rename",
            "conversation_id": conversation_id,
            "title": "Новый чат",
            "auditor_id": "ADMIN-777",
        }
    )
    assert result["ok"] is True

    with db_runtime.connect(server) as conn:
        owner = conn.execute(
            "SELECT auditor_id FROM audit.chat_threads WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()[0]
    assert owner == "ADMIN-777"


def test_load_history_is_hidden_from_another_auditor(server):
    conversation_id = "admin-chat-history-owner"
    _seed_thread(server, conversation_id)

    own = dialogue_store.load_history(
        server, conversation_id, auditor_id="ADMIN-001"
    )
    assert [row["role"] for row in own] == ["user", "assistant"]

    assert (
        dialogue_store.load_history(
            server, conversation_id, auditor_id="ADMIN-002"
        )
        == []
    )

    # Пустой auditor_id сохраняет прежнее поведение для CLI и legacy-вызовов.
    assert len(dialogue_store.load_history(server, conversation_id)) == 2
