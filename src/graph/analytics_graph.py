"""Analytics-подагент: ACL → план → SQL/шаблон → проверка → выполнение → ответ."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Literal

import psycopg
from langgraph.graph import END, START, StateGraph

from .. import config, dialogue_store
from ..acl import ACLMessage, ACLValidationError, make_reply, validate_acl
from ..charts import ground_chart_points
from ..dialogue import last_audit_code
from ..i18n import t
from ..llm import LLMClient
from ..query.compiler import QueryCompileError, compile_query_plan
from ..query.intent import apply_plan_gaps
from ..query.templates import template_parameters, template_plan_problems
from ..schemas import SQLPlan
from ..semantic.catalog import catalog_text, get_metric
from ..state import AnalyticsState
from ..textscan import audit_codes, number_tokens
from ..tools import db as db_tools
from ..tools.registry import TOOL_SPECS, execute_tool
from ..tools.sql_guard import UnsafeSQLError, validate_readonly_sql

ANALYTICS_MODES = ("sql", "drilldown", "multi_tool", "chart")

logger = logging.getLogger(__name__)


def _normalize_question(text: str) -> str:
    """Нормализует текст вопроса для проверки повторов."""
    return (
        " ".join(str(text or "").lower().replace("ё", "е").split())
        .strip(" ?!.,;:")
    )


def _complete_metric_dimensions(plan):
    """Дополняет план обязательными измерениями метрики.

    Метрика сама описывает, какие поля нужны, чтобы назвать результат:
    например, «самое крупное отклонение» бессмысленно без названия пункта
    и кода проверки. Это контракт semantic layer, а не правило под вопрос.
    """
    try:
        spec = get_metric(plan.metric)
    except KeyError:
        return plan
    missing = [
        name
        for name in spec.required_dimensions
        if name not in plan.dimensions
    ]
    update: dict[str, Any] = {}
    if missing:
        update["dimensions"] = [*plan.dimensions, *missing]
    if spec.single_row and plan.limit != 1:
        update["limit"] = 1
    return plan.model_copy(update=update) if update else plan


def _split_tool_call(name: str) -> tuple[str, dict[str, str]]:
    """Разбирает форму `tool(arg=value, ...)`, если модель положила туда аргументы.

    Модель иногда пишет аргументы в `name`, а `arguments` оставляет пустым.
    Формат простой (пары ключ=значение через запятую), поэтому разбираем его
    без регулярных выражений и не теряем `item_type` и другие фильтры.
    """
    text = str(name or "").strip()
    if not text.endswith(")") or "(" not in text:
        return text, {}
    head, _, tail = text.partition("(")
    parsed: dict[str, str] = {}
    for part in tail[:-1].split(","):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and value:
            parsed[key] = value
    return head.strip(), parsed


def _template_parameters(
    templates: list[dict[str, Any]],
    template_key: str,
    parameters: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str]:
    """Проверяет выбранный LLM шаблон и его параметры."""
    key = str(template_key or "").strip()
    template = next(
        (item for item in templates if item.get("template_key") == key),
        None,
    )
    if template is None:
        return None, f"шаблон не найден: {key}"

    declared = template.get("parameters") or {}
    if not isinstance(declared, dict):
        return None, "у шаблона некорректные параметры"

    provided = dict(parameters or {})
    unknown = sorted(set(provided) - set(declared))
    if unknown:
        return None, f"неизвестные параметры: {', '.join(unknown)}"
    return {**declared, **provided}, ""


def known_themes(server) -> list[str]:
    """Возвращает список тем (theme_code) из карманов аудита."""
    from .. import db_runtime

    with db_runtime.connect(server, role=db_runtime.APP_ROLE) as conn:
        rows = conn.execute(
            "SELECT DISTINCT lower(theme_code) AS theme FROM audit.audit_pockets "
            "ORDER BY theme"
        ).fetchall()
    return [str(row[0]) for row in rows]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _summary_allowed_numbers(
    rows: list[dict[str, Any]],
    columns: list[str],
) -> set[float]:
    """Числа, которые модель вправе назвать: строки, итоги, число строк."""
    allowed: set[float] = {float(len(rows))}
    for column in columns:
        values: list[float] = []
        for row in rows:
            value = row.get(column)
            if _is_number(value):
                number = float(value)
                allowed.add(number)
                allowed.add(round(number, 2))
                values.append(number)
        if values:
            # Итог по колонке — допустимое производное число.
            total = sum(values)
            allowed.add(total)
            allowed.add(round(total, 2))
    return allowed


def _number_grounded(value: float, allowed: set[float]) -> bool:
    """Число совпадает с допустимым, его округлением или процентом от доли."""
    if round(value, 2) in allowed:
        return True
    for candidate in allowed:
        if round(value, 1) == round(candidate, 1):
            return True
        if (
            0 < abs(candidate) <= 1
            and abs(value) <= 100
            and round(value, 1) == round(candidate * 100, 1)
        ):
            # Доля 0.0746 и «7,5%» — одно и то же число в разных единицах.
            return True
    return False


def _summary_numbers_supported(
    text: str,
    rows: list[dict[str, Any]],
    columns: list[str],
    claims: list[float] | None = None,
) -> bool:
    """Проверяет, что LLM не придумала числа вне таблицы.

    Годы (2025, 2026) разрешены как названия разрезов. Если модель вернула
    структурированный список использованных чисел (`claims`), каждое число
    в тексте должно быть в нём объявлено: так проверка не проходит вхолостую,
    когда модель записала число словами.
    """
    allowed = _summary_allowed_numbers(rows, columns)
    declared: set[float] | None = None
    if claims is not None:
        declared = set()
        for claim in claims:
            if not _is_number(claim):
                return False
            value = float(claim)
            # Годы — не результат запроса, их можно называть свободно.
            if 2000 <= value <= 2099:
                declared.add(value)
                continue
            if not _number_grounded(value, allowed):
                return False
            declared.add(value)

    for token in number_tokens(text):
        try:
            value = float(token.replace(",", "."))
        except ValueError:
            continue
        if 2000 <= value <= 2099:
            continue
        if not _number_grounded(value, allowed):
            return False
        if declared is not None and not _number_grounded(value, declared):
            return False
    return True


def _reply(
    state: AnalyticsState,
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
        sender="analytics_agent",
        content=content,
    )
    return {"acl_response": message.model_dump()}


def _refuse(state: AnalyticsState, reason: str) -> dict[str, Any]:
    return {"status": "refused", "error": reason}


def _fail(state: AnalyticsState, reason: str) -> dict[str, Any]:
    return {"status": "failed", "error": reason}


def _format_with_llm(
    llm: LLMClient,
    state: AnalyticsState,
    *,
    draft: str,
    kind: str,
    facts: Any = None,
) -> tuple[str, str]:
    """Оформляет черновик ответа моделью; при сбое возвращает как есть."""
    formatter = getattr(llm, "format_answer", None)
    if formatter is None:
        return draft, "agent"
    try:
        text = formatter(
            question=state.get("question", ""),
            draft=draft,
            kind=kind,
            facts=(
                json.dumps(facts, ensure_ascii=False, default=str) if facts else ""
            ),
            language=str(state.get("language") or "ru"),
            context=state.get("conversation_context", ""),
            profile_text=state.get("profile_text", ""),
        )
    except Exception:
        text = ""
    text = str(text or "").strip()
    return (text, "llm") if text else (draft, "agent")


def build_analytics_graph(server, llm: LLMClient):
    """Собирает и компилирует граф Analytics-агента."""

    def parse_acl(state: AnalyticsState) -> dict[str, Any]:
        """Проверяет ACL-запрос и извлекает вопрос, режим и контекст."""
        try:
            message = validate_acl(state.get("acl_request", {}))
        except ACLValidationError as exc:
            return {
                "status": "refused",
                "error": t(None, "invalid_acl", error=exc),
            }

        if message.performative != "request":
            lang = str(message.content.get("language", "ru"))
            return {
                "status": "refused",
                "error": t(lang, "request_only", agent="Analytics"),
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

        mode = str(message.content.get("analytics_mode") or "sql").strip().lower()
        if mode not in ANALYTICS_MODES:
            mode = "sql"
        chart_source = str(
            message.content.get("chart_source") or "current"
        ).strip().lower()
        if chart_source not in ("current", "previous"):
            chart_source = "current"
        if mode == "drilldown":
            # Детализация возможна только по коду проверки. Если кода нет
            # ни в вопросе, ни в контексте — это обычный агрегат.
            context_text = str(
                message.content.get("conversation_context", "")
            )
            if not audit_codes(question) and not last_audit_code(context_text):
                mode = "sql"

        asked = message.content.get("asked_clarifications")
        asked_clarifications = (
            [str(item) for item in asked if str(item).strip()]
            if isinstance(asked, list)
            else []
        )
        return {
            "status": "ok",
            "request": message.model_dump(),
            "question": question,
            "mode": mode,
            "chart_source": chart_source,
            "asked_clarifications": asked_clarifications,
            "conversation_context": str(
                message.content.get("conversation_context", "")
            ),
            "dialogue_slots": dict(message.content.get("dialogue_slots") or {}),
            "auditor_id": str(message.content.get("auditor_id", "")),
            "profile_text": str(message.content.get("profile_text", "")),
            "language": str(message.content.get("language", "ru")),
            "conversation_id": message.conversation_id,
            "retries": 0,
            "evidence": [],
            "tool_calls": [],
        }

    def plan_sql(state: AnalyticsState) -> dict[str, Any]:
        """Строит план запроса: Query IR/шаблон или свободный SQL."""
        templates = db_tools.list_script_templates(server)
        question = state["question"]
        latest_year = db_tools.latest_pocket_year(server)

        def template_by_key(key: str) -> dict[str, Any]:
            """Возвращает описание шаблона по ключу или пустой словарь."""
            return next(
                (
                    item
                    for item in templates
                    if item.get("template_key") == key
                ),
                {},
            )

        def script_plan(
            key: str,
            selected_parameters: dict[str, Any],
            query_plan,
            plan_source: str,
        ) -> dict[str, Any] | None:
            """Проверяет контракт шаблона и собирает plan для strategy=script."""
            template = template_by_key(key)
            parameters, error = _template_parameters(
                templates, key, selected_parameters
            )
            if parameters is None:
                logger.warning("template rejected: %s", error)
                return None
            return {
                "plan": {
                    "strategy": "script",
                    "template_key": key,
                    "template_title": str(template.get("title") or ""),
                    "template_description": str(
                        template.get("description") or ""
                    ),
                    "parameters": parameters,
                    "sql": "",
                    "reason": query_plan.reason
                    or "контракт шаблона",
                    "plan_source": plan_source,
                    "query_plan": query_plan.model_dump(),
                },
                "strategy": "script",
            }

        # 1. Query IR: LLM описывает смысл и может выбрать шаблон.
        # Контракт шаблона проверяет код; неподходящий шаблон отклоняется.
        planner = getattr(llm, "plan_query", None)
        if planner is not None:
            try:
                query_plan = planner(
                    question=question,
                    catalog_text=catalog_text(),
                    context=state.get("conversation_context", ""),
                    profile_text=state.get("profile_text", ""),
                    templates=templates,
                )
            except Exception:
                query_plan = None

            if query_plan is not None and query_plan.unsupported:
                logger.info(
                    "Query IR не покрывает вопрос: %s", query_plan.reason
                )
            if query_plan is not None and not query_plan.unsupported:
                # Вторая LLM-проверка: чего не хватает плану по сравнению
                # с вопросом. Код применяет gaps и валидирует их каталогом.
                reviewer = getattr(llm, "review_query_plan", None)
                if reviewer is not None:
                    try:
                        gaps = reviewer(
                            question=question,
                            plan=query_plan,
                            catalog_text=catalog_text(),
                            context=state.get("conversation_context", ""),
                            profile_text=state.get("profile_text", ""),
                        )
                        if gaps.clarification.strip():
                            asked = {
                                _normalize_question(item)
                                for item in state.get("asked_clarifications") or []
                                if str(item).strip()
                            }
                            if _normalize_question(gaps.clarification) not in asked:
                                # Две равноправные трактовки: не считаем наугад.
                                return {
                                    "status": "ok",
                                    "strategy": "clarify",
                                    "clarification": {
                                        "question": gaps.clarification.strip(),
                                        "missing": list(gaps.missing_dimensions),
                                        "options": [],
                                        "original_query": question,
                                        "route": "analytics",
                                        "attempts": 0,
                                    },
                                }
                        query_plan = apply_plan_gaps(query_plan, gaps)
                        query_plan = _complete_metric_dimensions(query_plan)
                    except Exception as exc:
                        logger.warning("plan review failed: %s", exc)

                key = str(query_plan.template_key or "").strip()
                if key:
                    problems = template_plan_problems(key, query_plan)
                    if problems:
                        logger.warning(
                            "template %s rejected: %s",
                            key,
                            ", ".join(problems),
                        )
                    else:
                        parameters = template_parameters(
                            key, query_plan, latest_year
                        )
                        result = script_plan(
                            key, parameters, query_plan, "query_ir"
                        )
                        if result is not None:
                            return result

                try:
                    sql = compile_query_plan(query_plan)
                except (QueryCompileError, KeyError):
                    pass
                else:
                    return {
                        "plan": {
                            "strategy": "generated",
                            "template_key": "",
                            "parameters": {},
                            "sql": sql,
                            "reason": query_plan.reason or "query_ir",
                            "plan_source": "query_ir",
                            "query_plan": query_plan.model_dump(),
                        },
                        "strategy": "generated",
                    }

        # Fallback: свободный SQL только когда Query IR не покрыл вопрос.
        # LLM здесь тоже не выбирает шаблон: только generated SQL.
        try:
            plan = llm.plan_sql(
                question=question,
                schema_text=db_tools.get_schema(),
                context=state.get("conversation_context", ""),
                profile_text=state.get("profile_text", ""),
            )
        except Exception as exc:
            detail = str(exc).strip() or repr(exc)
            return _fail(
                state,
                t(state.get("language"), "plan_failed", error=detail),
            )
        if plan.strategy != "generated" or not plan.sql.strip():
            return _fail(
                state,
                "Модель должна вернуть SQL: готовые шаблоны выбирает код",
            )
        plan_payload = plan.model_dump()
        plan_payload["template_key"] = ""
        plan_payload["parameters"] = {}
        return {"plan": plan_payload, "strategy": "generated"}

    def run_script(state: AnalyticsState) -> dict[str, Any]:
        """Выполняет выбранный шаблон и возвращает строки и evidence."""
        plan = state["plan"]
        try:
            result = db_tools.run_script_template(
                server, plan["template_key"], plan.get("parameters", {})
            )
        except Exception as exc:
            return _fail(state, f"Шаблон не выполнен: {exc}")
        return {
            "sql": result["sql"],
            "columns": result["columns"],
            "rows": result["rows"],
            "truncated": bool(result.get("truncated")),
            "max_rows": int(result.get("max_rows") or config.MAX_ROWS),
            "evidence": [
                {
                    "type": "script_template",
                    "template_key": plan["template_key"],
                    "row_count": result["row_count"],
                }
            ],
        }

    def validate_sql(state: AnalyticsState) -> dict[str, Any]:
        """Пропускает SQL через read-only guard; при ошибке — отказ."""
        try:
            safe = validate_readonly_sql(state["plan"]["sql"])
        except UnsafeSQLError as exc:
            logger.warning("SQL guard rejected: %s", exc)
            return {
                **_refuse(
                    state, t(state.get("language"), "sql_rejected")
                ),
                "retry": False,
            }

        return {"sql": safe, "retry": False}

    def execute_sql(state: AnalyticsState) -> dict[str, Any]:
        """Выполняет безопасный SQL и сохраняет результат с evidence."""
        try:
            result = db_tools.run_readonly_sql(server, state["sql"])
        except UnsafeSQLError as exc:
            logger.warning("SQL guard rejected on execute: %s", exc)
            return _refuse(state, t(state.get("language"), "sql_rejected"))
        except psycopg.Error as exc:
            retries = int(state.get("retries", 0))
            if retries < 2:
                return {
                    "retries": retries + 1,
                    "error": str(exc),
                    "retry": True,
                }
            return {**_fail(state, f"SQL не выполнен после исправлений: {exc}"), "retry": False}
        query_id = f"q-{uuid.uuid4().hex[:8]}"
        return {
            "sql": result["sql"],
            "columns": result["columns"],
            "rows": result["rows"],
            "truncated": bool(result.get("truncated")),
            "max_rows": int(result.get("max_rows") or config.MAX_ROWS),
            "retry": False,
            "evidence": [
                {
                    "type": "sql_result",
                    "query_id": query_id,
                    "row_count": result["row_count"],
                }
            ],
        }

    def verify_result(state: AnalyticsState) -> dict[str, Any]:
        """Проверяет, что SQL и результат отвечают на вопрос; один повтор плана."""
        if state.get("status") in ("refused", "failed"):
            return {}
        sql = str(state.get("sql") or "").strip()
        rows = state.get("rows") or []
        if not sql or not rows:
            return {}
        attempts = int(state.get("verify_attempts", 0))
        if attempts > 1:
            return {"verify_retry": False}
        verifier = getattr(llm, "verify_result", None)
        if verifier is None:
            return {"verify_retry": False}
        asked = {
            _normalize_question(item)
            for item in state.get("asked_clarifications") or []
            if str(item).strip()
        }
        try:
            check = verifier(
                question=state.get("question", ""),
                sql=sql,
                columns=list(state.get("columns") or []),
                rows=rows,
                language=str(state.get("language") or "ru"),
                asked_clarifications=list(
                    state.get("asked_clarifications") or []
                ),
            )
        except Exception as exc:
            logger.warning("result verify failed: %s", exc)
            return {
                "verify_retry": False,
                "metrics": {
                    **(state.get("metrics") or {}),
                    "result_check": "unavailable",
                },
            }
        metrics = dict(state.get("metrics") or {})
        issues = [
            str(item).strip()
            for item in check.missing_conditions
            if str(item).strip()
        ]
        if check.wrong_metric:
            issues.append("метрика не соответствует вопросу")
        metrics["verify_attempts"] = attempts + 1
        if check.complete or not issues:
            # Без конкретного пропущенного условия или неверной метрики
            # повтор плана только добавил бы шум.
            metrics["result_check"] = "ok"
            if check.assumption.strip():
                metrics["verify_assumption"] = check.assumption.strip()
            return {"verify_retry": False, "metrics": metrics}
        update: dict[str, Any] = {
            "verify_attempts": attempts + 1,
            "verify_retry": False,
            "verify_issues": issues,
            "metrics": metrics,
        }
        if attempts == 0 and check.corrected_question.strip():
            metrics["result_check"] = "retry"
            update["question"] = check.corrected_question.strip()
            update["verify_retry"] = True
            return update
        question = _normalize_question(check.clarification)
        if question and question not in asked:
            metrics["result_check"] = "clarify"
            metrics["clarification_asked"] = 1
            update.update(
                {
                    "clarification": {
                        "question": check.clarification.strip(),
                        "missing": issues,
                        "options": [],
                        "original_query": str(state.get("question") or ""),
                        "route": "analytics",
                        "attempts": 0,
                    },
                    "strategy": "clarify",
                    "status": "ok",
                }
            )
            return update
        if check.assumption.strip():
            metrics["result_check"] = "ok"
            metrics["verify_assumption"] = check.assumption.strip()
            return update
        # Технические подробности проверки остаются в метриках, а не в ответе.
        metrics["result_check"] = "warning"
        return update

    def repair_sql(state: AnalyticsState) -> dict[str, Any]:
        """Просит LLM исправить SQL по тексту ошибки (не более 2 раз)."""
        try:
            plan = llm.repair_sql(
                question=state["question"],
                sql=state.get("sql") or state["plan"].get("sql", ""),
                error=state.get("error", ""),
                schema_text=db_tools.get_schema(),
                context=state.get("conversation_context", ""),
                profile_text=state.get("profile_text", ""),
            )
        except Exception as exc:
            return {
                **_fail(
                    state,
                    t(state.get("language"), "repair_failed", error=exc),
                ),
                "retry": False,
            }
        return {"plan": plan.model_dump(), "strategy": "generated", "retry": False}

    def drilldown(state: AnalyticsState) -> dict[str, Any]:
        """Показывает пункты проверки по коду AUD-… из вопроса или контекста."""
        codes = audit_codes(state["question"])
        audit_code = (
            codes[0]
            if codes
            else last_audit_code(state.get("conversation_context", ""))
        )
        if not audit_code:
            return _fail(
                state,
                "Для детализации нужен код проверки, например "
                "AUD-2026-MORTGAGE-03.",
            )
        items = db_tools.get_act_items(server, audit_code, limit=50)
        english = str(state.get("language")).lower() == "en"
        if not items:
            return {
                "answer": (
                    f"No items were found for audit {audit_code}."
                    if english
                    else f"По проверке {audit_code} пункты не найдены."
                ),
                "rows": [],
                "columns": [],
                "evidence": [],
                "answer_source": "agent",
            }
        lines = [
            (
                f"Audit {audit_code}: {len(items)} items found."
                if english
                else f"По проверке {audit_code} найдено пунктов: {len(items)}."
            )
        ]
        for item in items[:5]:
            lines.append(
                f"{item['item_number']} — {item['title']} "
                f"({item['risk_level']}, {item['status']})"
            )
        draft = "\n".join(lines)
        answer, answer_source = _format_with_llm(
            llm,
            state,
            draft=draft,
            kind="items",
            facts=items[:5],
        )
        # Модель иногда пересчитывает итог по видимому списку (5 из 9).
        # Если исходное число потерялось — отдаём детерминированный черновик.
        if answer_source == "llm" and str(len(items)) not in answer:
            answer, answer_source = draft, "agent"
        return {
            "answer": answer,
            "rows": items,
            "columns": list(items[0].keys()),
            "evidence": [
                {"type": "item", "item_id": item["item_id"]} for item in items
            ],
            "strategy": "drilldown",
            "answer_source": answer_source,
        }

    def multi_tool(state: AnalyticsState) -> dict[str, Any]:
        """Планирует несколько tools одним вызовом LLM и выполняет их."""
        plan = None
        last_error: Exception | None = None
        for _ in range(2):
            try:
                plan = llm.plan_tools(
                    question=state["question"],
                    tools_text=TOOL_SPECS,
                    context=state.get("conversation_context", ""),
                    profile_text=state.get("profile_text", ""),
                )
                break
            except Exception as exc:
                last_error = exc
        if plan is None:
            return _fail(
                state,
                t(state.get("language"), "tools_failed", error=last_error),
            )

        calls: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        requested = len(plan.calls)
        limit = config.MAX_AGENT_ITERATIONS
        truncated = requested > limit
        english = str(state.get("language")).lower() == "en"
        codes = audit_codes(state["question"])
        audit_code = (
            codes[0]
            if codes
            else last_audit_code(state.get("conversation_context", ""))
        )
        hints = None
        reviewer = getattr(llm, "review_tool_arguments", None)
        if reviewer is not None:
            try:
                hints = reviewer(question=state["question"])
            except Exception:
                hints = None
        lines: list[str] = [f"Проверка {audit_code}:" if audit_code else "Результаты:"]
        for call in plan.calls[:limit]:
            name, inline_arguments = _split_tool_call(call.name)
            arguments = {**inline_arguments, **call.arguments.as_call_arguments()}
            if name in ("get_audit", "get_act", "get_act_items"):
                if not arguments.get("audit_code"):
                    arguments["audit_code"] = (
                        hints.audit_code if hints and hints.audit_code else audit_code
                    )
                arguments.pop("audit_id", None)
            if (
                name == "get_act_items"
                and hints is not None
                and not arguments.get("item_type")
                and hints.item_type
            ):
                arguments["item_type"] = hints.item_type
            if name == "search_acts" and not arguments.get("query"):
                arguments["query"] = (
                    hints.query if hints and hints.query else state["question"]
                )
            try:
                result = execute_tool(server, name, arguments)
            except Exception as exc:
                lines.append(f"{name}: ошибка — {exc}")
                continue
            calls.append({"name": name, "arguments": arguments})
            if isinstance(result, list):
                lines.append(f"{call.name}: {len(result)} результатов")
                for row in result[:10]:
                    if isinstance(row, dict):
                        if row.get("item_id"):
                            evidence.append(
                                {"type": "item", "item_id": row["item_id"]}
                            )
                        elif row.get("audit_code"):
                            evidence.append(
                                {"type": "act", "audit_code": row["audit_code"]}
                            )
            elif isinstance(result, dict):
                lines.append(f"{call.name}: 1 результат")
            else:
                lines.append(f"{call.name}: выполнено")
            evidence.append({"type": "tool", "name": call.name})

        answer, answer_source = _format_with_llm(
            llm,
            state,
            draft="\n".join(lines),
            kind="tools",
            facts=calls,
        )
        truncation_metrics: dict[str, Any] = {}
        if truncated:
            # Часть плана не выполнена — сообщаем об этом явно, а не молча.
            note = (
                f"Only the first {len(calls)} of {requested} tools were run."
                if english
                else f"Выполнены первые {len(calls)} из {requested} инструментов."
            )
            answer = f"{answer}\n\n{note}" if answer else note
            truncation_metrics = {
                "tool_calls_requested": requested,
                "tool_calls_truncated": True,
                "tool_calls_executed": len(calls),
            }
        return {
            "answer": answer,
            "rows": [],
            "columns": [],
            "tool_calls": calls,
            "evidence": evidence,
            "strategy": "multi_tool",
            "answer_source": answer_source,
            "metrics": truncation_metrics,
        }

    COLUMN_LABELS = {
        "year": "год",
        "month": "месяц",
        "period_year": "год",
        "pocket_year": "год",
        "theme_code": "тема",
        "theme": "тема",
        "pocket": "карман",
        "pocket_title": "карман",
        "status": "статус",
        "act_status": "статус акта",
        "item_status": "статус пункта",
        "risk_level": "уровень риска",
        "audit_code": "проверка",
        "audit_count": "Проверок",
        "completed_count": "Завершённых проверок",
        "completed_audits_count": "Завершённых проверок",
        "cnt": "Всего",
        "count": "Всего",
        "total": "Всего",
        "items_count": "Пунктов",
        "total_items": "Всего пунктов",
        "deviations_count": "Отклонений",
        "overdue_open_items": "Просроченных открытых пунктов",
        "overdue_open_items_count": "Просроченных открытых пунктов",
        "critical_open_count": "Критичных открытых пунктов",
        "overdue_share_pct": "Доля просроченных, %",
    }
    HEADLINE_COLUMNS = (
        "completed_audits_count",
        "completed_count",
        "audit_count",
        "overdue_open_items_count",
        "critical_open_count",
        "deviations_count",
        "items_count",
        "total_items",
        "count",
        "total",
    )

    def _format_rows(
        rows: list[dict[str, Any]],
        columns: list[str],
        language: str | None = None,
    ) -> str:
        english = str(language).lower() == "en"

        def label(column: str) -> str:
            """Человекочитаемая подпись колонки для табличного fallback."""
            return (
                column.replace("_", " ").capitalize()
                if english
                else COLUMN_LABELS.get(column, column)
            )

        if not rows:
            return (
                "No rows match the given conditions."
                if english
                else "По заданным условиям ничего не найдено."
            )
        if len(rows) == 1:
            row = rows[0]
            headline = next(
                (
                    key
                    for key in HEADLINE_COLUMNS
                    if key in row and row[key] is not None
                ),
                None,
            )
            if headline is not None:
                headline_label = label(headline)
                status_value = str(
                    row.get("status") or row.get("act_status") or ""
                ).strip().lower()
                if headline in (
                    "audit_count",
                    "completed_count",
                    "completed_audits_count",
                ) and status_value in ("завершена", "completed"):
                    headline_label = (
                        "Completed audits"
                        if english
                        else "Завершённых проверок"
                    )
                # Условия вопроса (год, тема, статус) пользователь уже знает:
                # не дублируем их и не показываем технические имена колонок.
                return f"{headline_label}: {row[headline]}."
            parts = [
                f"{label(column)}: {rows[0].get(column)}"
                for column in columns
                if rows[0].get(column) is not None
            ]
            if parts:
                return t(language, "result", body=", ".join(parts))
        return t(language, "present_table_title", count=len(rows))

    def chart(state: AnalyticsState) -> dict[str, Any]:
        """Диаграмма по текущему запросу или по предыдущему результату."""
        language = state.get("language")
        rows = list(state.get("rows") or [])
        columns = list(state.get("columns") or [])
        sql = str(state.get("sql") or "")
        source_question = str(state.get("question") or "")
        from_previous = False

        if not rows:
            # Если текущий SQL уже выполнялся и вернул 0 строк — это честный
            # «нет данных», а не повод подставлять старую диаграмму.
            if sql or columns:
                return {
                    "status": "ok", "answer": t(language, "chart_no_data"),
                    "answer_source": "agent",
                    "strategy": "chart",
                    "rows": [],
                    "columns": columns,
                    "sql": sql,
                    "evidence": [],
                }
            # Иначе это follow-up «построй диаграмму по этим данным».
            try:
                previous = dialogue_store.load_last_analytics(
                    server,
                    state.get("conversation_id", ""),
                    auditor_id=state.get("auditor_id", ""),
                )
            except Exception as exc:
                logger.warning(
                    "Не удалось загрузить данные для диаграммы: %s", exc
                )
                previous = None
            if not previous:
                return {
                    "status": "ok", "answer": t(language, "chart_no_previous"),
                    "answer_source": "agent",
                    "strategy": "chart",
                    "rows": [],
                    "columns": [],
                    "evidence": [],
                }
            rows = list(previous.get("rows") or [])
            columns = list(previous.get("columns") or [])
            sql = str(previous.get("sql") or "")
            source_question = str(previous.get("question") or "")
            from_previous = True
            if not rows and sql:
                try:
                    result = db_tools.run_readonly_sql(server, sql)
                except Exception as exc:
                    return _fail(
                        state, f"Данные для диаграммы недоступны: {exc}"
                    )
                rows = result["rows"]
                columns = result["columns"]
                sql = result["sql"]

        if not rows:
            return {
                "status": "ok", "answer": t(language, "chart_no_data"),
                "answer_source": "agent",
                "strategy": "chart",
                "rows": [],
                "columns": columns,
                "sql": sql,
                "evidence": [],
            }

        spec: dict[str, Any] | None = None
        chart_planner = getattr(llm, "plan_chart", None)
        if chart_planner is not None:
            try:
                candidate = chart_planner(
                    question=state.get("question", "") or source_question,
                    previous_question=source_question if from_previous else "",
                    columns=columns,
                    rows=rows,
                    language=str(language or "ru"),
                    context=state.get("conversation_context", ""),
                    profile_text=state.get("profile_text", ""),
                )
                candidate_payload = (
                    candidate.model_dump()
                    if hasattr(candidate, "model_dump")
                    else dict(candidate)
                )
                grounded = ground_chart_points(
                    candidate_payload, rows, columns
                )
                if grounded is not None:
                    if candidate_payload.get("type") == "line":
                        # Временную ось упорядочиваем по сырому значению
                        # категории («2025-03»), а не по человеческой
                        # подписи («Март 2025»).
                        grounded.sort(
                            key=lambda point: str(
                                point.get("_order_value")
                                if point.get("_order_value") is not None
                                else point.get("label", "")
                            )
                        )
                    candidate_payload["data"] = [
                        {
                            key: point[key]
                            for key in ("label", "value", "series")
                            if key in point
                        }
                        for point in grounded
                    ]
                    spec = candidate_payload
            except Exception as exc:
                logger.warning("LLM chart spec rejected: %s", exc)

        evidence = [
            {
                "type": "previous_result" if from_previous else "sql_result",
                "row_count": len(rows),
            }
        ]
        if spec is not None:
            evidence.append(
                {
                    "type": "chart",
                    "chart_type": spec["type"],
                    "points": len(spec["data"]),
                }
            )
        if spec is None:
            return {
                "status": "ok", "answer": t(language, "chart_failed"),
                "answer_source": "agent",
                "strategy": "chart",
                "rows": rows,
                "columns": columns,
                "sql": sql,
                "evidence": evidence,
            }

        chart_answer = t(
            language, "chart_ready" if from_previous else "chart_ready_current"
        )
        if state.get("truncated"):
            chart_answer = (
                f"{chart_answer}\n\n"
                + t(
                    language,
                    "limit_notice",
                    limit=int(state.get("max_rows") or config.MAX_ROWS),
                )
            )
        return {
            "status": "ok",
            "answer": chart_answer,
            "answer_source": "agent",
            "strategy": "chart",
            "rows": rows,
            "columns": columns,
            "chart": spec,
            "chart_source_question": source_question,
            "sql": sql,
            "evidence": evidence,
        }

    def summarize(state: AnalyticsState) -> dict[str, Any]:
        """Формулирует ответ по строкам; fallback — детерминированная таблица."""
        if state.get("status") in ("refused", "failed"):
            return {}

        if state.get("answer") or state.get("clarification"):
            return {}

        rows = state.get("rows", [])
        columns = state.get("columns", [])
        template_title = str(
            (state.get("plan") or {}).get("template_title") or ""
        ).strip()
        template_description = str(
            (state.get("plan") or {}).get("template_description") or ""
        ).strip()
        template_header = (template_description or template_title).strip().rstrip(".")

        # Формулировку ответа всегда отдаём LLM — и для одной строки, и для
        # разреза. Детерминированный шаблон остаётся fallback'ом, чтобы при
        # недоступности модели пользователь всё равно получил корректное число.
        if rows:
            summarizer = getattr(llm, "summarize", None)
            if summarizer is not None:
                try:
                    result = summarizer(
                        question=state.get("question", ""),
                        columns=columns,
                        rows=rows,
                        profile_text=state.get("profile_text", ""),
                    )
                except Exception:
                    result = ""
                claims: list[float] | None = None
                if hasattr(result, "text"):
                    text = str(getattr(result, "text", "") or "").strip()
                    raw_claims = getattr(result, "numbers_used", None) or []
                    claims = []
                    for value in raw_claims:
                        try:
                            claims.append(float(value))
                        except (TypeError, ValueError):
                            continue
                else:
                    text = str(result or "").strip()
                text = str(text or "").strip()
                if text and _summary_numbers_supported(
                    text, rows, columns, claims
                ):
                    if (
                        template_header
                        and template_header.lower() not in text.lower()
                    ):
                        text = f"{template_header}. {text}"
                    if state.get("truncated"):
                        text = (
                            f"{text}\n\n"
                            + t(
                                state.get("language"),
                                "limit_notice",
                                limit=int(
                                    state.get("max_rows") or config.MAX_ROWS
                                ),
                            )
                        )
                    return {"answer": text, "answer_source": "llm"}
                if text:
                    logger.debug(
                        "summarize rejected by number check: %s", text[:300]
                    )

        if len(rows) > 1:
            # Многострочную таблицу рисует presentation. Текст-заглушка
            # «Найдено строк: N» дублировала бы её заголовок.
            answer = f"{template_header}." if template_header else ""
        else:
            answer = _format_rows(rows, columns, state.get("language"))
            if template_header:
                answer = f"{template_header}. {answer}"
        if state.get("truncated"):
            notice = t(
                state.get("language"),
                "limit_notice",
                limit=int(state.get("max_rows") or config.MAX_ROWS),
            )
            answer = f"{answer}\n\n{notice}" if answer else notice
        return {"answer": answer, "answer_source": "template"}

    def pack_response(state: AnalyticsState) -> dict[str, Any]:
        """Упаковывает результат в ACL-ответ inform/refuse/failure."""
        status = state.get("status", "ok")
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
                    or t(state.get("language"), "request_failed")
                },
            )

        metrics: dict[str, Any] = {
            "sql_retries": int(state.get("retries", 0)),
            "tool_calls": len(state.get("tool_calls", [])),
            "plan_source": str(
                (state.get("plan") or {}).get("plan_source", "llm_sql")
            ),
        }
        # Флаги усечения плана инструментов, выставленные в multi_tool.
        metrics.update(state.get("metrics") or {})
        answer = str(state.get("answer") or "")
        content: dict[str, Any] = {
            "answer": answer,
            "answer_source": state.get("answer_source", "template"),
            "strategy": state.get("strategy", "sql"),
            "analytics_mode": state.get("mode", "sql"),
            "evidence": state.get("evidence", []),
            "metrics": metrics,
        }
        if state.get("clarification"):
            content["clarification"] = state["clarification"]
        metric = str(
            (state.get("plan") or {}).get("query_plan", {}).get("metric") or ""
        ).strip()
        if metric:
            content["metric"] = metric
        if metrics.get("tool_calls_truncated"):
            content["tool_calls_truncated"] = True
            content["tool_calls_requested"] = int(
                metrics.get("tool_calls_requested", 0)
            )
        if state.get("sql"):
            content["sql"] = state["sql"]
        if state.get("columns"):
            content["columns"] = state["columns"]
        if state.get("rows"):
            content["rows"] = state["rows"]
        if state.get("truncated"):
            content["rows_truncated"] = True
            content["max_rows"] = int(
                state.get("max_rows") or config.MAX_ROWS
            )
        if state.get("chart"):
            content["chart"] = state["chart"]
        if state.get("chart_source_question"):
            content["source_question"] = state["chart_source_question"]
        return _reply(state, "inform", content)

    builder = StateGraph(AnalyticsState)
    builder.add_node("parse_acl", parse_acl)
    builder.add_node("plan", plan_sql)
    builder.add_node("run_script", run_script)
    builder.add_node("validate", validate_sql)
    builder.add_node("execute", execute_sql)
    builder.add_node("verify", verify_result)
    builder.add_node("repair", repair_sql)
    builder.add_node("drilldown", drilldown)
    builder.add_node("multi_tool", multi_tool)
    builder.add_node("chart", chart)
    builder.add_node("summarize", summarize)
    builder.add_node("pack", pack_response)

    builder.add_edge(START, "parse_acl")
    builder.add_conditional_edges(
        "parse_acl",
        lambda s: (
            "pack"
            if s.get("status") != "ok"
            else (
                "chart"
                if s.get("mode") == "chart"
                and s.get("chart_source") == "previous"
                else (
                    "plan"
                    if s.get("mode") == "chart"
                    else s.get("mode", "sql")
                )
            )
        ),
        {
            "sql": "plan",
            "plan": "plan",
            "drilldown": "drilldown",
            "multi_tool": "multi_tool",
            "chart": "chart",
            "pack": "pack",
        },
    )
    builder.add_conditional_edges(
        "plan",
        lambda s: (
            "summarize"
            if s.get("clarification")
            else (
                "chart"
                if s.get("status") == "failed" and s.get("mode") == "chart"
                else (
                    "summarize"
                    if s.get("status") == "failed"
                    else (
                        "run_script"
                        if s.get("strategy") == "script"
                        else "validate"
                    )
                )
            )
        ),
        {
            "run_script": "run_script",
            "validate": "validate",
            "summarize": "summarize",
            "chart": "chart",
        },
    )
    builder.add_conditional_edges(
        "validate",
        lambda s: (
            "repair"
            if s.get("retry")
            else (
                "execute"
                if s.get("status") == "ok"
                else ("chart" if s.get("mode") == "chart" else "summarize")
            )
        ),
        {
            "execute": "execute",
            "repair": "repair",
            "summarize": "summarize",
            "chart": "chart",
        },
    )
    builder.add_conditional_edges(
        "execute",
        lambda s: "repair" if s.get("retry") else "verify",
        {"repair": "repair", "verify": "verify"},
    )
    builder.add_conditional_edges(
        "verify",
        lambda s: (
            "plan"
            if s.get("verify_retry")
            else (
                "summarize"
                if s.get("answer") or s.get("clarification")
                else ("chart" if s.get("mode") == "chart" else "summarize")
            )
        ),
        {"plan": "plan", "summarize": "summarize", "chart": "chart"},
    )
    builder.add_edge("repair", "validate")
    builder.add_edge("run_script", "verify")
    builder.add_edge("drilldown", "summarize")
    builder.add_edge("multi_tool", "summarize")
    builder.add_edge("chart", "summarize")
    builder.add_edge("summarize", "pack")
    builder.add_edge("pack", END)

    return builder.compile()
