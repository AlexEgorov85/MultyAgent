"""Analytics-подагент: ACL → план → SQL/шаблон → проверка → выполнение → ответ."""

from __future__ import annotations

import re
import uuid
from typing import Any, Literal

import psycopg
from langgraph.graph import END, START, StateGraph

from ..acl import ACLMessage, ACLValidationError, make_reply, validate_acl
from ..i18n import t
from ..llm import LLMClient
from ..schemas import SQLPlan, ToolPlan
from ..state import AnalyticsState
from ..tools import db as db_tools
from ..tools.registry import TOOL_SPECS, execute_tool
from ..tools.sql_guard import UnsafeSQLError, validate_readonly_sql

AUDIT_CODE_RE = re.compile(r"AUD-\d{4}-[A-Z]+-\d{2}", re.IGNORECASE)


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
            "auditor_id": str(message.content.get("auditor_id", "")),
            "language": str(message.content.get("language", "ru")),
            "conversation_id": message.conversation_id,
            "retries": 0,
            "evidence": [],
            "tool_calls": [],
        }

    def classify(state: AnalyticsState) -> dict[str, Any]:
        question = state.get("question", "").lower()
        code = AUDIT_CODE_RE.search(question)
        if code and ("похож" in question or "друг" in question):
            return {"mode": "multi_tool"}
        if code and any(
            word in question for word in ("пункт", "отклон", "критическ", "акт")
        ):
            return {"mode": "drilldown"}
        return {"mode": "sql"}

    def plan_sql(state: AnalyticsState) -> dict[str, Any]:
        try:
            plan = llm.plan_sql(
                question=state["question"],
                schema_text=db_tools.get_schema(),
                templates=db_tools.list_script_templates(server),
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
            return _refuse(state, f"SQL отклонён: {exc}")
        return {"sql": safe}

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
            )
        except Exception as exc:
            return _fail(
                state,
                t(state.get("language"), "repair_failed", error=exc),
            )
        return {"plan": plan.model_dump(), "strategy": "generated"}

    def drilldown(state: AnalyticsState) -> dict[str, Any]:
        code = AUDIT_CODE_RE.search(state["question"])
        if not code:
            return _fail(state, "Не найден код проверки")
        audit_code = code.group(0).upper()
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
        return {
            "answer": "\n".join(lines),
            "rows": items,
            "columns": list(items[0].keys()),
            "evidence": [
                {"type": "item", "item_id": item["item_id"]} for item in items
            ],
            "strategy": "drilldown",
        }

    def multi_tool(state: AnalyticsState) -> dict[str, Any]:
        try:
            plan: ToolPlan = llm.plan_tools(
                question=state["question"], tools_text=TOOL_SPECS
            )
        except Exception as exc:
            return _fail(
                state,
                t(state.get("language"), "tools_failed", error=exc),
            )

        calls: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        code_match = AUDIT_CODE_RE.search(state["question"])
        audit_code = code_match.group(0).upper() if code_match else ""
        lines: list[str] = [f"Проверка {audit_code}:" if audit_code else "Результаты:"]
        for call in plan.calls[:5]:
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

        return {
            "answer": "Инструменты выполнены:\n" + "\n".join(lines),
            "rows": [],
            "columns": [],
            "tool_calls": calls,
            "evidence": evidence,
            "strategy": "multi_tool",
        }

    COLUMN_LABELS = {
        "year": "год",
        "period_year": "год",
        "theme_code": "тема",
        "status": "статус",
        "audit_code": "проверка",
        "audit_count": "Проверок",
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
                text = f"{label(headline)}: {row[headline]}"
                details = [
                    f"{label(column)}: {row[column]}"
                    for column in columns
                    if column != headline and row.get(column) is not None
                ]
                if details:
                    text += " (" + ", ".join(details) + ")"
                return text + "."
            parts = [
                f"{label(column)}: {rows[0].get(column)}"
                for column in columns
                if rows[0].get(column) is not None
            ]
            if parts:
                return t(language, "result", body=", ".join(parts))
        preview = "; ".join(
            ", ".join(f"{column}={row.get(column)}" for column in columns)
            for row in rows[:5]
        )
        return t(language, "found_rows", count=len(rows), preview=preview)

    def summarize(state: AnalyticsState) -> dict[str, Any]:
        if state.get("status") in ("refused", "failed"):
            return {}

        if state.get("answer"):
            return {}

        rows = state.get("rows", [])
        answer = _format_rows(
            rows, state.get("columns", []), state.get("language")
        )
        return {"answer": answer}

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

        content: dict[str, Any] = {
            "answer": state.get("answer", ""),
            "strategy": state.get("strategy", "sql"),
            "evidence": state.get("evidence", []),
            "metrics": {
                "sql_retries": int(state.get("retries", 0)),
                "tool_calls": len(state.get("tool_calls", [])),
            },
        }
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
        lambda s: "execute" if s.get("status") == "ok" else "summarize",
        {"execute": "execute", "summarize": "summarize"},
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
