"""Тесты служебного графа управления чатами."""

from __future__ import annotations

from src import db_runtime, dialogue_store
from src.graph.admin_graph import build_admin_graph


def _seed_thread(server, conversation_id: str) -> None:
    dialogue_store.append_turn(
        server,
        conversation_id=conversation_id,
        auditor_id="ADMIN-001",
        turn_id="turn-1",
        user_text="Сколько проверок?",
        assistant_text="Всего: 1.",
        trace=[],
        resolved_query="Сколько проверок?",
    )


def test_admin_renames_and_deletes_thread_with_messages(server):
    conversation_id = "admin-chat-rename-delete"
    _seed_thread(server, conversation_id)
    graph = build_admin_graph(server)

    renamed = graph.invoke(
        {
            "action": "rename",
            "conversation_id": conversation_id,
            "title": "  Новое   название  ",
        }
    )
    assert renamed["ok"] is True

    with db_runtime.connect(server) as conn:
        title = conn.execute(
            "SELECT title FROM audit.chat_threads WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()[0]
    assert title == "Новое название"

    deleted = graph.invoke(
        {"action": "delete", "conversation_id": conversation_id}
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
