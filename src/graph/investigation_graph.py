"""Coordinator расследования: план → раунды ACL → синтез (A7)."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from ..acl import ACLMessage, ACLValidationError, make_acl_message, make_reply, validate_acl
from ..i18n import t
from ..llm import LLMClient
from ..schemas import InvestigationAnswer, InvestigationPlan
from ..state import InvestigationState
from ..tools import db as db_tools
from .analytics_graph import build_analytics_graph
from .retrieval_graph import build_retrieval_graph

EVIDENCE_MAP = {
    "sql_result": "sql_result",
    "item": "item",
    "пункт": "item",
    "act": "act",
    "акт": "act",
}


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
    ):
        request = make_acl_message(
            performative="request",
            sender=sender,
            receiver=receiver,
            content={
                "question": question,
                "conversation_context": conversation_context,
                "auditor_id": auditor_id or "AUD-001",
                "language": language,
            },
            conversation_id=conversation_id,
        )
        result = graph.invoke({"acl_request": request.model_dump()})
        response = result.get("acl_response", {})
        return request, response

    def parse_acl(state: InvestigationState) -> dict[str, Any]:
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
            "language": str(message.content.get("language", "ru")),
            "conversation_id": message.conversation_id,
            "rounds": 0,
            "acl_log": [],
            "evidence": [],
            "missing": [],
        }

    def plan(state: InvestigationState) -> dict[str, Any]:
        try:
            plan_model = llm.plan_investigation(
                question=state["question"],
                schema_text=db_tools.get_schema(),
                context=state.get("conversation_context", ""),
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": t(state.get("language"), "plan_failed", error=exc),
            }
        return {"plan": plan_model.model_dump()}

    def round1(state: InvestigationState) -> dict[str, Any]:
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
        evidence.extend(analytics.get("evidence", []))
        evidence.extend(retrieval.get("evidence", []))

        required = plan_model.required_evidence or ["sql_result", "item"]
        missing = [
            item for item in required if item not in _evidence_types(evidence)
        ]

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
        plan_model = InvestigationPlan.model_validate(state["plan"])
        missing = state.get("missing", [])
        try:
            refined = llm.refine_investigation(
                question=state["question"],
                plan=plan_model,
                missing=missing,
                context=state.get("conversation_context", ""),
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
            )
            log.extend(
                [
                    {"direction": "request", **req.model_dump()},
                    {"direction": "response", **resp},
                ]
            )
            if resp.get("performative") == "inform":
                retrieval = resp.get("content", {})
                evidence.extend(retrieval.get("evidence", []))

        required = refined.required_evidence or plan_model.required_evidence
        missing = [
            item for item in required if item not in _evidence_types(evidence)
        ]
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
        try:
            answer = llm.synthesize_investigation(
                question=state["question"],
                analytics=state.get("analytics_content", {}),
                retrieval=state.get("retrieval_content", {}),
                missing=state.get("missing", []),
                rounds=int(state.get("rounds", 0)),
                context=state.get("conversation_context", ""),
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
        return _reply(
            state,
            "inform",
            {
                "answer": answer.get("text", ""),
                "causal_claim": answer.get("causal_claim", False),
                "evidence": state.get("evidence", []),
                "rounds": int(state.get("rounds", 0)),
                "missing": state.get("missing", []),
                "metrics": {"acl_rounds": int(state.get("rounds", 0))},
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
