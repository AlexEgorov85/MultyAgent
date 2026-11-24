"""Report-подагент и Inspector: факты → черновик → проверка → исправление."""

from __future__ import annotations

import re
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from ..acl import ACLMessage, ACLValidationError, make_reply, validate_acl
from ..dialogue import last_audit_code
from ..i18n import t
from ..llm import LLMClient
from ..schemas import ReportDraft, ReportReview
from ..state import ReportState
from ..tools import db as db_tools

AUDIT_CODE_RE = re.compile(r"AUD-\d{4}-[A-Z]+-\d{2}", re.IGNORECASE)

def _citation_pattern(allowed_ids: list[str]) -> re.Pattern[str]:
    """Собирает regex по префиксам допустимых ID, чтобы ловить и опечатки."""
    prefixes = sorted(
        {
            item.split("-", 1)[0].upper()
            for item in allowed_ids
            if "-" in item and item.split("-", 1)[0]
        }
    )
    if prefixes:
        bodies = "|".join(re.escape(prefix) for prefix in prefixes)
        return re.compile(
            rf"(?<![A-Za-z0-9_-])(?:{bodies})-[A-Z0-9]+(?:-[A-Z0-9]+)*"
            r"(?![A-Z0-9_-])",
            re.IGNORECASE,
        )
    return re.compile(
        r"(?<![A-Za-z0-9_-])[A-Z]{2,4}-\d{4}-[A-Z0-9]+(?:-[A-Z0-9]+)*"
        r"(?![A-Z0-9_-])",
        re.IGNORECASE,
    )


def _reply(
    state: ReportState,
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
            return {"status": "refused", "error": t(None, "invalid_acl", error=exc)}
        if message.performative != "request":
            lang = str(message.content.get("language", "ru"))
            return {
                "status": "refused",
                "error": t(lang, "request_only", agent="Report"),
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
            "report_format": str(
                message.content.get("report_format") or "подробный"
            ),
            "signature": str(message.content.get("signature") or "").strip(),
            "language": str(message.content.get("language", "ru")),
            "conversation_id": message.conversation_id,
            "iterations": 0,
        }

    def collect_facts(state: ReportState) -> dict[str, Any]:
        match = AUDIT_CODE_RE.search(state["question"])
        audit_code = (
            match.group(0).upper()
            if match
            else last_audit_code(state.get("conversation_context", ""))
        )
        if not audit_code:
            return {
                "status": "failed",
                "error": t(state.get("language"), "missing_audit_code"),
            }
        audit = db_tools.get_audit(server, audit_code)
        if audit is None:
            return {
                "status": "failed",
                "error": t(
                    state.get("language"), "audit_not_found", code=audit_code
                ),
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
                context=state.get("conversation_context", ""),
                report_format=state.get("report_format", "подробный"),
                profile_text=state.get("profile_text", ""),
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": t(state.get("language"), "draft_failed", error=exc),
            }
        return {"draft": draft_model.model_dump(), "status": "ok"}

    def validate_citations(state: ReportState) -> dict[str, Any]:
        allowed_ids = [str(item) for item in state.get("allowed_ids", [])]
        canonical = {item.upper(): item for item in allowed_ids}
        draft_model = state.get("draft", {})
        text = str(draft_model.get("text", "")).replace("<br>", "\n").replace("<br/>", "\n")
        text = re.sub(r"\[\d+\]", "", text)

        declared_raw = [str(item) for item in draft_model.get("citations", [])]
        declared = [
            canonical[item.upper()] for item in declared_raw if item.upper() in canonical
        ]
        invalid = [item for item in declared_raw if item.upper() not in canonical]

        found_raw = [
            match.upper()
            for match in _citation_pattern(allowed_ids).findall(text)
        ]
        found = [
            canonical[item] for item in dict.fromkeys(found_raw) if item in canonical
        ]
        invalid.extend(item for item in dict.fromkeys(found_raw) if item not in canonical)

        citations: list[str] = []
        for item in declared + found:
            if item not in citations:
                citations.append(item)

        issue_items = list(dict.fromkeys(invalid))
        issues = (
            [f"Несуществующие ID: {', '.join(issue_items)}"] if issue_items else []
        )
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
            return {
                "status": "failed",
                "error": t(state.get("language"), "inspector_failed", error=exc),
            }
        citations = draft_model.citations or state.get("citations", [])
        issues = list(review_model.issues) + list(state.get("citation_issues", []))
        if not citations:
            issues.append("В черновике нет ссылок на источники")
        ok = (
            review_model.verdict == "ok"
            and review_model.citations_ok
            and not review_model.unsupported_claims
            and not review_model.missing_sections
            and not issues
        )
        structure_only = (
            int(state.get("iterations", 0)) >= 1
            and review_model.verdict == "ok"
            and review_model.citations_ok
            and not review_model.unsupported_claims
            and bool(issues)
            and all(issue.startswith("Нет раздела:") for issue in issues)
        )
        return {
            "review": review_model.model_dump(),
            "review_issues": issues,
            "status": "ok" if ok else ("finalize" if structure_only else "needs_revision"),
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
                context=state.get("conversation_context", ""),
                report_format=state.get("report_format", "подробный"),
                profile_text=state.get("profile_text", ""),
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": t(state.get("language"), "revise_failed", error=exc),
            }
        citations = list(revised.citations) or list(draft_model.citations)
        revised_payload = revised.model_dump()
        revised_payload["citations"] = citations
        return {
            "draft": revised_payload,
            "citations": citations,
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
                + "\n\n"
                + t(
                    state.get("language"),
                    "needs_review",
                    issues="; ".join(issues[:5]),
                )
            )
        return {"draft": draft_model, "status": "ok"}

    def pack_response(state: ReportState) -> dict[str, Any]:
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

        draft_model = state.get("draft", {})
        citations = draft_model.get("citations", [])
        draft_text = str(draft_model.get("text", ""))
        # Подпись из профиля — детерминированно, последней строкой документа.
        # Модель видит «Подпись: …» в профиле и может добавить её сама —
        # тогда второй раз не дописываем.
        signature = str(state.get("signature") or "").strip()
        if signature and not draft_text.rstrip().endswith(signature):
            draft_text = draft_text.rstrip() + "\n\n" + signature
        evidence = []
        if state.get("audit_code"):
            evidence.append({"type": "audit", "audit_code": state["audit_code"]})
        for citation in citations:
            evidence.append({"type": "citation", "source_id": citation})
        return _reply(
            state,
            "inform",
            {
                "draft": draft_text,
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
    def after_review(state: ReportState) -> str:
        status = state.get("status")
        if status in ("ok", "failed"):
            return "pack"
        if status == "finalize":
            return "finalize"
        return "revise" if int(state.get("iterations", 0)) < 2 else "finalize"

    builder.add_edge("validate", "review")
    builder.add_conditional_edges(
        "review",
        after_review,
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
