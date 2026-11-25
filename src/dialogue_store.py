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


_OWNER_ERROR = "chat belongs to another auditor"


def _thread_owner(conn, conversation_id: str) -> str:
    """Возвращает auditor_id владельца чата или "" если строки нет."""
    row = conn.execute(
        "SELECT auditor_id FROM audit.chat_threads WHERE conversation_id = %s",
        (conversation_id,),
    ).fetchone()
    return str(row[0] or "").strip() if row is not None else ""


def _check_owner(owner: str, auditor_id: str) -> None:
    """Разрешает операцию, если владелец неизвестен или совпадает.

    Это defense-in-depth, а не аутентификация: пустой ``auditor_id``
    допустим только для чатов, у которых владелец не записан.
    """
    caller = str(auditor_id or "").strip()
    if owner and owner != caller:
        raise PermissionError(_OWNER_ERROR)


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
    payload: dict[str, Any] | None = None,
) -> None:
    """Записывает один ход диалога: user + assistant.

    ``payload`` хранит данные ответа (строки, колонки, SQL), чтобы
    follow-up «построй диаграмму по этим данным» не зависел от текста.
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
    payload_json = (
        json.dumps(payload, ensure_ascii=False, default=str)
        if payload is not None
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
                " trace, resolved_query, payload) "
                "VALUES (%s, %s, %s, 'assistant', %s, %s, %s, %s) "
                "ON CONFLICT (conversation_id, turn_id, role) DO NOTHING",
                (
                    f"{turn}-assistant",
                    conversation_id,
                    turn,
                    assistant_text,
                    trace_json,
                    resolved,
                    payload_json,
                ),
            )


def rename_thread(
    server,
    conversation_id: str,
    title: str,
    *,
    auditor_id: str = "",
) -> None:
    """Меняет название чата; создаёт строку для старых чатов без истории.

    Если у чата уже есть владелец, переименовать его может только он.
    """
    conversation_id = str(conversation_id or "").strip()
    title = " ".join(str(title or "").split())[:160]
    if not conversation_id or not title:
        return
    with _connect(server) as conn:
        _check_owner(_thread_owner(conn, conversation_id), auditor_id)
        conn.execute(
            "INSERT INTO audit.chat_threads "
            "(conversation_id, auditor_id, title) VALUES (%s, %s, %s) "
            "ON CONFLICT (conversation_id) DO UPDATE SET "
            "title = EXCLUDED.title, "
            "auditor_id = COALESCE("
            "NULLIF(audit.chat_threads.auditor_id, ''), "
            "NULLIF(EXCLUDED.auditor_id, '')), "
            "updated_at = now()",
            (conversation_id, str(auditor_id or "").strip(), title),
        )


def delete_thread(
    server,
    conversation_id: str,
    *,
    auditor_id: str = "",
) -> None:
    """Удаляет чат и все его сообщения (FK ON DELETE CASCADE).

    Если у чата уже есть владелец, удалить его может только он.
    Отсутствие строки не ошибка: удалять нечего.
    """
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return
    with _connect(server) as conn:
        _check_owner(_thread_owner(conn, conversation_id), auditor_id)
        conn.execute(
            "DELETE FROM audit.chat_threads WHERE conversation_id = %s",
            (conversation_id,),
        )


def load_history(
    server,
    conversation_id: str,
    *,
    auditor_id: str = "",
    limit: int = 24,
) -> list[dict[str, str]]:
    """Последние сообщения чата в хронологическом порядке.

    Если передан ``auditor_id``, история чужого чата не отдаётся. Пустой
    ``auditor_id`` сохраняет прежнее поведение (CLI, тесты, legacy-вызовы).
    """
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return []
    with _connect(server) as conn:
        owner = _thread_owner(conn, conversation_id)
        caller = str(auditor_id or "").strip()
        if caller and owner and owner != caller:
            return []
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


def _trace_sql(trace: Any) -> str:
    steps = trace
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except (TypeError, ValueError):
            return ""
    if not isinstance(steps, list):
        return ""
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("step") != "sql":
            continue
        code = step.get("code") or step.get("detail")
        if isinstance(code, str) and code.strip():
            return code.strip()
    return ""


def last_assistant_kind(
    server,
    conversation_id: str,
    *,
    auditor_id: str = "",
) -> str:
    """Тип последнего ответа ассистента: chart / text / пусто.

    Нужен, чтобы router понимал, что пользователь дополняет диаграмму,
    а не начинает новый аналитический вопрос.
    """
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return ""
    with _connect(server) as conn:
        owner = _thread_owner(conn, conversation_id)
        caller = str(auditor_id or "").strip()
        if caller and owner and owner != caller:
            return ""
        row = conn.execute(
            "SELECT role, payload, trace FROM audit.chat_messages "
            "WHERE conversation_id = %s "
            "ORDER BY created_at DESC, message_id DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    if not row or str(row[0]) != "assistant":
        return ""
    payload, trace = row[1], row[2]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = None
    if isinstance(payload, dict) and payload.get("chart"):
        return "chart"
    if isinstance(trace, str):
        try:
            trace = json.loads(trace)
        except (TypeError, ValueError):
            trace = None
    if isinstance(trace, list) and any(
        isinstance(step, dict) and step.get("kind") == "chart" for step in trace
    ):
        return "chart"
    return "text"


def load_pending_clarification(
    server,
    conversation_id: str,
    *,
    auditor_id: str = "",
) -> dict[str, Any] | None:
    """Незакрытый уточняющий вопрос последнего хода.

    Возвращает clarification, только если последнее сообщение — ответ
    ассистента с уточнением. Если после него уже была реплика пользователя,
    вопрос считается отвеченным.
    """
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return None
    with _connect(server) as conn:
        owner = _thread_owner(conn, conversation_id)
        caller = str(auditor_id or "").strip()
        if caller and owner and owner != caller:
            return None
        row = conn.execute(
            "SELECT role, payload FROM audit.chat_messages "
            "WHERE conversation_id = %s "
            "ORDER BY created_at DESC, message_id DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    if not row or str(row[0]) != "assistant":
        return None
    payload = row[1]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return None
    if not isinstance(payload, dict):
        return None
    clarification = payload.get("clarification")
    if isinstance(clarification, dict) and str(
        clarification.get("question") or ""
    ).strip():
        return clarification
    return None


def load_last_analytics(
    server,
    conversation_id: str,
    *,
    auditor_id: str = "",
    limit: int = 20,
) -> dict[str, Any] | None:
    """Данные последнего аналитического ответа для follow-up.

    Сначала используется ``payload`` (точные строки/колонки), затем
    fallback на SQL из trace для старых сообщений без payload.
    """
    conversation_id = str(conversation_id or "").strip()
    if not conversation_id:
        return None
    with _connect(server) as conn:
        owner = _thread_owner(conn, conversation_id)
        caller = str(auditor_id or "").strip()
        if caller and owner and owner != caller:
            return None
        rows = conn.execute(
            "SELECT turn_id, trace, payload FROM audit.chat_messages "
            "WHERE conversation_id = %s AND role = 'assistant' "
            "ORDER BY created_at DESC LIMIT %s",
            (conversation_id, max(1, int(limit))),
        ).fetchall()
        for turn_id, trace, payload in rows:
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (TypeError, ValueError):
                    payload = None
            if isinstance(payload, dict):
                payload_rows = payload.get("rows")
                payload_columns = payload.get("columns")
                if isinstance(payload_rows, list) and payload_rows:
                    result = dict(payload)
                    result["sql"] = str(payload.get("sql") or "")
                    result["question"] = str(payload.get("question") or "")
                    result["rows"] = payload_rows
                    result["columns"] = (
                        payload_columns if isinstance(payload_columns, list) else []
                    )
                    return result
            sql = _trace_sql(trace)
            if not sql:
                continue
            user_row = conn.execute(
                "SELECT content FROM audit.chat_messages "
                "WHERE conversation_id = %s AND turn_id = %s AND role = 'user'",
                (conversation_id, turn_id),
            ).fetchone()
            return {
                "sql": sql,
                "question": str(user_row[0]) if user_row is not None else "",
            }
    return None


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
