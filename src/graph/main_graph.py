"""Основной граф: маршрутизация, ACL-вызовы агентов, память и финализация."""

from __future__ import annotations

import re
import time
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ..acl import make_acl_message
from ..guardrails import check_final_answer, check_request, extract_sql
from ..llm import LLMClient
from ..memory import store as memory_store
from ..state import MainState
from .analytics_graph import build_analytics_graph
from .investigation_graph import build_investigation_graph
from .report_graph import build_report_graph
from .retrieval_graph import build_retrieval_graph


def _content_text(content: Any) -> str:
    """Достаёт текст из строки или списка content-блоков LangChain."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") in ("text", "text_delta"):
                parts.append(str(item.get("text", "")))
        return " ".join(part for part in parts if part).strip()
    return "" if content is None else str(content)


def _last_user_text(messages: list[Any]) -> str:
    """Последнее сообщение пользователя.

    LangGraph API присылает сообщения словарями с `type: "human"`, а прямой
    вызов графа — объектами LangChain. Поддерживаем оба варианта.
    """
    for message in reversed(messages):
        if isinstance(message, dict):
            role = message.get("role") or message.get("type")
            if role in ("user", "human"):
                return _content_text(message.get("content", ""))
        elif getattr(message, "type", "") in ("human", "user"):
            return _content_text(getattr(message, "content", ""))
    return ""


def _response_text(content: dict[str, Any]) -> str:
    return str(
        content.get("answer")
        or content.get("draft")
        or content.get("reason")
        or content.get("error")
        or ""
    )


def _pick(state: MainState, ru: str, en: str) -> str:
    return en if state.get("language") == "en" else ru


def build_main_graph(
    server,
    llm: LLMClient,
    analytics_llm: LLMClient | None = None,
    retrieval_llm: LLMClient | None = None,
    report_llm: LLMClient | None = None,
    investigation_llm: LLMClient | None = None,
    embeddings=None,
    top_k: int = 5,
    checkpointer=None,
):
    """Собирает основной граф с краткосрочной памятью по thread_id."""
    analytics = build_analytics_graph(server, analytics_llm or llm)
    retrieval = build_retrieval_graph(
        server, retrieval_llm or llm, embeddings=embeddings, top_k=top_k
    )
    report = build_report_graph(server, report_llm or llm)
    investigation = build_investigation_graph(
        server,
        investigation_llm or llm,
        analytics_llm=analytics_llm or llm,
        retrieval_llm=retrieval_llm or llm,
        embeddings=embeddings,
        top_k=top_k,
    )

    def load_memory(state: MainState) -> dict[str, Any]:
        question = _last_user_text(state.get("messages", []))
        auditor_id = state.get("auditor_id", "")
        profile = memory_store.load_profile(server, auditor_id)
        return {
            "user_query": question,
            "profile": profile,
            "conversation_id": state.get("conversation_id", "conv-main"),
            "metrics": {"started_at": time.perf_counter()},
        }

    def save_memory(state: MainState) -> dict[str, Any]:
        facts = memory_store.infer_memory(state.get("user_query", ""))
        if not facts:
            return {"memory_saved": False}
        for key, value in facts.items():
            memory_store.save_fact(server, state.get("auditor_id", ""), key, value)
        profile = memory_store.load_profile(server, state.get("auditor_id", ""))
        answer = _pick(
            state, "Профиль сохранён: ", "Profile saved: "
        ) + memory_store.profile_text(profile)
        return {
            "memory_saved": True,
            "profile": profile,
            "route": "memory",
            "final_answer": answer,
        }

    def guard_request(state: MainState) -> dict[str, Any]:
        result = check_request(state.get("user_query", ""))
        if not result.safe:
            return {
                "guardrail": result.model_dump(),
                "route": "unsafe",
                "route_reason": result.reason,
            }
        return {"guardrail": result.model_dump()}

    def router(state: MainState) -> dict[str, Any]:
        question = state.get("user_query", "")
        lower = question.lower()
        if re.search(r"aud-\d{4}-[a-z]+-\d{2}", lower) and (
            "похож" in lower or "друг" in lower
        ):
            return {
                "route": "analytics",
                "route_reason": "код проверки и запрос похожих формулировок",
                "route_confidence": 0.95,
            }
        if "повторн" in lower and "наход" in lower:
            return {
                "route": "retrieval",
                "route_reason": "поиск примеров повторных находок",
                "route_confidence": 0.9,
            }
        if (
            ("почему" in lower or "за счёт" in lower or "за счет" in lower)
            and any(
                word in lower
                for word in ("доля", "вырос", "изменил", "динамик", "снизил")
            )
        ):
            return {
                "route": "investigation",
                "route_reason": "причинный вопрос о динамике показателя",
                "route_confidence": 0.9,
            }
        try:
            decision = llm.route(
                question=question,
                profile_text=memory_store.profile_text(state.get("profile", {})),
            )
        except Exception:
            decision = None
        if decision is None:
            return {
                "route": "out_of_domain",
                "route_reason": "маршрутизация недоступна",
            }
        return {
            "route": decision.route,
            "route_reason": decision.reason,
            "route_confidence": decision.confidence,
        }

    def _question_with_profile(state: MainState) -> str:
        question = state.get("user_query", "")
        profile = state.get("profile", {})
        parts = []
        if profile.get("focus_theme"):
            parts.append(f"Тема: {profile['focus_theme']}.")
        if profile.get("default_format"):
            parts.append(f"Формат: {profile['default_format']}.")
        if parts:
            question = question + "\n" + " ".join(parts)
        return question

    def _call_branch(state: MainState, receiver: str, graph) -> dict[str, Any]:
        request = make_acl_message(
            performative="request",
            sender="orchestrator",
            receiver=receiver,
            content={
                "question": _question_with_profile(state),
                "auditor_id": state.get("auditor_id", ""),
                "language": state.get("language", "ru"),
            },
            conversation_id=state.get("conversation_id", "conv-main"),
        )
        result = graph.invoke({"acl_request": request.model_dump()})
        response = result.get("acl_response", {})
        content = response.get("content", {})
        return {
            "acl_response": response,
            "final_answer": _response_text(content),
            "evidence": content.get("evidence", []),
        }

    def analytics_branch(state: MainState) -> dict[str, Any]:
        return _call_branch(state, "analytics_agent", analytics)

    def retrieval_branch(state: MainState) -> dict[str, Any]:
        return _call_branch(state, "retrieval_agent", retrieval)

    def report_branch(state: MainState) -> dict[str, Any]:
        return _call_branch(state, "report_agent", report)

    def investigation_branch(state: MainState) -> dict[str, Any]:
        return _call_branch(state, "investigation_coordinator", investigation)

    def refusal(state: MainState) -> dict[str, Any]:
        route = state.get("route")
        guard = state.get("guardrail", {})
        if guard and not guard.get("safe"):
            answer = (
                guard.get("final_answer")
                or guard.get("reason")
                or _pick(state, "Запрос отклонён.", "The request was declined.")
            )
        elif route == "unsafe":
            answer = _pick(
                state,
                "Не могу выполнить запрос: изменение данных запрещено.",
                "I cannot run this request: data modification is not allowed.",
            )
        else:
            answer = _pick(
                state,
                "Я помогаю только по вопросам внутреннего аудита.",
                "I can only help with internal audit questions.",
            )
        return {"final_answer": answer, "evidence": []}

    def guard_answer(state: MainState) -> dict[str, Any]:
        route = state.get("route")
        result = check_final_answer(
            state.get("final_answer", ""),
            extract_sql(state.get("acl_response")),
            is_domain=route != "out_of_domain",
        )
        if not result.safe:
            return {
                "final_answer": result.final_answer,
                "guardrail": result.model_dump(),
            }
        return {"guardrail": result.model_dump()}

    def finalize(state: MainState) -> dict[str, Any]:
        answer = state.get("final_answer", "")
        metrics = dict(state.get("metrics", {}))
        started = metrics.pop("started_at", None)
        if started is not None:
            metrics["latency_total_sec"] = round(time.perf_counter() - started, 4)
        return {
            "messages": [{"type": "ai", "content": answer}],
            "final_answer": answer,
            "metrics": metrics,
        }

    builder = StateGraph(MainState)
    builder.add_node("load_memory", load_memory)
    builder.add_node("save_memory", save_memory)
    builder.add_node("guard_request", guard_request)
    builder.add_node("router", router)
    builder.add_node("analytics", analytics_branch)
    builder.add_node("retrieval", retrieval_branch)
    builder.add_node("report", report_branch)
    builder.add_node("investigation", investigation_branch)
    builder.add_node("refusal", refusal)
    builder.add_node("guard_answer", guard_answer)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "load_memory")
    builder.add_edge("load_memory", "save_memory")
    builder.add_conditional_edges(
        "save_memory",
        lambda s: "finalize" if s.get("memory_saved") else "guard_request",
        {"guard_request": "guard_request", "finalize": "finalize"},
    )
    builder.add_conditional_edges(
        "guard_request",
        lambda s: "refusal" if s.get("route") == "unsafe" else "router",
        {"router": "router", "refusal": "refusal"},
    )
    builder.add_conditional_edges(
        "router",
        lambda s: s.get("route", "out_of_domain"),
        {
            "analytics": "analytics",
            "retrieval": "retrieval",
            "report": "report",
            "investigation": "investigation",
            "out_of_domain": "refusal",
            "unsafe": "refusal",
        },
    )
    for branch in ("analytics", "retrieval", "report", "investigation", "refusal"):
        builder.add_edge(branch, "guard_answer")
    builder.add_edge("guard_answer", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())
