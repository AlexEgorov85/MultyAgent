"""Служебный граф для управления чатами: rename/delete.

Вызывается через LangGraph API как отдельный assistant ``dialogue_admin``.
Не использует LLM и не создаёт ответов в истории диалога.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .. import dialogue_store

logger = logging.getLogger(__name__)


class AdminState(TypedDict, total=False):
    action: str
    conversation_id: str
    title: str
    auditor_id: str
    ok: bool
    error: str


def build_admin_graph(server):
    def run_action(state: AdminState) -> dict[str, Any]:
        action = str(state.get("action") or "").strip().lower()
        conversation_id = str(state.get("conversation_id") or "").strip()
        if not conversation_id:
            return {"ok": False, "error": "conversation_id is required"}
        try:
            if action == "rename":
                title = " ".join(str(state.get("title") or "").split())[:160]
                if not title:
                    return {"ok": False, "error": "title is required"}
                dialogue_store.rename_thread(
                    server,
                    conversation_id,
                    title,
                    auditor_id=str(state.get("auditor_id") or ""),
                )
                return {"ok": True, "error": ""}
            if action == "delete":
                dialogue_store.delete_thread(
                    server,
                    conversation_id,
                    auditor_id=str(state.get("auditor_id") or ""),
                )
                return {"ok": True, "error": ""}
            return {"ok": False, "error": f"unknown action: {action or 'empty'}"}
        except PermissionError as exc:
            # Чужой чат: наружу только понятное сообщение, без трейсбека.
            logger.warning("dialogue_admin %s denied: %s", action, exc)
            return {"ok": False, "error": str(exc) or "access denied"}
        except Exception as exc:  # noqa: BLE001 - вернуть ошибку в UI
            logger.exception("dialogue_admin %s failed", action)
            detail = str(exc).strip() or type(exc).__name__
            return {"ok": False, "error": detail}

    builder = StateGraph(AdminState)
    builder.add_node("run", run_action)
    builder.add_edge(START, "run")
    builder.add_edge("run", END)
    return builder.compile()
