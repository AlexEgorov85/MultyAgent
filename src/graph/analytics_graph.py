"""Analytics-подагент: ACL → план → SQL/шаблон → проверка → выполнение → ответ."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Literal

import psycopg
from langgraph.graph import END, START, StateGraph

from .. import config
from ..acl import ACLMessage, ACLValidationError, make_reply, validate_acl
from ..capabilities import match_capability
from ..dialogue import last_audit_code
from ..i18n import t
from ..llm import LLMClient
from ..query.compiler import QueryCompileError, compile_query_plan
from ..schemas import SQLPlan, ToolPlan
from ..semantic.catalog import catalog_text
from ..state import AnalyticsState
from ..tools import db as db_tools
from ..tools.registry import TOOL_SPECS, execute_tool
from ..tools.sql_guard import UnsafeSQLError, validate_readonly_sql

AUDIT_CODE_RE = re.compile(r"AUD-\d{4}-[A-Z]+-\d{2}", re.IGNORECASE)

# «по годам» — это разбивка, а не фильтр по одному году.
_GROUP_BY_YEAR_RE = re.compile(r"group\s+by[\s\S]*?year", re.IGNORECASE)
_GROUP_BY_POCKET_RE = re.compile(
    r"group\s+by[\s\S]*?(pocket|theme_code|theme)", re.IGNORECASE
)


def _normalise(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def _stem(word: str) -> str:
    """Грубая основа слова для поиска темы в разных падежах.

    «ипотека» / «ипотеке» → «ипотек», «карты» / «картам» → «карт».
    Это не морфология, но достаточно для коротких названий тем.
    """
    value = _normalise(word)
    value = re.sub(
        r"(иями|ями|ами|ией|иях|ях|ах|ов|ев|ей|ой|ый|ий|ая|яя|ое|ее|ые|ие|"
        r"ам|ям|ом|ем|ую|юю|а|я|ы|и|е|о|ю|ь)$",
        "",
        value,
    )
    return value


def missing_question_filters(
    question: str,
    sql: str,
    themes: list[str],
    parameters: dict[str, Any] | None = None,
) -> list[str]:
    """Какие условия вопроса не попали в SQL (или попали лишние).

    Планировщик иногда теряет фильтр (например, тему «ипотека») или,
    наоборот, добавляет тему, которой в вопросе не было. Без этой проверки
    пользователь получает правдоподобное, но неверное число.
    """
    query = _normalise(question)
    haystack = _normalise(f"{sql or ''} {parameters or ''}")
    missing: list[str] = []

    for year in re.findall(r"\b(20\d{2})\b", query):
        if year not in haystack:
            missing.append(f"год {year}")

    requested_themes: list[str] = []
    for theme in themes:
        value = _normalise(theme)
        stem = _stem(value)
        if len(stem) >= 4 and stem in query:
            requested_themes.append(value)
            if value not in haystack:
                missing.append(f"тема «{theme}»")

    # Лишний фильтр темы: модель подставила «ипотеку», хотя в вопросе
    # речь шла только о разрезе по годам и карманам.
    for theme in themes:
        value = _normalise(theme)
        if value and value in haystack and value not in requested_themes:
            missing.append(f"лишний фильтр темы «{theme}»")

    if "заверш" in query and "заверш" not in haystack:
        missing.append("статус «завершена»")
    if "закрыт" in query:
        # «Закрытая проверка» в домене — это audits.status='завершена',
        # а «закрытый пункт» — act_items.status='закрыт'.
        if "пункт" in query or "item" in query:
            if "закрыт" not in haystack:
                missing.append("статус пункта «закрыт»")
        elif not any(marker in haystack for marker in ("заверш", "закрыт")):
            missing.append("статус «завершена» (закрытая проверка)")
    if "открыт" in query and "открыт" not in haystack:
        missing.append("статус «открыт»")
    if "критич" in query and "критич" not in haystack:
        missing.append("уровень риска «критический»")

    if "карман" in query and not _GROUP_BY_POCKET_RE.search(haystack):
        missing.append("разбивка по карманам")
    if re.search(r"\bпо\s+годам?\b", query) and not _GROUP_BY_YEAR_RE.search(haystack):
        missing.append("разбивка по годам")

    for code in AUDIT_CODE_RE.findall(query):
        if code.lower() not in haystack:
            missing.append(f"проверка {code.upper()}")
    return list(dict.fromkeys(missing))


def known_themes(server) -> list[str]:
    """Возвращает список тем (theme_code) из карманов аудита."""
    from .. import db_runtime

    with db_runtime.connect(server, role=db_runtime.APP_ROLE) as conn:
        rows = conn.execute(
            "SELECT DISTINCT lower(theme_code) AS theme FROM audit.audit_pockets "
            "ORDER BY theme"
        ).fetchall()
    return [str(row[0]) for row in rows]


_YEAR_COLUMNS = ("pocket_year", "period_year", "year")
_THEME_COLUMNS = (
    "theme_code",
    "theme",
    "theme_name",
    "pocket_title",
    "pocket_id",
)
_MEASURE_COLUMNS = (
    "closed_audits_count",
    "completed_audits_count",
    "completed_count",
    "audit_count",
    "deviations_count",
    "items_count",
    "total_items",
    "overdue_open_items_count",
    "critical_open_count",
    "count",
    "total",
    "cnt",
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _pick_column(
    rows: list[dict[str, Any]],
    columns: list[str],
    candidates: tuple[str, ...],
    *,
    numeric: bool = False,
) -> str | None:
    for name in candidates:
        if name not in columns:
            continue
        for row in rows:
            value = row.get(name)
            if value is None:
                continue
            if numeric and not _is_number(value):
                break
            return name
    return None


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _aggregate_summary(
    rows: list[dict[str, Any]],
    columns: list[str],
    language: str | None = None,
) -> str:
    """Детерминированные итоги по годам и темам — без арифметики LLM."""
    if not rows:
        return ""
    english = str(language).lower() == "en"
    measure = _pick_column(rows, columns, _MEASURE_COLUMNS, numeric=True)
    if measure is None:
        measure = _pick_column(
            rows,
            columns,
            tuple(column for column in columns if column not in _YEAR_COLUMNS),
            numeric=True,
        )
    if measure is None:
        return ""

    parts: list[str] = []
    year_column = _pick_column(rows, columns, _YEAR_COLUMNS)
    theme_column = _pick_column(rows, columns, _THEME_COLUMNS)

    def totals(column: str) -> dict[Any, float]:
        result: dict[Any, float] = {}
        for row in rows:
            value = row.get(measure)
            if not _is_number(value):
                continue
            key = row.get(column)
            result[key] = result.get(key, 0.0) + float(value)
        return result

    if year_column:
        by_year = totals(year_column)
        if by_year:
            body = ", ".join(
                f"{key} — {_format_number(value)}"
                for key, value in sorted(by_year.items(), key=lambda item: str(item[0]))
            )
            parts.append(f"By year: {body}." if english else f"По годам: {body}.")

    if theme_column and theme_column != year_column:
        by_theme = totals(theme_column)
        if by_theme:
            body = ", ".join(
                f"{key} — {_format_number(value)}"
                for key, value in sorted(
                    by_theme.items(), key=lambda item: (-item[1], str(item[0]))
                )
            )
            parts.append(f"By theme: {body}." if english else f"По темам: {body}.")

    grand_total = sum(
        float(row[measure]) for row in rows if _is_number(row.get(measure))
    )
    if grand_total:
        parts.append(
            f"Total: {_format_number(grand_total)}."
            if english
            else f"Всего: {_format_number(grand_total)}."
        )
    return " ".join(parts)


def _summary_numbers_supported(
    text: str,
    rows: list[dict[str, Any]],
    columns: list[str],
) -> bool:
    """Проверяет, что LLM не придумала числа вне таблицы.

    Годы (2025, 2026) разрешены как названия разрезов. Суммы и разницы,
    которых нет в строках, считаются выдуманными: итоги добавляет
    детерминированный агрегатор.
    """
    allowed: set[float] = {float(len(rows))}
    for row in rows:
        for column in columns:
            value = row.get(column)
            if _is_number(value):
                allowed.add(round(float(value), 2))

    for token in re.findall(r"\d+(?:[.,]\d+)?", text or ""):
        try:
            value = float(token.replace(",", "."))
        except ValueError:
            continue
        if 2000 <= value <= 2099:
            continue
        if round(value, 2) not in allowed:
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

        return {
            "status": "ok",
            "request": message.model_dump(),
            "question": question,
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

    def classify(state: AnalyticsState) -> dict[str, Any]:
        question = state.get("question", "").lower()
        code = AUDIT_CODE_RE.search(question)
        if not code:
            code = last_audit_code(state.get("conversation_context", ""))
        if code and ("похож" in question or "друг" in question):
            return {"mode": "multi_tool"}
        if code and any(
            word in question for word in ("пункт", "отклон", "критическ", "акт")
        ):
            return {"mode": "drilldown"}
        return {"mode": "sql"}

    def plan_sql(state: AnalyticsState) -> dict[str, Any]:
        # 1. Typed capability: явные template-вопросы не отдаём LLM.
        capability = match_capability(
            state["question"],
            state.get("dialogue_slots") or {},
        )
        if capability is not None:
            return {
                "plan": {
                    "strategy": "script",
                    "template_key": capability.capability.id,
                    "parameters": capability.parameters,
                    "sql": "",
                    "reason": capability.reason,
                    "plan_source": "capability",
                },
                "strategy": "script",
            }

        # 2. Query IR: LLM выбирает метрику/разрезы/фильтры, SQL
        # собирает детерминированный компилятор semantic layer.
        planner = getattr(llm, "plan_query", None)
        if planner is not None:
            try:
                query_plan = planner(
                    question=state["question"],
                    catalog_text=catalog_text(),
                    context=state.get("conversation_context", ""),
                    profile_text=state.get("profile_text", ""),
                )
                sql = compile_query_plan(query_plan)
            except (QueryCompileError, KeyError):
                query_plan = None
            except Exception:
                query_plan = None
            if query_plan is not None:
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

        # Fallback: старый свободный SQL-план для запросов вне каталога.
        try:
            plan = llm.plan_sql(
                question=state["question"],
                schema_text=db_tools.get_schema(),
                templates=db_tools.list_script_templates(server),
                context=state.get("conversation_context", ""),
                profile_text=state.get("profile_text", ""),
            )
        except Exception as exc:
            detail = str(exc).strip() or repr(exc)
            return _fail(
                state,
                t(state.get("language"), "plan_failed", error=detail),
            )
        if plan.strategy == "script" and not plan.template_key.strip():
            return _fail(state, "Модель выбрала шаблон, но не указала template_key")
        if plan.strategy == "generated" and not plan.sql.strip():
            return _fail(state, "Модель не вернула SQL")
        return {"plan": plan.model_dump(), "strategy": plan.strategy}

    def run_script(state: AnalyticsState) -> dict[str, Any]:
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
            "evidence": [
                {
                    "type": "script_template",
                    "template_key": plan["template_key"],
                    "row_count": result["row_count"],
                }
            ],
        }

    def validate_sql(state: AnalyticsState) -> dict[str, Any]:
        try:
            safe = validate_readonly_sql(state["plan"]["sql"])
        except UnsafeSQLError as exc:
            return {**_refuse(state, f"SQL отклонён: {exc}"), "retry": False}

        missing = missing_question_filters(
            state.get("question", ""),
            safe,
            known_themes(server),
            state["plan"].get("parameters"),
        )
        if missing:
            retries = int(state.get("retries", 0))
            message = "SQL не учитывает условия вопроса: " + ", ".join(missing)
            if retries < 2:
                return {
                    "sql": safe,
                    "retry": True,
                    "retries": retries + 1,
                    "error": message + ". Добавь соответствующие фильтры.",
                }
            # Флаг retry обязательно сбрасываем: иначе цикл
            # validate → repair → validate не завершится.
            return {**_fail(state, message + "."), "retry": False}
        return {"sql": safe, "retry": False}

    def execute_sql(state: AnalyticsState) -> dict[str, Any]:
        try:
            result = db_tools.run_readonly_sql(server, state["sql"])
        except UnsafeSQLError as exc:
            return _refuse(state, f"SQL отклонён: {exc}")
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
            "retry": False,
            "evidence": [
                {
                    "type": "sql_result",
                    "query_id": query_id,
                    "row_count": result["row_count"],
                }
            ],
        }

    def repair_sql(state: AnalyticsState) -> dict[str, Any]:
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
        code = AUDIT_CODE_RE.search(state["question"])
        audit_code = (
            code.group(0).upper()
            if code
            else last_audit_code(state.get("conversation_context", ""))
        )
        if not audit_code:
            return _fail(state, "Не найден код проверки")
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
        try:
            plan: ToolPlan = llm.plan_tools(
                question=state["question"],
                tools_text=TOOL_SPECS,
                context=state.get("conversation_context", ""),
                profile_text=state.get("profile_text", ""),
            )
        except Exception as exc:
            return _fail(
                state,
                t(state.get("language"), "tools_failed", error=exc),
            )

        calls: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        requested = len(plan.calls)
        limit = config.MAX_AGENT_ITERATIONS
        truncated = requested > limit
        english = str(state.get("language")).lower() == "en"
        code_match = AUDIT_CODE_RE.search(state["question"])
        audit_code = (
            code_match.group(0).upper()
            if code_match
            else last_audit_code(state.get("conversation_context", ""))
        )
        lines: list[str] = [f"Проверка {audit_code}:" if audit_code else "Результаты:"]
        for call in plan.calls[:limit]:
            name = call.name.split("(", 1)[0].strip()
            arguments = dict(call.arguments)
            if name in ("get_audit", "get_act", "get_act_items"):
                if not arguments.get("audit_code"):
                    arguments["audit_code"] = audit_code
                arguments.pop("audit_id", None)
            if name == "search_acts" and not arguments.get("query"):
                arguments["query"] = state["question"]
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
        "period_year": "год",
        "pocket_year": "год",
        "theme_code": "тема",
        "theme": "тема",
        "status": "статус",
        "act_status": "статус акта",
        "item_status": "статус пункта",
        "risk_level": "уровень риска",
        "audit_code": "проверка",
        "audit_count": "Проверок",
        "completed_count": "Завершённых проверок",
        "completed_audits_count": "Завершённых проверок",
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
                ):
                    if status_value.startswith("заверш"):
                        headline_label = (
                            "Completed audits"
                            if english
                            else "Завершённых проверок"
                        )
                    elif status_value.startswith("complet"):
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
        preview = "; ".join(
            ", ".join(f"{column}={row.get(column)}" for column in columns)
            for row in rows[:20]
        )
        return t(language, "found_rows", count=len(rows), preview=preview)

    def summarize(state: AnalyticsState) -> dict[str, Any]:
        if state.get("status") in ("refused", "failed"):
            return {}

        if state.get("answer"):
            return {}

        rows = state.get("rows", [])
        columns = state.get("columns", [])

        # Формулировку ответа всегда отдаём LLM — и для одной строки, и для
        # разреза. Детерминированный шаблон остаётся fallback'ом, чтобы при
        # недоступности модели пользователь всё равно получил корректное число.
        if rows:
            summarizer = getattr(llm, "summarize", None)
            if summarizer is not None:
                try:
                    text = summarizer(
                        question=state.get("question", ""),
                        columns=columns,
                        rows=rows,
                        profile_text=state.get("profile_text", ""),
                    )
                except Exception:
                    text = ""
                text = str(text or "").strip()
                if text and _summary_numbers_supported(text, rows, columns):
                    if len(rows) > 1:
                        aggregate = _aggregate_summary(
                            rows, columns, state.get("language")
                        )
                        return {
                            "answer": "\n\n".join(
                                part for part in (text, aggregate) if part
                            ),
                            "answer_source": "llm",
                        }
                    return {"answer": text, "answer_source": "llm"}

        answer = _format_rows(rows, columns, state.get("language"))
        if len(rows) > 1:
            aggregate = _aggregate_summary(rows, columns, state.get("language"))
            if aggregate:
                answer = aggregate
        return {"answer": answer, "answer_source": "template"}

    def pack_response(state: AnalyticsState) -> dict[str, Any]:
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
        content: dict[str, Any] = {
            "answer": state.get("answer", ""),
            "answer_source": state.get("answer_source", "template"),
            "strategy": state.get("strategy", "sql"),
            "evidence": state.get("evidence", []),
            "metrics": metrics,
        }
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
        return _reply(state, "inform", content)

    builder = StateGraph(AnalyticsState)
    builder.add_node("parse_acl", parse_acl)
    builder.add_node("classify", classify)
    builder.add_node("plan", plan_sql)
    builder.add_node("run_script", run_script)
    builder.add_node("validate", validate_sql)
    builder.add_node("execute", execute_sql)
    builder.add_node("repair", repair_sql)
    builder.add_node("drilldown", drilldown)
    builder.add_node("multi_tool", multi_tool)
    builder.add_node("summarize", summarize)
    builder.add_node("pack", pack_response)

    builder.add_edge(START, "parse_acl")
    builder.add_conditional_edges(
        "parse_acl",
        lambda s: "classify" if s.get("status") == "ok" else "pack",
        {"classify": "classify", "pack": "pack"},
    )
    builder.add_conditional_edges(
        "classify",
        lambda s: s.get("mode", "sql"),
        {"sql": "plan", "drilldown": "drilldown", "multi_tool": "multi_tool"},
    )
    builder.add_conditional_edges(
        "plan",
        lambda s: (
            "summarize"
            if s.get("status") == "failed"
            else ("run_script" if s.get("strategy") == "script" else "validate")
        ),
        {"run_script": "run_script", "validate": "validate", "summarize": "summarize"},
    )
    builder.add_conditional_edges(
        "validate",
        lambda s: (
            "repair"
            if s.get("retry")
            else ("execute" if s.get("status") == "ok" else "summarize")
        ),
        {"execute": "execute", "repair": "repair", "summarize": "summarize"},
    )
    builder.add_conditional_edges(
        "execute",
        lambda s: "repair" if s.get("retry") else "summarize",
        {"repair": "repair", "summarize": "summarize"},
    )
    builder.add_edge("repair", "validate")
    builder.add_edge("run_script", "summarize")
    builder.add_edge("drilldown", "summarize")
    builder.add_edge("multi_tool", "summarize")
    builder.add_edge("summarize", "pack")
    builder.add_edge("pack", END)

    return builder.compile()
