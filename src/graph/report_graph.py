"""Report-подагент и Inspector: факты → черновик → проверка → исправление."""

from __future__ import annotations

import re
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from ..acl import ACLMessage, ACLValidationError, make_reply, validate_acl
from ..llm import LLMClient
from ..schemas import ReportDraft, ReportReview
from ..state import ReportState
from ..tools import db as db_tools

AUDIT_CODE_RE = re.compile(r"AUD-\d{4}-[A-Z]+-\d{2}", re.IGNORECASE)


def _reply(
    state: ReportState,
    performative: Literal["inform", "refuse", "failure"],
    content: dict[str, Any],
) -> dict[str, Any]:
    request = state.get("request")
    if not request:
        return {"acl_response": {"error": state.get("error", "нет ACL-запроса")}}
    message = make_reply(
        ACLMessage.model_validate(request),
        performative=performative,
        sender="report_agent",
        content=content,
    )
    return {"acl_response": message.model_dump()}


def build_report_graph(server, llm: LLMClient):
    """Собирает граф Report + Inspector."""

    def parse_acl(state: ReportState) -> dict[str, Any]:
        try:
            message = validate_acl(state.get("acl_request", {}))
        except ACLValidationError as exc:
            return {"status": "refused", "error": f"Невалидный ACL: {exc}"}
        if message.performative != "request":
            return {
                "status": "refused",
                "error": "Report принимает только performative=request",
                "request": message.model_dump(),
            }
        question = str(message.content.get("question", "")).strip()
        if not question:
            return {
                "status": "refused",
                "error": "В ACL-запросе нет question",
                "request": message.model_dump(),
            }
        return {
            "status": "ok",
            "request": message.model_dump(),
            "question": question,
            "auditor_id": str(message.content.get("auditor_id", "")),
            "conversation_id": message.conversation_id,
            "iterations": 0,
        }

    def collect_facts(state: ReportState) -> dict[str, Any]:
        match = AUDIT_CODE_RE.search(state["question"])
        if not match:
            return {
                "status": "failed",
                "error": "В запросе не указан код проверки (AUD-...).",
            }
        audit_code = match.group(0).upper()
        audit = db_tools.get_audit(server, audit_code)
        if audit is None:
            return {
                "status": "failed",
                "error": f"Проверка {audit_code} не найдена.",
            }

        act = db_tools.get_act(server, audit_code)
        items = db_tools.get_act_items(server, audit_code, limit=50)

        facts = [{"type": "audit", **audit}]
        if act:
            facts.append({"type": "act", **act})
        for item in items:
            facts.append({"type": "item", **item})

        allowed_ids = [audit["audit_id"]]
        if act:
            allowed_ids.append(act["act_id"])
        allowed_ids.extend(item["item_id"] for item in items)

        lines = [
            f"Проверка: {audit['audit_code']} — {audit['title']}",
            f"Статус: {audit['status']}, период: {audit['start_date']} — {audit['end_date']}",
            f"Карман: {audit['pocket_title']} ({audit['theme_code']})",
            f"Руководитель: {audit['lead_auditor']}",
        ]
        if act:
            lines.append(
                f"Акт: {act['act_number']}, статус {act['status']}, дата {act['act_date']}"
            )
            lines.append(f"Краткое содержание акта: {act['summary'] or ''}")
        lines.append("Пункты:")
        for item in items:
            lines.append(
                f"- {item['item_id']} | {item['item_number']} | {item['title']} | "
                f"{item['item_type']} | риск {item['risk_level']} | "
                f"статус {item['status']} | срок {item['deadline']}"
            )
        if not items:
            lines.append("- пунктов нет")

        return {
            "audit_code": audit_code,
            "facts": facts,
            "facts_text": "\n".join(lines),
            "allowed_ids": allowed_ids,
        }

    def draft(state: ReportState) -> dict[str, Any]:
        try:
            draft_model = llm.draft_report(
                question=state["question"],
                facts_text=state["facts_text"],
                allowed_ids=state["allowed_ids"],
            )
        except Exception as exc:
            return {"status": "failed", "error": f"Не удалось подготовить черновик: {exc}"}
        return {"draft": draft_model.model_dump(), "status": "ok"}

    def validate_citations(state: ReportState) -> dict[str, Any]:
        allowed = set(state.get("allowed_ids", []))
        draft_model = state.get("draft", {})
        text = str(draft_model.get("text", "")).replace("<br>", "\n").replace("<br/>", "\n")
        text = re.sub(r"\[\d+\]", "", text)
        declared = draft_model.get("citations", [])
        citations = [item for item in declared if item in allowed]
        invalid = [item for item in declared if item not in allowed]
        if not citations:
            found = re.findall(r"(?:ITM|ACT|AUD)-[A-Z0-9-]+", text)
            citations = [item for item in dict.fromkeys(found) if item in allowed]
        issues = [f"Несуществующие ID: {', '.join(invalid)}"] if invalid else []
        return {
            "draft": {**draft_model, "text": text, "citations": citations},
            "citations": citations,
            "citation_issues": issues,
        }

    def review(state: ReportState) -> dict[str, Any]:
        draft_model = ReportDraft.model_validate(state["draft"])
        try:
            review_model = llm.review_report(
                draft=draft_model,
                facts_text=state["facts_text"],
                allowed_ids=state["allowed_ids"],
            )
        except Exception as exc:
            return {"status": "failed", "error": f"Inspector недоступен: {exc}"}
        issues = list(review_model.issues) + list(state.get("citation_issues", []))
        if not draft_model.citations:
            issues.append("В черновике нет ссылок на источники")
        ok = (
            review_model.verdict == "ok"
            and review_model.citations_ok
            and not review_model.unsupported_claims
            and not review_model.missing_sections
            and not issues
        )
        return {
            "review": review_model.model_dump(),
            "review_issues": issues,
            "status": "ok" if ok else "needs_revision",
        }

    def revise(state: ReportState) -> dict[str, Any]:
        draft_model = ReportDraft.model_validate(state["draft"])
        review_model = ReportReview.model_validate(state.get("review", {}))
        try:
            revised = llm.revise_report(
                draft=draft_model,
                review=review_model,
                facts_text=state["facts_text"],
                allowed_ids=state["allowed_ids"],
            )
        except Exception as exc:
            return {"status": "failed", "error": f"Не удалось исправить черновик: {exc}"}
        return {
            "draft": revised.model_dump(),
            "citations": revised.citations,
            "iterations": int(state.get("iterations", 0)) + 1,
            "citation_issues": [],
            "review_issues": [],
            "status": "ok",
        }

    def finalize(state: ReportState) -> dict[str, Any]:
        draft_model = dict(state.get("draft", {}))
        issues = state.get("review_issues", []) + state.get("citation_issues", [])
        if issues:
            draft_model["text"] = (
                draft_model.get("text", "")
                + "\n\nТребует проверки: "
                + "; ".join(issues[:5])
            )
        return {"draft": draft_model, "status": "ok"}

    def pack_response(state: ReportState) -> dict[str, Any]:
        status = state.get("status")
        if status == "refused":
            return _reply(state, "refuse", {"reason": state.get("error", "Отклонено")})
        if status == "failed":
            return _reply(
                state, "failure", {"reason": state.get("error", "Ошибка выполнения")}
            )

        draft_model = state.get("draft", {})
        citations = draft_model.get("citations", [])
        evidence = []
        if state.get("audit_code"):
            evidence.append({"type": "audit", "audit_code": state["audit_code"]})
        for citation in citations:
            evidence.append({"type": "citation", "source_id": citation})
        return _reply(
            state,
            "inform",
            {
                "draft": draft_model.get("text", ""),
                "citations": citations,
                "evidence": evidence,
                "review": state.get("review", {}),
                "metrics": {"inspector_iterations": int(state.get("iterations", 0))},
            },
        )

    builder = StateGraph(ReportState)
    builder.add_node("parse_acl", parse_acl)
    builder.add_node("collect_facts", collect_facts)
    builder.add_node("draft", draft)
    builder.add_node("validate", validate_citations)
    builder.add_node("review", review)
    builder.add_node("revise", revise)
    builder.add_node("finalize", finalize)
    builder.add_node("pack", pack_response)

    builder.add_edge(START, "parse_acl")
    builder.add_conditional_edges(
        "parse_acl",
        lambda s: "collect_facts" if s.get("status") == "ok" else "pack",
        {"collect_facts": "collect_facts", "pack": "pack"},
    )
    builder.add_conditional_edges(
        "collect_facts",
        lambda s: "draft" if s.get("status", "ok") == "ok" else "pack",
        {"draft": "draft", "pack": "pack"},
    )
    builder.add_conditional_edges(
        "draft",
        lambda s: "validate" if s.get("status") == "ok" else "pack",
        {"validate": "validate", "pack": "pack"},
    )
    builder.add_edge("validate", "review")
    builder.add_conditional_edges(
        "review",
        lambda s: (
            "pack"
            if s.get("status") in ("ok", "failed")
            else ("revise" if int(s.get("iterations", 0)) < 2 else "finalize")
        ),
        {"pack": "pack", "revise": "revise", "finalize": "finalize"},
    )
    builder.add_conditional_edges(
        "revise",
        lambda s: "pack" if s.get("status") == "failed" else "validate",
        {"validate": "validate", "pack": "pack"},
    )
    builder.add_edge("finalize", "pack")
    builder.add_edge("pack", END)

    return builder.compile()
