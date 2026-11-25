"""Coordinator расследования: план → раунды ACL → синтез (A7)."""

from __future__ import annotations

import logging
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from ..acl import (
    ACLMessage,
    ACLValidationError,
    append_acl_log,
    make_acl_message,
    make_reply,
    resolve_acl_log_path,
    validate_acl,
)
from ..i18n import t
from ..llm import LLMClient
from ..schemas import InvestigationAnswer, InvestigationPlan
from ..state import InvestigationState
from ..tools import db as db_tools
from .analytics_graph import build_analytics_graph
from .retrieval_graph import build_retrieval_graph

logger = logging.getLogger(__name__)

EVIDENCE_MAP = {
    "sql_result": "sql_result",
    "item": "item",
    "пункт": "item",
    "act": "act",
    "акт": "act",
}

# Какие найденные доказательства закрывают требуемый тип.
# Акт подтверждает пункт с меньшим весом, но не наоборот.
EVIDENCE_SATISFIES: dict[str, set[str]] = {
    "item": {"item", "act"},
    "act": {"act"},
    "sql_result": {"sql_result"},
}


def _log_acl(message: dict[str, Any]) -> None:
    """Дописывает ACL-сообщение в журнал, не ломая расследование."""
    if not message:
        return
    try:
        append_acl_log(message)
    except Exception as exc:  # журнал не должен ломать ответ
        logger.warning("Не удалось записать ACL-журнал: %s", exc)


def _reply(
    state: InvestigationState,
    performative: Literal["inform", "refuse", "failure"],
    content: dict[str, Any],
) -> dict[str, Any]:
    request = state.get("request")
    if not request:
        return {
            "acl_response": {
                "error": state.get("error") or t(state.get("language"), "no_acl")
            }
        }
    message = make_reply(
        ACLMessage.model_validate(request),
        performative=performative,
        sender="investigation_coordinator",
        content=content,
    )
    return {"acl_response": message.model_dump()}


def _evidence_types(evidence: list[dict[str, Any]]) -> set[str]:
    types: set[str] = set()
    for item in evidence:
        mapped = EVIDENCE_MAP.get(str(item.get("type", "")).lower())
        if mapped:
            types.add(mapped)
    return types


def _required_type(value: Any) -> str:
    """Приводит требуемый тип evidence к каноническому виду."""
    text = str(value or "").strip().lower()
    return EVIDENCE_MAP.get(text, text)


def _missing_evidence(
    required: list[Any],
    found: set[str],
) -> list[Any]:
    """Возвращает требования, которые не закрыты найденными доказательствами."""
    missing: list[Any] = []
    for item in required:
        canon = _required_type(item)
        accepted = EVIDENCE_SATISFIES.get(canon, {canon})
        if not (accepted & found):
            missing.append(item)
    return missing


def _filter_retrieval_by_scope(
    server,
    retrieval: dict[str, Any],
    scope: dict[str, Any] | None,
) -> dict[str, Any]:
    """Убирает акты, которые не попадают в ограничения вопроса.

    Scope берётся из проверенного QueryPlan Analytics (тема, код проверки),
    а не из отдельного поля плана расследования.
    """
    if not scope or not isinstance(retrieval, dict):
        return retrieval

    def is_act(value: Any) -> bool:
        return str(value or "").strip().lower() in ("act", "акт")

    sources = list(retrieval.get("sources") or [])
    act_numbers = [
        str(item.get("source_id") or "")
        for item in sources
        if is_act(item.get("source_type"))
    ]
    if not act_numbers:
        return retrieval
    try:
        act_scope = db_tools.act_scope_map(server, act_numbers)
    except Exception:
        return retrieval
    if not act_scope:
        return retrieval

    def matches(code: str) -> bool:
        data = act_scope.get(code)
        if not data:
            # Неизвестный акт не доказывает нерелевантность.
            return True
        for field, value in scope.items():
            if field not in data:
                continue
            if str(data[field]).strip().lower() != str(value).strip().lower():
                return False
        return True

    filtered_sources = [
        item
        for item in sources
        if not is_act(item.get("source_type"))
        or matches(str(item.get("source_id") or ""))
    ]
    kept_ids = {str(item.get("source_id") or "") for item in filtered_sources}
    citations = [
        item
        for item in retrieval.get("citations") or []
        if str(item) in kept_ids or str(item) not in act_scope
    ]
    evidence = [
        item
        for item in retrieval.get("evidence") or []
        if str(item.get("source_id") or "") not in act_scope
        or str(item.get("source_id") or "") in kept_ids
    ]
    return {
        **retrieval,
        "sources": filtered_sources,
        "citations": citations,
        "evidence": evidence,
    }


