"""Постоянная история диалога в PostgreSQL.

История хранится отдельно от LangGraph checkpoint-состояния. Ключ —
``conversation_id`` (стабильный id чата из UI), поэтому пересоздание
backend-треда не теряет контекст.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from . import db_runtime


def _connect(server):
    return db_runtime.connect(server, role=db_runtime.APP_ROLE)


def _title(text: str) -> str:
    normalized = " ".join((text or "").split())
    return normalized[:120]


def append_turn(
    server,
    *,
    conversation_id: str,
    auditor_id: str,
    turn_id: str,
    user_text: str,
    assistant_text: str,
    trace: list[dict[str, Any]] | None = None,
    resolved_query: str = "",
) -> None:
    """Записывает один ход диалога: user + assistant.

    Повторный вызов с тем же ``turn_id`` не создаёт дублей.
    """
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return
    turn = str(turn_id or "").strip() or uuid.uuid4().hex
    user_text = str(user_text or "").strip()
    assistant_text = str(assistant_text or "").strip()
    trace_json = (
        json.dumps(trace or [], ensure_ascii=False, default=str)
        if trace is not None
        else None
    )
    resolved = str(resolved_query or "").strip() or None

    with _connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.chat_threads "
            "(conversation_id, auditor_id, title) VALUES (%s, %s, %s) "
            "ON CONFLICT (conversation_id) DO UPDATE SET "
            "auditor_id = COALESCE("
            "NULLIF(audit.chat_threads.auditor_id, ''), "
            "NULLIF(EXCLUDED.auditor_id, '')), "
            "title = COALESCE("
            "NULLIF(audit.chat_threads.title, ''), "
            "NULLIF(EXCLUDED.title, '')), "
            "updated_at = now()",
            (conversation_id, str(auditor_id or ""), _title(user_text)),
        )
        if user_text:
            conn.execute(
                "INSERT INTO audit.chat_messages "
                "(message_id, conversation_id, turn_id, role, content) "
                "VALUES (%s, %s, %s, 'user', %s) "
                "ON CONFLICT (conversation_id, turn_id, role) DO NOTHING",
                (f"{turn}-user", conversation_id, turn, user_text),
            )
        if assistant_text:
            conn.execute(
                "INSERT INTO audit.chat_messages "
                "(message_id, conversation_id, turn_id, role, content, "
                " trace, resolved_query) "
                "VALUES (%s, %s, %s, 'assistant', %s, %s, %s) "
                "ON CONFLICT (conversation_id, turn_id, role) DO NOTHING",
                (
                    f"{turn}-assistant",
                    conversation_id,
                    turn,
                    assistant_text,
                    trace_json,
                    resolved,
                ),
            )


def load_history(
    server,
    conversation_id: str,
    *,
    limit: int = 24,
) -> list[dict[str, str]]:
    """Последние сообщения чата в хронологическом порядке."""
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return []
    with _connect(server) as conn:
        rows = conn.execute(
            "SELECT role, content FROM ("
            "  SELECT role, content, created_at, "
            "         CASE role WHEN 'user' THEN 0 ELSE 1 END AS role_order "
            "  FROM audit.chat_messages "
            "  WHERE conversation_id = %s "
            "  ORDER BY created_at DESC, role_order DESC "
            "  LIMIT %s"
            ") recent "
            "ORDER BY created_at ASC, role_order ASC",
            (conversation_id, max(1, int(limit))),
        ).fetchall()
    return [{"role": row[0], "content": row[1]} for row in rows]


def load_threads(
    server,
    auditor_id: str,
    *,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Список чатов аудитора — задел для серверной истории в UI."""
    with _connect(server) as conn:
        rows = conn.execute(
            "SELECT conversation_id, title, created_at, updated_at "
            "FROM audit.chat_threads "
            "WHERE auditor_id = %s "
            "ORDER BY updated_at DESC LIMIT %s",
            (str(auditor_id or ""), max(1, int(limit))),
        ).fetchall()
    return [
        {
            "conversation_id": row[0],
            "title": row[1],
            "created_at": row[2].isoformat(),
            "updated_at": row[3].isoformat(),
        }
        for row in rows
    ]
