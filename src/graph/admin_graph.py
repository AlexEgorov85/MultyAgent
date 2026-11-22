"""Служебный граф для управления чатами и профилем аудитора.

Вызывается через LangGraph API как отдельный assistant ``dialogue_admin``.
Не использует LLM и не создаёт ответов в истории диалога.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .. import dialogue_store
from ..memory import store as memory_store

logger = logging.getLogger(__name__)


class AdminState(TypedDict, total=False):
    """Вход и результат служебной операции над чатом или профилем."""

    action: str
    conversation_id: str
    title: str
    auditor_id: str
    key: str
    ok: bool
    error: str
    profile: dict[str, str]


def build_admin_graph(server):
    """Собирает граф rename/delete чатов и операций с профилем без LLM."""

    def run_action(state: AdminState) -> dict[str, Any]:
        action = str(state.get("action") or "").strip().lower()
        auditor_id = str(state.get("auditor_id") or "").strip()

        if action in ("profile_get", "profile_reset", "profile_delete"):
            if not auditor_id:
                return {"ok": False, "error": "auditor_id is required"}
            try:
                if action == "profile_delete":
                    memory_store.delete_fact(
                        server, auditor_id, str(state.get("key") or "").strip()
                    )
                elif action == "profile_reset":
                    memory_store.clear_profile(server, auditor_id)
                return {
                    "ok": True,
                    "error": "",
                    "profile": memory_store.load_stored(server, auditor_id),
                }
            except memory_store.MemoryError as exc:
                return {"ok": False, "error": str(exc)}
            except Exception as exc:  # noqa: BLE001 - вернуть ошибку в UI
                logger.exception("dialogue_admin %s failed", action)
                detail = str(exc).strip() or type(exc).__name__
                return {"ok": False, "error": detail}

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
                    auditor_id=auditor_id,
                )
                return {"ok": True, "error": ""}
            if action == "delete":
                dialogue_store.delete_thread(
                    server,
                    conversation_id,
                    auditor_id=auditor_id,
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