def build_investigation_graph(
    server,
    llm: LLMClient,
    analytics_llm: LLMClient | None = None,
    retrieval_llm: LLMClient | None = None,
    embeddings=None,
    top_k: int = 5,
):
    """Собирает граф Coordinator с реальными ACL-вызовами подагентов."""
    analytics_graph = build_analytics_graph(server, analytics_llm or llm)
    retrieval_graph = build_retrieval_graph(
        server, retrieval_llm or llm, embeddings=embeddings, top_k=top_k
    )

    def _call(
        graph,
        *,
        sender: str,
        receiver: str,
        question: str,
        conversation_id: str,
        auditor_id: str = "",
        language: str = "ru",
        conversation_context: str = "",
        profile_text: str = "",
    ):
        request = make_acl_message(
            performative="request",
            sender=sender,
            receiver=receiver,
            content={
                "question": question,
                "conversation_context": conversation_context,
                # Не подставляем чужой профиль: пустой id означает «нет
                # аудитора», а не «аудитор AUD-001».
                "auditor_id": auditor_id,
                "language": language,
                "profile_text": profile_text,
            },
            conversation_id=conversation_id,
        )
        _log_acl(request.model_dump())
        result = graph.invoke({"acl_request": request.model_dump()})
        response = result.get("acl_response", {})
        if isinstance(response, dict) and response:
            _log_acl(response)
        return request, response

    def parse_acl(state: InvestigationState) -> dict[str, Any]:
        """Проверяет ACL-запрос и извлекает вопрос и контекст."""
        try:
            message = validate_acl(state.get("acl_request", {}))
        except ACLValidationError as exc:
            return {"status": "refused", "error": t(None, "invalid_acl", error=exc)}
        if message.performative != "request":
            lang = str(message.content.get("language", "ru"))
            return {
                "status": "refused",
                "error": t(lang, "request_only", agent="Coordinator"),
                "language": lang,
                "request": message.model_dump(),
            }
        question = str(message.content.get("question", "")).strip()
        if not question:
            lang = str(message.content.get("language", "ru"))
            return {
                "status": "refused",
                "error": t(lang, "missing_question"),
                "language": lang,
                "request": message.model_dump(),
            }
        return {
            "status": "ok",
            "request": message.model_dump(),
            "question": question,
            "conversation_context": str(
                message.content.get("conversation_context", "")
            ),
            "auditor_id": str(message.content.get("auditor_id", "")),
            "profile_text": str(message.content.get("profile_text", "")),
            "language": str(message.content.get("language", "ru")),
            "conversation_id": message.conversation_id,
            "rounds": 0,
            "acl_log": [],
            "evidence": [],
            "missing": [],
        }

    def plan(state: InvestigationState) -> dict[str, Any]:
        """Декомпозирует вопрос на analytics_question и retrieval_question."""
        try:
            plan_model = llm.plan_investigation(
                question=state["question"],
                schema_text=db_tools.get_schema(),
                context=state.get("conversation_context", ""),
                profile_text=state.get("profile_text", ""),
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": t(state.get("language"), "plan_failed", error=exc),
            }
        return {"plan": plan_model.model_dump()}

    def round1(state: InvestigationState) -> dict[str, Any]:
        """Первый ACL-раунд: опрашивает Analytics и Retrieval."""
        plan_model = InvestigationPlan.model_validate(state["plan"])
        log = list(state.get("acl_log", []))
        evidence = list(state.get("evidence", []))

        a_req, a_resp = _call(
            analytics_graph,
            sender="investigation_coordinator",
            receiver="analytics_agent",
            question=plan_model.analytics_question,
            conversation_id=state["conversation_id"],
            auditor_id=state.get("auditor_id", ""),
            language=state.get("language", "ru"),
            conversation_context=state.get("conversation_context", ""),
            profile_text=state.get("profile_text", ""),
        )
        r_req, r_resp = _call(
            retrieval_graph,
            sender="investigation_coordinator",
            receiver="retrieval_agent",
            question=plan_model.retrieval_question,
            conversation_id=state["conversation_id"],
            auditor_id=state.get("auditor_id", ""),
            language=state.get("language", "ru"),
            conversation_context=state.get("conversation_context", ""),
            profile_text=state.get("profile_text", ""),
        )
        log.extend(
            [
                {"direction": "request", **a_req.model_dump()},
                {"direction": "response", **a_resp},
                {"direction": "request", **r_req.model_dump()},
                {"direction": "response", **r_resp},
            ]
        )
        analytics = a_resp.get("content", {}) if a_resp.get("performative") == "inform" else {}
        retrieval = r_resp.get("content", {}) if r_resp.get("performative") == "inform" else {}
        retrieval = _filter_retrieval_by_scope(
            server, retrieval, analytics.get("scope")
        )
        evidence.extend(analytics.get("evidence", []))
        evidence.extend(retrieval.get("evidence", []))

        required = plan_model.required_evidence or ["sql_result", "item"]
        found_types = _evidence_types(evidence)
        missing = _missing_evidence(required, found_types)

        return {
            "rounds": 1,
            "acl_log": log,
            "analytics_content": analytics,
            "retrieval_content": retrieval,
            "evidence": evidence,
            "missing": missing,
            "status": "ok",
        }

    def round2(state: InvestigationState) -> dict[str, Any]:
        """Второй ACL-раунд: добирает недостающие evidence."""
        plan_model = InvestigationPlan.model_validate(state["plan"])
        missing = state.get("missing", [])
        try:
            refined = llm.refine_investigation(
                question=state["question"],
                plan=plan_model,
                missing=missing,
                context=state.get("conversation_context", ""),
                profile_text=state.get("profile_text", ""),
            )
        except Exception:
            return {"rounds": 2, "status": "ok"}

        log = list(state.get("acl_log", []))
        evidence = list(state.get("evidence", []))
        analytics = dict(state.get("analytics_content", {}))
        retrieval = dict(state.get("retrieval_content", {}))

        if "sql_result" in missing:
            req, resp = _call(
                analytics_graph,
                sender="investigation_coordinator",
                receiver="analytics_agent",
                question=refined.analytics_question,
                conversation_id=state["conversation_id"],
                auditor_id=state.get("auditor_id", ""),
                language=state.get("language", "ru"),
                conversation_context=state.get("conversation_context", ""),
                profile_text=state.get("profile_text", ""),
            )
            log.extend(
                [
                    {"direction": "request", **req.model_dump()},
                    {"direction": "response", **resp},
                ]
            )
            if resp.get("performative") == "inform":
                analytics = resp.get("content", {})
                evidence.extend(analytics.get("evidence", []))

        if any(item in ("item", "act") for item in missing):
            req, resp = _call(
                retrieval_graph,
                sender="investigation_coordinator",
                receiver="retrieval_agent",
                question=refined.retrieval_question,
                conversation_id=state["conversation_id"],
                auditor_id=state.get("auditor_id", ""),
                language=state.get("language", "ru"),
                conversation_context=state.get("conversation_context", ""),
                profile_text=state.get("profile_text", ""),
            )
            log.extend(
                [
                    {"direction": "request", **req.model_dump()},
                    {"direction": "response", **resp},
                ]
            )
            if resp.get("performative") == "inform":
                retrieval = resp.get("content", {})
                retrieval = _filter_retrieval_by_scope(
                    server, retrieval, analytics.get("scope")
                )
                evidence.extend(retrieval.get("evidence", []))

        required = refined.required_evidence or plan_model.required_evidence
        found_types = _evidence_types(evidence)
        missing = _missing_evidence(required, found_types)
        return {
            "rounds": 2,
            "plan": refined.model_dump(),
            "acl_log": log,
            "analytics_content": analytics,
            "retrieval_content": retrieval,
            "evidence": evidence,
            "missing": missing,
            "status": "ok",
        }

    def synthesize(state: InvestigationState) -> dict[str, Any]:
        """Синтезирует итог, отделяя факт от гипотезы."""
        try:
            answer = llm.synthesize_investigation(
                question=state["question"],
                analytics=state.get("analytics_content", {}),
                retrieval=state.get("retrieval_content", {}),
                missing=state.get("missing", []),
                rounds=int(state.get("rounds", 0)),
                context=state.get("conversation_context", ""),
                profile_text=state.get("profile_text", ""),
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": t(
                    state.get("language"), "synthesis_failed", error=exc
                ),
            }

        text = answer.text
        causal = answer.causal_claim
        if causal and state.get("missing"):
            causal = False
            text += "\n\n" + t(
                state.get("language"),
                "causal_missing",
                missing=", ".join(state.get("missing", [])),
            )
        return {"answer": {"text": text, "causal_claim": causal}, "status": "ok"}

    def pack_response(state: InvestigationState) -> dict[str, Any]:
        """Упаковывает итог расследования в ACL-ответ."""
        status = state.get("status")
        if status == "refused":
            return _reply(
                state,
                "refuse",
                {
                    "reason": state.get("error")
                    or t(state.get("language"), "request_declined")
                },
            )
        if status == "failed":
            return _reply(
                state,
                "failure",
                {
                    "reason": state.get("error")
                    or t(state.get("language"), "run_failed")
                },
            )
        answer = state.get("answer", {})
        plan = state.get("plan") or {}
        required = list(
            plan.get("required_evidence") or ["sql_result", "item"]
        )
        missing = list(state.get("missing") or [])
        total = max(1, len(required))
        present = max(0, total - len([item for item in required if item in missing]))
        return _reply(
            state,
            "inform",
            {
                "answer": answer.get("text", ""),
                "causal_claim": answer.get("causal_claim", False),
                "evidence": state.get("evidence", []),
                "rounds": int(state.get("rounds", 0)),
                "missing": missing,
                "metrics": {
                    "acl_rounds": int(state.get("rounds", 0)),
                    "acl_log_count": len(state.get("acl_log", [])),
                    "acl_log_path": str(resolve_acl_log_path()),
                    "investigation_completeness": round(present / total, 3),
                },
            },
        )

    builder = StateGraph(InvestigationState)
    builder.add_node("parse_acl", parse_acl)
    builder.add_node("plan", plan)
    builder.add_node("round1", round1)
    builder.add_node("round2", round2)
    builder.add_node("synthesize", synthesize)
    builder.add_node("pack", pack_response)

    builder.add_edge(START, "parse_acl")
    builder.add_conditional_edges(
        "parse_acl",
        lambda s: "plan" if s.get("status") == "ok" else "pack",
        {"plan": "plan", "pack": "pack"},
    )
    builder.add_conditional_edges(
        "plan",
        lambda s: "round1" if s.get("status", "ok") == "ok" else "pack",
        {"round1": "round1", "pack": "pack"},
    )
    builder.add_conditional_edges(
        "round1",
        lambda s: (
            "round2"
            if s.get("missing") and int(s.get("rounds", 0)) < 2
            else "synthesize"
        ),
        {"round2": "round2", "synthesize": "synthesize"},
    )
    builder.add_edge("round2", "synthesize")
    builder.add_edge("synthesize", "pack")
    builder.add_edge("pack", END)

    return builder.compile()
