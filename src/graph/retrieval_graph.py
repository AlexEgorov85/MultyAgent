"""Retrieval-подагент: поиск → ответ с цитатами → критик → при необходимости rewrite."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from ..acl import ACLMessage, ACLValidationError, make_reply, validate_acl
from ..i18n import t
from ..llm import LLMClient
from ..rag.vector_store import search
from ..schemas import RetrievalAnswer
from ..state import RetrievalState
from ..textscan import reference_ids

EMPTY_ANSWER = "Подходящих формулировок в актах и методичках не найдено."


def _reply(
    state: RetrievalState,
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
        sender="retrieval_agent",
        content=content,
    )
    return {"acl_response": message.model_dump()}


def build_retrieval_graph(server, llm: LLMClient, embeddings=None, top_k: int = 5):
    """Собирает граф Retrieval-агента."""

    def parse_acl(state: RetrievalState) -> dict[str, Any]:
        """Проверяет ACL-запрос и извлекает вопрос и контекст."""
        try:
            message = validate_acl(state.get("acl_request", {}))
        except ACLValidationError as exc:
            return {"status": "refused", "error": t(None, "invalid_acl", error=exc)}
        if message.performative != "request":
            lang = str(message.content.get("language", "ru"))
            return {
                "status": "refused",
                "error": t(lang, "request_only", agent="Retrieval"),
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
            "analysis_focus": str(message.content.get("analysis_focus", "")),
            "language": str(message.content.get("language", "ru")),
            "conversation_id": message.conversation_id,
            "iterations": 0,
            "warnings": [],
        }

    def retrieve(state: RetrievalState) -> dict[str, Any]:
        """Ищет чанки гибридным поиском (pgvector + FTS)."""
        result = search(server, state["question"], embeddings=embeddings, top_k=top_k)
        chunks = result["chunks"]
        if not chunks:
            return {
                "chunks": [],
                "search_mode": result["mode"],
                "answer": {
                    "text": t(state.get("language"), "empty_retrieval"),
                    "citations": [],
                },
                "citations": [],
                "evidence": [],
            }
        return {"chunks": chunks, "search_mode": result["mode"]}

    def _fallback_answer(
        chunks: list[dict[str, Any]], language: str | None
    ) -> RetrievalAnswer:
        top = chunks[0]
        return RetrievalAnswer(
            text=t(
                language,
                "relevant_fragment",
                title=top["title"],
                content=top["content"][:900],
            ),
            citations=[top["source_id"]],
        )

    def generate(state: RetrievalState) -> dict[str, Any]:
        """Просит LLM ответить по чанкам; при сбое — fallback по top-чанку."""
        try:
            answer = llm.answer_from_chunks(
                question=state["question"],
                chunks=state["chunks"],
                context=state.get("conversation_context", ""),
                profile_text=state.get("profile_text", ""),
                focus=str(state.get("analysis_focus") or ""),
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": t(state.get("language"), "answer_failed", error=exc),
            }
        text = answer.text.strip().lower()
        if not answer.citations or len(text) < 5:
            answer = _fallback_answer(state["chunks"], state.get("language"))
        return {"answer": answer.model_dump(), "citations": answer.citations}

    def validate_citations(state: RetrievalState) -> dict[str, Any]:
        """Проверяет, что цитаты и ID в тексте есть среди чанков."""
        allowed = {chunk["source_id"] for chunk in state.get("chunks", [])}
        answer = state.get("answer", {})
        citations = [item for item in answer.get("citations", []) if item in allowed]
        invalid = [item for item in answer.get("citations", []) if item not in allowed]
        # Проверяем и ID, упомянутые в тексте, а не только citations.
        text = str(answer.get("text", "") or "")
        prefixes = {
            str(item).split("-", 1)[0].upper()
            for item in allowed
            if "-" in str(item) and str(item).split("-", 1)[0]
        }
        text_ids = reference_ids(text, prefixes)
        known = {str(item).upper() for item in allowed}
        invalid_text_ids = [
            item for item in dict.fromkeys(text_ids) if item not in known
        ]
        if invalid_text_ids:
            invalid.extend(invalid_text_ids)
        issues = (
            [
                t(
                    state.get("language"),
                    "invalid_sources",
                    ids=", ".join(dict.fromkeys(invalid)),
                )
            ]
            if invalid
            else []
        )
        if not citations and not invalid and state.get("chunks"):
            fallback = _fallback_answer(
                state["chunks"], state.get("language")
            )
            return {
                "answer": fallback.model_dump(),
                "citations": fallback.citations,
                "citation_issues": [],
            }
        return {
            "answer": {**answer, "citations": citations},
            "citations": citations,
            "citation_issues": issues,
        }

    def critic(state: RetrievalState) -> dict[str, Any]:
        """LLM-критик проверяет обоснованность ответа и цитаты."""
        answer = RetrievalAnswer.model_validate(state["answer"])
        try:
            critique = llm.critique_answer(
                question=state["question"],
                answer=answer,
                chunks=state["chunks"],
                context=state.get("conversation_context", ""),
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": t(state.get("language"), "critic_failed", error=exc),
            }
        issues = list(critique.issues) + list(state.get("citation_issues", []))
        if not answer.citations:
            issues.append("В ответе нет ссылок на источники")
        # Вердикт «rewrite» без конкретных замечаний не даёт, что править:
        # такой ответ принимаем, иначе граф дважды переписывает корректный
        # текст и выходит за лимит вызовов LLM.
        suggestions = [
            str(item).strip() for item in critique.suggestions if str(item).strip()
        ]
        ok = (
            critique.grounded
            and critique.citations_ok
            and not issues
            and not suggestions
        )
        return {
            "critique": critique.model_dump(),
            "critic_issues": issues + suggestions,
            "status": "ok" if ok else "needs_rewrite",
        }

    def rewrite(state: RetrievalState) -> dict[str, Any]:
        """Переписывает ответ по замечаниям критика."""
        answer = RetrievalAnswer.model_validate(state["answer"])
        try:
            rewritten = llm.rewrite_answer(
                question=state["question"],
                answer=answer,
                issues=state.get("critic_issues", []),
                chunks=state["chunks"],
                context=state.get("conversation_context", ""),
                profile_text=state.get("profile_text", ""),
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": t(state.get("language"), "revise_failed", error=exc),
            }
        return {
            "answer": rewritten.model_dump(),
            "citations": rewritten.citations,
            "iterations": int(state.get("iterations", 0)) + 1,
            "critic_issues": [],
            "citation_issues": [],
            "status": "ok",
        }

    def finalize(state: RetrievalState) -> dict[str, Any]:
        """Добавляет оговорку к ответу, если замечания остались."""
        answer = dict(state.get("answer", {}))
        issues = state.get("critic_issues", []) + state.get("citation_issues", [])
        if issues:
            answer["text"] = (
                answer.get("text", "")
                + "\n\n"
                + t(
                    state.get("language"),
                    "needs_review",
                    issues="; ".join(issues[:5]),
                )
            )
        return {"answer": answer, "status": "ok"}

    def pack_response(state: RetrievalState) -> dict[str, Any]:
        """Упаковывает ответ Retrieval в ACL-сообщение."""
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
        citations = state.get("citations", [])
        chunks_by_source = {
            chunk["source_id"]: chunk for chunk in state.get("chunks", [])
        }
        evidence = [
            {
                "type": chunks_by_source[citation]["source_type"],
                "source_id": citation,
            }
            for citation in citations
            if citation in chunks_by_source
        ]
        content = {
            "answer": answer.get("text", ""),
            "citations": citations,
            "sources": [
                {
                    "source_id": source_id,
                    "source_type": chunks_by_source[source_id]["source_type"],
                    "title": chunks_by_source[source_id]["title"],
                }
                for source_id in citations
                if source_id in chunks_by_source
            ],
            "evidence": evidence,
            "search_mode": state.get("search_mode", "fts"),
            "metrics": {
                "critic_iterations": int(state.get("iterations", 0)),
                "chunks": len(state.get("chunks", [])),
            },
        }
        return _reply(state, "inform", content)

    builder = StateGraph(RetrievalState)
    builder.add_node("parse_acl", parse_acl)
    builder.add_node("retrieve", retrieve)
    builder.add_node("generate", generate)
    builder.add_node("validate", validate_citations)
    builder.add_node("critic", critic)
    builder.add_node("rewrite", rewrite)
    builder.add_node("finalize", finalize)
    builder.add_node("pack", pack_response)

    builder.add_edge(START, "parse_acl")
    builder.add_conditional_edges(
        "parse_acl",
        lambda s: "retrieve" if s.get("status") == "ok" else "pack",
        {"retrieve": "retrieve", "pack": "pack"},
    )
    builder.add_conditional_edges(
        "retrieve",
        lambda s: "generate" if s.get("chunks") else "pack",
        {"generate": "generate", "pack": "pack"},
    )
    builder.add_conditional_edges(
        "generate",
        lambda s: "pack" if s.get("status") == "failed" else "validate",
        {"validate": "validate", "pack": "pack"},
    )
    builder.add_edge("validate", "critic")
    builder.add_conditional_edges(
        "critic",
        lambda s: (
            "pack"
            if s.get("status") in ("ok", "failed")
            else ("rewrite" if int(s.get("iterations", 0)) < 2 else "finalize")
        ),
        {"pack": "pack", "rewrite": "rewrite", "finalize": "finalize"},
    )
    builder.add_conditional_edges(
        "rewrite",
        lambda s: "pack" if s.get("status") == "failed" else "validate",
        {"validate": "validate", "pack": "pack"},
    )
    builder.add_edge("finalize", "pack")
    builder.add_edge("pack", END)

    return builder.compile()
