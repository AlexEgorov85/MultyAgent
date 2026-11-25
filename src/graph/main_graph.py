"""Основной граф: маршрутизация, ACL-вызовы агентов, память и финализация."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .. import dialogue_store
from ..acl import append_acl_log, make_acl_message
from ..dialogue import build_dialogue_context
from ..dialogue_slots import DialogueSlots, augment_query, merge_slots
from ..guardrails import check_final_answer, check_request, extract_sql
from ..llm import LLMClient
from ..memory import store as memory_store
from ..presentation import present
from ..state import MainState
from .analytics_graph import build_analytics_graph, known_themes
from .investigation_graph import build_investigation_graph
from .report_graph import build_report_graph
from .retrieval_graph import build_retrieval_graph

logger = logging.getLogger(__name__)


def _log_acl(message: dict[str, Any]) -> None:
    """Дописывает ACL-сообщение в журнал, не ломая ответ при ошибке записи."""
    if not message:
        return
    try:
        append_acl_log(message)
    except Exception as exc:  # журнал не должен ломать ответ
        logger.warning("Не удалось записать ACL-журнал: %s", exc)


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


def _acl_content(acl: Any) -> dict[str, Any]:
    """Содержимое ACL-ответа или пустой словарь."""
    content = acl.get("content") if isinstance(acl, dict) else None
    return content if isinstance(content, dict) else {}


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


def _same_question(left: str, right: str) -> bool:
    """Сравнивает вопросы без регистра, ё и пунктуации по краям."""
    def norm(text: str) -> str:
        return (
            " ".join(str(text or "").lower().replace("ё", "е").split())
            .strip(" ?!.,;:")
        )

    return bool(norm(left)) and norm(left) == norm(right)


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

    def load_memory(state: MainState, config: RunnableConfig) -> dict[str, Any]:
        """Загружает профиль, историю диалога и slots для текущего хода."""
        messages = state.get("messages", [])
        question = _last_user_text(messages)
        language = str(state.get("language") or "ru")
        configurable = (config or {}).get("configurable", {})
        thread_id = str(configurable.get("thread_id") or "")
        conversation_id = (
            str(state.get("conversation_id") or "").strip()
            or thread_id
            or "conv-main"
        )

        db_history: list[dict[str, str]] = []
        try:
            db_history = dialogue_store.load_history(
                server,
                conversation_id,
                auditor_id=str(state.get("auditor_id") or ""),
            )
        except Exception as exc:  # история не должна ломать ответ
            logger.warning("История диалога недоступна: %s", exc)

        context = build_dialogue_context(
            db_history or messages,
            state.get("client_history", []),
            question,
            language=language,
        )
        pending = state.get("pending_clarification")
        if not pending:
            try:
                pending = dialogue_store.load_pending_clarification(
                    server,
                    conversation_id,
                    auditor_id=str(state.get("auditor_id") or ""),
                )
            except Exception as exc:
                logger.warning("Не удалось загрузить уточнение: %s", exc)
                pending = None
        clarification_history = [
            str(item)
            for item in state.get("clarification_history") or []
            if str(item).strip()
        ]
        if (
            isinstance(pending, dict)
            and pending.get("question")
            and pending["question"] not in clarification_history
        ):
            clarification_history.append(str(pending["question"]))
        auditor_id = state.get("auditor_id", "")
        profile = memory_store.load_profile(server, auditor_id)
        slots = merge_slots(state.get("dialogue_slots"), question)
        return {
            "user_query": question,
            "resolved_query": question,
            "resolved_reason": "",
            "dialogue_context": context,
            "dialogue_slots": slots.model_dump(),
            "profile": profile,
            "conversation_id": conversation_id,
            "turn_id": uuid.uuid4().hex,
            "route": "",
            "route_reason": "",
            "route_confidence": 0.0,
            "route_error": False,
            "pending_clarification": pending or {},
            "clarification": {},
            "clarification_assumption": "",
            "clarification_history": clarification_history[-10:],
            "answered_clarification": False,
            "meta_query": False,
            "guardrail": {},
            "answer_guardrail": {},
            "final_answer": "",
            "acl_response": {},
            "evidence": [],
            "presentation": {},
            "trace": [],
            "memory_saved": False,
            "metrics": {"started_at": time.perf_counter()},
        }

    def resolve_query(state: MainState) -> dict[str, Any]:
        """Переформулирует уточнение и сохраняет структурированные слоты."""
        question = state.get("user_query", "")
        context = state.get("dialogue_context", "")
        text = question
        reason = ""
        assumption = ""
        resolved_answer = False
        meta_query = False
        pending = dict(state.get("pending_clarification") or {})

        if pending:
            resolver = getattr(llm, "resolve_clarification", None)
            resolution = None
            if resolver is not None:
                try:
                    resolution = resolver(
                        original_query=str(pending.get("original_query") or ""),
                        clarification=str(pending.get("question") or ""),
                        answer=question,
                        context=context,
                        profile_text=memory_store.profile_text(
                            state.get("profile", {})
                        ),
                        language=str(state.get("language") or "ru"),
                    )
                except Exception:
                    resolution = None
            if resolution is None:
                pending = {}
            elif resolution.topic_changed:
                pending = {}
            elif resolution.resolved and resolution.question.strip():
                text = " ".join(resolution.question.split()).strip()
                reason = "ответ на уточнение"
                pending = {}
                resolved_answer = True
            elif (
                resolution.clarification_question.strip()
                and int(pending.get("attempts", 0)) < 1
                and not _same_question(
                    resolution.clarification_question,
                    str(pending.get("question") or ""),
                )
            ):
                next_pending = {
                    **pending,
                    "question": " ".join(
                        resolution.clarification_question.split()
                    ).strip(),
                    "attempts": int(pending.get("attempts", 0)) + 1,
                    # Варианты относились к предыдущему вопросу.
                    "options": [],
                }
                slots = merge_slots(state.get("dialogue_slots"), question)
                return {
                    "pending_clarification": next_pending,
                    "clarification": next_pending,
                    "resolved_query": question,
                    "answered_clarification": False,
                    "final_answer": next_pending["question"],
                    "dialogue_slots": slots.model_dump(),
                }
            else:
                text = (
                    " ".join(resolution.question.split()).strip()
                    or str(pending.get("original_query") or "").strip()
                    or question
                )
                assumption = " ".join(resolution.assumption.split()).strip()
                pending = {}
                resolved_answer = bool(text)

        if not resolved_answer and context:
            resolver = getattr(llm, "resolve_followup", None)
            if resolver is not None:
                try:
                    resolved = resolver(
                        question=question,
                        context=context,
                        profile_text=memory_store.profile_text(
                            state.get("profile", {})
                        ),
                        language=str(state.get("language") or "ru"),
                    )
                    candidate = " ".join(str(resolved.question or "").split()).strip()
                    if resolved.is_meta:
                        meta_query = True
                        text = question
                        reason = str(resolved.reason or "")
                    elif resolved.is_followup and candidate and len(candidate) <= 500:
                        text = candidate
                        reason = str(resolved.reason or "")
                except Exception:
                    text = question
                    reason = ""

        slots = merge_slots(state.get("dialogue_slots"), question, text)
        text = augment_query(text, question)
        return {
            "resolved_query": text,
            "resolved_reason": reason,
            "dialogue_slots": slots.model_dump(),
            "pending_clarification": pending,
            "clarification_assumption": assumption,
            "answered_clarification": resolved_answer,
            "meta_query": meta_query,
            "route": "meta" if meta_query else state.get("route", ""),
        }

    def update_memory(state: MainState) -> dict[str, Any]:
        """Маршрут memory: LLM извлекает факты, код валидирует и пишет.

        Решение «это запрос на запоминание?» принимает router, поэтому
        смешанные реплики («я проверяю ипотеку, сколько отклонений?»)
        сюда не попадают и не теряют аналитическую часть вопроса.
        """
        question = state.get("resolved_query") or state.get("user_query", "")
        auditor_id = str(state.get("auditor_id") or "")
        if not auditor_id:
            return {
                "memory_saved": False,
                "final_answer": _pick(
                    state,
                    "Не удалось обновить профиль: не задан идентификатор аудитора.",
                    "Cannot update the profile: auditor ID is missing.",
                ),
            }

        themes = known_themes(server)
        update = None
        extractor = getattr(llm, "extract_memory", None)
        if extractor is not None:
            try:
                update = extractor(
                    question=question,
                    profile_text=memory_store.profile_text(
                        state.get("profile", {})
                    ),
                    themes=themes,
                    context=state.get("dialogue_context", ""),
                    language=str(state.get("language") or "ru"),
                )
            except Exception:
                update = None
        facts = (
            {fact.key: fact.value for fact in update.facts}
            if update is not None
            else {}
        )
        forget = list(update.forget) if update is not None else []

        for key in forget:
            if key in memory_store.ALLOWED_KEYS:
                memory_store.delete_fact(server, auditor_id, key)
        saved: dict[str, str] = {}
        for key, value in facts.items():
            normalized = memory_store.normalize_fact(key, value, themes)
            if normalized is None:
                continue
            memory_store.save_fact(server, auditor_id, key, normalized)
            saved[key] = normalized

        profile = memory_store.load_profile(server, auditor_id)
        stored = memory_store.load_stored(server, auditor_id)
        if saved:
            answer = _pick(
                state, "Профиль сохранён: ", "Profile saved: "
            ) + memory_store.profile_text(profile)
        elif forget:
            if stored:
                answer = _pick(
                    state, "Профиль обновлён: ", "Profile updated: "
                ) + memory_store.profile_text(profile)
            else:
                answer = _pick(
                    state,
                    "Профиль сброшен: сохранённые предпочтения удалены.",
                    "Profile reset: saved preferences were removed.",
                )
        elif facts:
            answer = _pick(
                state,
                "Не удалось распознать предпочтения. Пример: «Запомни: "
                "я проверяю ипотеку, акт нужен в кратком формате».",
                "Could not recognize the preferences. Example: “Remember: "
                "I audit mortgages, keep the act brief”.",
            )
        elif stored:
            answer = _pick(
                state, "Ваш профиль: ", "Your profile: "
            ) + memory_store.profile_text(profile)
        else:
            answer = _pick(
                state,
                "Профиль пока пуст. Скажите, что запомнить, например: "
                "«Я проверяю ипотеку, акт нужен в кратком формате».",
                "The profile is empty. Tell me what to remember, e.g. "
                "“I audit mortgages, keep the act brief”.",
            )
        return {
            "memory_saved": bool(saved),
            "profile": profile,
            "final_answer": answer,
        }

    def guard_request(state: MainState) -> dict[str, Any]:
        """Проверяет запрос до Router: изменение данных, PII, инъекции."""
        user_query = state.get("user_query", "")
        resolved_query = state.get("resolved_query", "")
        conversation_id = str(state.get("conversation_id") or "")
        result = check_request(
            user_query, conversation_id=conversation_id
        )
        if result.safe and resolved_query and resolved_query != user_query:
            result = check_request(
                resolved_query, conversation_id=conversation_id
            )
        if not result.safe:
            return {
                "guardrail": result.model_dump(),
                "route": "unsafe",
                "route_reason": result.reason,
            }
        return {"guardrail": result.model_dump()}

    def router(state: MainState) -> dict[str, Any]:
        """Выбирает маршрут LLM-роутером; при сбое — честный fallback."""
        question = state.get("resolved_query") or state.get("user_query", "")
        # Маршрут выбирает LLM по смыслу вопроса. Доменных эвристик
        # («если есть AUD-код и слово похож», «если есть повторн и наход»)
        # здесь намеренно нет: они не покрывают все формулировки и
        # перекрывают друг друга. Детерминированный код остаётся только
        # аварийным fallback'ом на случай недоступности модели.
        try:
            decision = llm.route(
                question=question,
                profile_text=memory_store.profile_text(state.get("profile", {})),
                context=state.get("dialogue_context", ""),
            )
        except Exception:
            decision = None
        if decision is None:
            return _fallback_route(question)
        return {
            "route": decision.route,
            "route_reason": decision.reason,
            "route_confidence": decision.confidence,
            "analytics_mode": decision.analytics_mode,
        }

    def _fallback_route(question: str) -> dict[str, Any]:
        """Честный fallback, если LLM недоступна.

        Маршрут не угадываем даже для приветствия: лучше сказать, что
        маршрутизация недоступна, чем выполнить не тот агент.
        """
        return {
            "route": "out_of_domain",
            "route_reason": "маршрутизация недоступна",
            "route_error": True,
        }

    def _call_branch(state: MainState, receiver: str, graph) -> dict[str, Any]:
        profile = state.get("profile", {})
        content: dict[str, Any] = {
            "question": state.get("resolved_query")
            or state.get("user_query", ""),
            "original_question": state.get("user_query", ""),
            "conversation_context": state.get("dialogue_context", ""),
            "dialogue_slots": state.get("dialogue_slots", {}),
            "auditor_id": state.get("auditor_id", ""),
            "language": state.get("language", "ru"),
            "asked_clarifications": [
                str(item)
                for item in state.get("clarification_history") or []
                if str(item).strip()
            ][-5:],
            # Профиль передаётся всем агентам как блок предпочтений
            # в промпте, а не как условия вопроса.
            "profile_text": memory_store.profile_text(profile),
        }
        if receiver == "analytics_agent":
            content["analytics_mode"] = str(state.get("analytics_mode") or "sql")
        if receiver == "report_agent":
            content["report_format"] = str(
                profile.get("default_format") or "подробный"
            )
            signature = str(profile.get("signature") or "").strip()
            if signature:
                content["signature"] = signature
        request = make_acl_message(
            performative="request",
            sender="orchestrator",
            receiver=receiver,
            content=content,
            conversation_id=state.get("conversation_id", "conv-main"),
        )
        _log_acl(request.model_dump())
        result = graph.invoke({"acl_request": request.model_dump()})
        response = result.get("acl_response", {})
        if isinstance(response, dict) and response:
            _log_acl(response)
        content = response.get("content", {})
        return {
            "acl_response": response,
            "final_answer": _response_text(content),
            "evidence": content.get("evidence", []),
            "analytics_mode": str(
                content.get("analytics_mode")
                or state.get("analytics_mode")
                or "sql"
            ),
        }

    def analytics_branch(state: MainState) -> dict[str, Any]:
        """Вызывает Analytics-подагента по ACL."""
        return _call_branch(state, "analytics_agent", analytics)

    def retrieval_branch(state: MainState) -> dict[str, Any]:
        """Вызывает Retrieval-подагента по ACL."""
        return _call_branch(state, "retrieval_agent", retrieval)

    def report_branch(state: MainState) -> dict[str, Any]:
        """Вызывает Report-подагента по ACL."""
        return _call_branch(state, "report_agent", report)

    def investigation_branch(state: MainState) -> dict[str, Any]:
        """Вызывает Investigation Coordinator по ACL."""
        return _call_branch(state, "investigation_coordinator", investigation)

    def refusal(state: MainState) -> dict[str, Any]:
        """Формирует отказ для unsafe/out_of_domain запросов."""
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
        elif state.get("route_error"):
            answer = _pick(
                state,
                "Сервис модели временно недоступен. Повторите запрос позже.",
                "The model service is temporarily unavailable. Please retry later.",
            )
        else:
            answer = _pick(
                state,
                "Я помогаю только по вопросам внутреннего аудита.",
                "I can only help with internal audit questions.",
            )
        return {"final_answer": answer, "evidence": []}

    def _smalltalk_kind(state: MainState) -> str:
        """Подтип smalltalk из reason, с запасным разбором вопроса.

        Основной контракт — ``smalltalk:<kind>`` из router.md. Если модель
        вернула свободный текст, не показываем приветствие на «что умеешь?»
        и благодарность: это ошибка формата, а не повод потерять смысл.
        """
        reason = str(state.get("route_reason") or "").strip().lower()
        if reason.startswith("smalltalk:") and ":" in reason:
            return reason.split(":", 1)[-1] or "greeting"
        question = str(
            state.get("resolved_query") or state.get("user_query") or ""
        ).lower()
        if any(word in question for word in ("спасибо", "благодар")):
            return "thanks"
        if any(
            word in question
            for word in ("что ты умеешь", "что ты можешь", "возможност")
        ):
            return "capabilities"
        return "greeting"

    def smalltalk(state: MainState) -> dict[str, Any]:
        """Отвечает на приветствие, благодарность или вопрос о возможностях."""
        kind = _smalltalk_kind(state)
        capabilities = _pick(
            state,
            "Я — ассистент внутреннего аудитора. Умею:\n\n"
            "- считать показатели по базе: проверки, пункты, отклонения, просрочки;\n"
            "- искать подтверждения в актах и методичках;\n"
            "- готовить проект раздела акта и проверять его Inspector'ом;\n"
            "- разбирать причины отклонений по данным и цитатам;\n"
            "- запоминать профиль аудитора между сессиями.\n\n"
            "Например: «Сколько завершённых проверок по ипотеке в 2026 году?»",
            "I am an internal audit assistant. I can:\n\n"
            "- compute metrics from the database: audits, items, deviations, overdue;\n"
            "- find evidence in acts and methodologies;\n"
            "- draft an act section and review it with the Inspector;\n"
            "- investigate why deviations grew, using data and citations;\n"
            "- remember the auditor profile between sessions.\n\n"
            "For example: “How many mortgage audits were completed in 2026?”",
        )
        greeting = _pick(
            state,
            "Здравствуйте! Я ассистент внутреннего аудитора. Могу посчитать "
            "показатели по базе, найти подтверждения в актах, подготовить проект "
            "раздела акта и разобрать причины отклонений. Чем помочь?",
            "Hello! I am an internal audit assistant. I can compute metrics from "
            "the database, find evidence in acts, draft an act section and "
            "investigate deviations. How can I help?",
        )
        thanks = _pick(
            state,
            "Пожалуйста! Если нужно, задайте следующий вопрос по проверкам, актам "
            "или отклонениям.",
            "You are welcome! Ask another question about audits, acts or deviations.",
        )
        if kind == "capabilities":
            answer = capabilities
        elif kind == "thanks":
            answer = thanks
        else:
            answer = greeting
        formatter = getattr(llm, "format_answer", None)
        if formatter is not None:
            try:
                text = formatter(
                    question=state.get("user_query", ""),
                    draft=answer,
                    kind="smalltalk",
                    language=str(state.get("language") or "ru"),
                    context=state.get("dialogue_context", ""),
                )
            except Exception:
                text = ""
            text = str(text or "").strip()
            if text:
                answer = text
        return {"final_answer": answer, "evidence": []}

    def explain_previous(state: MainState) -> dict[str, Any]:
        """Поясняет предыдущий ответ, не выполняя новый запрос."""
        explainer = getattr(llm, "explain_previous", None)
        answer = ""
        if explainer is not None:
            try:
                answer = explainer(
                    question=state.get("user_query", ""),
                    context=state.get("dialogue_context", ""),
                    profile_text=memory_store.profile_text(
                        state.get("profile", {})
                    ),
                    language=str(state.get("language") or "ru"),
                )
            except Exception:
                answer = ""
        if not answer:
            answer = _pick(
                state,
                "Уточните, какой фрагмент предыдущего ответа объяснить.",
                "Please specify which part of the previous answer to explain.",
            )
        return {"final_answer": answer, "evidence": []}

    def guard_answer(state: MainState) -> dict[str, Any]:
        """Финальная проверка ответа и пометка ответов без evidence."""
        route = state.get("route")
        factual_routes = {"analytics", "retrieval", "report", "investigation"}
        clarify = bool(
            state.get("clarification")
            or _acl_content(state.get("acl_response")).get("clarification")
        )
        result = check_final_answer(
            state.get("final_answer", ""),
            extract_sql(state.get("acl_response")),
            # Сообщение о недоступности модели — не ответ вне домена.
            is_domain=route != "out_of_domain" or bool(state.get("route_error")),
            evidence=state.get("evidence", []),
            is_factual=str(route or "") in factual_routes and not clarify,
            route=str(route or ""),
            conversation_id=str(state.get("conversation_id") or ""),
        )
        update: dict[str, Any] = {"answer_guardrail": result.model_dump()}
        if not result.safe:
            update["final_answer"] = result.final_answer
        elif result.warnings:
            # Не выдаём утверждение за подтверждённый факт: помечаем ответ.
            note = _pick(
                state,
                "Пометка: ответ не подтверждён evidence из базы или источников.",
                "Note: the answer is not supported by database or source evidence.",
            )
            answer = str(state.get("final_answer") or "").rstrip()
            update["final_answer"] = f"{answer}\n\n{note}".strip()
        return update

    def finalize(state: MainState) -> dict[str, Any]:
        """Сохраняет сообщения, trace и метрики в историю диалога."""
        answer = state.get("final_answer", "")
        metrics = dict(state.get("metrics", {}))
        started = metrics.pop("started_at", None)
        if started is not None:
            metrics["latency_total_sec"] = round(time.perf_counter() - started, 4)
        acl = state.get("acl_response") or {}
        content = _acl_content(acl)
        clarification = state.get("clarification") or content.get("clarification")
        history = [
            str(item)
            for item in state.get("clarification_history") or []
            if str(item).strip()
        ]
        if isinstance(clarification, dict) and clarification.get("question"):
            question = str(clarification["question"])
            if not any(_same_question(question, item) for item in history):
                history.append(question)
        assumption = str(state.get("clarification_assumption") or "").strip()
        if assumption:
            note = _pick(
                state,
                f"Допущение: {assumption}",
                f"Assumption: {assumption}",
            )
            answer = f"{answer}\n\n{note}".strip()
        payload: dict[str, Any] | None = None
        if content.get("rows") and content.get("columns"):
            payload = {
                "rows": content.get("rows")[:200],
                "columns": content.get("columns"),
                "sql": str(content.get("sql") or ""),
                "question": str(
                    content.get("source_question")
                    or state.get("user_query")
                    or ""
                ),
            }
            if content.get("chart"):
                payload["chart"] = content.get("chart")
        if clarification:
            payload = dict(payload or {})
            payload["clarification"] = clarification
        try:
            dialogue_store.append_turn(
                server,
                conversation_id=state.get("conversation_id", ""),
                auditor_id=state.get("auditor_id", ""),
                turn_id=state.get("turn_id", ""),
                user_text=state.get("user_query", ""),
                assistant_text=answer,
                trace=state.get("trace", []),
                resolved_query=state.get("resolved_query", ""),
                payload=payload,
            )
        except Exception as exc:  # ответ важнее записи истории
            logger.warning("Не удалось сохранить историю диалога: %s", exc)
        return {
            "messages": [{"type": "ai", "content": answer}],
            "final_answer": answer,
            "pending_clarification": clarification
            if isinstance(clarification, dict) and clarification
            else (state.get("pending_clarification") or {}),
            "clarification_history": history[-10:],
            "metrics": metrics,
        }

    builder = StateGraph(MainState)
    builder.add_node("load_memory", load_memory)
    builder.add_node("update_memory", update_memory)
    builder.add_node("resolve_query", resolve_query)
    builder.add_node("guard_request", guard_request)
    builder.add_node("router", router)
    builder.add_node("analytics", analytics_branch)
    builder.add_node("retrieval", retrieval_branch)
    builder.add_node("report", report_branch)
    builder.add_node("investigation", investigation_branch)
    builder.add_node("explain_previous", explain_previous)
    builder.add_node("smalltalk", smalltalk)
    builder.add_node("refusal", refusal)
    builder.add_node("guard_answer", guard_answer)
    builder.add_node("present", present)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "load_memory")
    builder.add_edge("load_memory", "resolve_query")
    builder.add_conditional_edges(
        "resolve_query",
        lambda s: (
            "guard_answer"
            if s.get("clarification")
            else ("explain_previous" if s.get("meta_query") else "guard_request")
        ),
        {
            "guard_answer": "guard_answer",
            "explain_previous": "explain_previous",
            "guard_request": "guard_request",
        },
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
            "meta": "explain_previous",
            "memory": "update_memory",
            "smalltalk": "smalltalk",
            "out_of_domain": "refusal",
            "unsafe": "refusal",
        },
    )
    for branch in (
        "analytics",
        "retrieval",
        "report",
        "investigation",
        "explain_previous",
        "update_memory",
        "smalltalk",
        "refusal",
    ):
        builder.add_edge(branch, "guard_answer")
    builder.add_edge("guard_answer", "present")
    builder.add_edge("present", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())
