"""Многоуровневый бенчмарк: простые, средние, сложные и цепочечные вопросы.

Модуль не зависит от LangGraph и LLM: он читает и проверяет набор кейсов,
а также оценивает ответ и процесс работы агента. Запуск —
``scripts/benchmark.py``.

Уровни:
* ``simple`` — один факт или один инструмент;
* ``medium`` — join, группировки, готовые шаблоны;
* ``complex`` — multi-tool, отчёт, расследование, cross-table;
* ``chain`` — несколько реплик в одной нити, где проверяется перенос
  сущностей (год, тема, тип находки, код проверки) в ``resolved_query``
  и в ответ.

Процесс оценивается отдельно: tools, стратегия, шаги ``trace``, вызовы LLM,
токены, стоимость, время и лимиты из кейса.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Sequence

from .metrics import mean, percentile

TIERS: tuple[str, ...] = ("simple", "medium", "complex", "chain")
TABLES: tuple[str, ...] = (
    "auditors",
    "audit_pockets",
    "audits",
    "acts",
    "act_items",
    "scripts",
    "script_runs",
    "deviations",
    "script_templates",
    "auditor_memory",
    "knowledge_chunks",
    "dataset_metadata",
)
ROUTES: set[str] = {
    "analytics",
    "retrieval",
    "report",
    "investigation",
    "out_of_domain",
    "unsafe",
    "memory",
    "smalltalk",
}
FACTUAL_ROUTES: set[str] = {"analytics", "retrieval", "report", "investigation"}


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    """Читает JSONL-набор бенчмарка."""
    cases: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _as_str_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def validate_cases(cases: Sequence[dict[str, Any]]) -> list[str]:
    """Проверяет структуру набора без обращения к БД и LLM."""
    errors: list[str] = []
    seen: set[str] = set()

    for index, case in enumerate(cases, start=1):
        case_id = str(case.get("id") or f"#{index}")
        if not case.get("id"):
            errors.append(f"{case_id}: нет поля id")
        elif case_id in seen:
            errors.append(f"{case_id}: дубликат id")
        seen.add(case_id)

        for field in ("tier", "auditor_id", "title", "turns"):
            if not case.get(field):
                errors.append(f"{case_id}: нет поля {field}")

        tier = case.get("tier")
        if tier not in TIERS:
            errors.append(f"{case_id}: неизвестный tier {tier!r}")

        tables = case.get("tables", [])
        if not isinstance(tables, list) or any(
            not isinstance(table, str) or table not in TABLES for table in tables
        ):
            errors.append(
                f"{case_id}: tables должен быть списком из {', '.join(TABLES)}"
            )

        turns = case.get("turns")
        if not isinstance(turns, list) or not turns:
            errors.append(f"{case_id}: turns должен быть непустым списком")
            continue
        if tier == "chain" and len(turns) < 2:
            errors.append(f"{case_id}: цепочка должна содержать минимум 2 реплики")

        context_turns = 0
        for step, turn in enumerate(turns, start=1):
            if not isinstance(turn, dict):
                errors.append(f"{case_id}.{step}: реплика должна быть объектом")
                continue
            prefix = f"{case_id}.{step}"
            for field in ("query", "expected_route"):
                if not turn.get(field):
                    errors.append(f"{prefix}: нет поля {field}")
            if turn.get("expected_route") not in ROUTES:
                errors.append(
                    f"{prefix}: неизвестный маршрут {turn.get('expected_route')!r}"
                )

            for field in (
                "expected_tools",
                "expected_evidence",
                "must_include",
                "must_not_include",
                "expected_context",
            ):
                value = turn.get(field, [])
                if not isinstance(value, list) or any(
                    not isinstance(item, str) or not item.strip() for item in value
                ):
                    errors.append(f"{prefix}: {field} должен быть списком строк")

            numbers = turn.get("expected_numbers", [])
            if not isinstance(numbers, list) or any(
                isinstance(item, bool) or not isinstance(item, (int, float))
                for item in numbers
            ):
                errors.append(f"{prefix}: expected_numbers должен быть списком чисел")

            for field in (
                "min_evidence",
                "min_acl_rounds",
                "min_citations",
                "max_llm_calls",
                "max_llm_errors",
                "max_tool_calls",
                "max_total_tokens",
                "max_sql_retries",
                "max_acl_rounds",
                "max_steps",
            ):
                value = turn.get(field, 0)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    errors.append(f"{prefix}: {field} должен быть неотрицательным целым")
            if "max_cost_usd" in turn and (
                isinstance(turn["max_cost_usd"], bool)
                or not isinstance(turn["max_cost_usd"], (int, float))
                or turn["max_cost_usd"] < 0
            ):
                errors.append(f"{prefix}: max_cost_usd должен быть неотрицательным числом")
            if "max_latency_sec" in turn and (
                isinstance(turn["max_latency_sec"], bool)
                or not isinstance(turn["max_latency_sec"], (int, float))
                or turn["max_latency_sec"] < 0
            ):
                errors.append(f"{prefix}: max_latency_sec должен быть неотрицательным числом")
            for field in ("expected_steps", "forbidden_tools"):
                value = turn.get(field, [])
                if not isinstance(value, list) or any(
                    not isinstance(item, str) or not item.strip() for item in value
                ):
                    errors.append(f"{prefix}: {field} должен быть списком строк")

            if turn.get("expected_context"):
                context_turns += 1
            if turn.get("reset_thread") and tier != "chain":
                errors.append(f"{prefix}: reset_thread допустим только в цепочке")

        if tier == "chain" and context_turns == 0:
            errors.append(f"{case_id}: в цепочке нет ни одного expected_context")

    return errors


def select_cases(
    cases: Sequence[dict[str, Any]],
    *,
    tier: str | None = None,
    only: Sequence[str] = (),
    limit: int = 0,
) -> list[dict[str, Any]]:
    """Фильтрует набор по уровню, ID и ограничению количества."""
    selected = list(cases)
    if tier:
        selected = [case for case in selected if case.get("tier") == tier]
    if only:
        wanted = set(only)
        selected = [case for case in selected if case.get("id") in wanted]
    if limit > 0:
        selected = selected[:limit]
    return selected


def normalize_text(text: Any) -> str:
    """Нормализует регистр, ё и пробелы для проверок ответа."""
    return " ".join(str(text or "").lower().replace("ё", "е").split())


def _contains(haystack: str, needle: str) -> bool:
    return normalize_text(needle) in normalize_text(haystack)


def answer_has_number(answer: Any, value: int | float) -> bool:
    """Ищет самостоятельное число, не часть года, кода или номера пункта."""
    text = normalize_text(answer)
    number = f"{value:g}" if isinstance(value, float) else str(value)
    pattern = rf"(?<![\d.,]){re.escape(number)}(?![\d.,])"
    return bool(re.search(pattern, text))


def content_of(result: dict[str, Any]) -> dict[str, Any]:
    """ACL-content ответа подграфа."""
    content = (result.get("acl_response") or {}).get("content") or {}
    return content if isinstance(content, dict) else {}


def extract_evidence(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Evidence из ACL-ответа; fallback — evidence основного графа."""
    content = content_of(result)
    evidence = content.get("evidence")
    if not evidence:
        evidence = result.get("evidence", [])
    return [item for item in evidence or [] if isinstance(item, dict)]


def _guard_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "safe": value.get("safe"),
        "reason": value.get("reason"),
        "final_answer": value.get("final_answer"),
    }


def _compact_evidence(evidence: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in evidence:
        compact = {
            key: item[key]
            for key in ("type", "item_id", "audit_code", "source_id", "query_id", "name")
            if key in item
        }
        result.append(compact)
    return result


def extract_agent_state(
    result: dict[str, Any],
    process: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Компактный снимок состояния агента после хода.

    Фиксируем не весь граф, а то, что нужно для воспроизводимости и разбора:
    маршрут, resolved_query, guardrails, ACL-конверт, evidence, шаги, версии
    промптов и хэш ответа. Полный ``final_answer`` и тяжёлые строки не
    дублируются.
    """
    content = content_of(result)
    acl = result.get("acl_response") or {}
    acl = acl if isinstance(acl, dict) else {}
    trace = result.get("trace") or []
    process = process or {}
    prompts = process.get("prompts") or []
    steps = []
    for item in trace:
        if not isinstance(item, dict):
            continue
        steps.append(
            {
                "step": item.get("step"),
                "agent": item.get("agent"),
                "kind": item.get("kind"),
                "status": item.get("status"),
                "duration_s": item.get("duration_s"),
                "chips": item.get("chips"),
            }
        )

    answer = str(result.get("final_answer", "") or "")
    state = {
        "route": result.get("route"),
        "route_reason": result.get("route_reason"),
        "route_confidence": result.get("route_confidence"),
        "resolved_query": result.get("resolved_query"),
        "resolved_reason": result.get("resolved_reason"),
        "conversation_id": result.get("conversation_id"),
        "turn_id": result.get("turn_id"),
        "memory_saved": result.get("memory_saved"),
        "profile": result.get("profile") or {},
        "guardrail": _guard_summary(result.get("guardrail")),
        "answer_guardrail": _guard_summary(result.get("answer_guardrail")),
        "acl": {
            "performative": acl.get("performative"),
            "sender": acl.get("sender"),
            "receiver": acl.get("receiver"),
            "conversation_id": acl.get("conversation_id"),
            "reply_with": acl.get("reply_with"),
        },
        "content": {
            key: content.get(key)
            for key in (
                "strategy",
                "search_mode",
                "citations",
                "rounds",
                "missing",
                "metrics",
                "review",
                "sources",
            )
            if content.get(key) not in (None, "", [], {})
        },
        "evidence": _compact_evidence(extract_evidence(result)),
        "steps": steps,
        "metrics": result.get("metrics") or {},
        "prompts": prompts,
        "answer_chars": len(answer),
        "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest()[:16],
    }
    fingerprint_source = {
        "route": state["route"],
        "resolved_query": state["resolved_query"],
        "evidence": state["evidence"],
        "steps": [item.get("step") for item in steps],
        "prompts": prompts,
    }
    state["fingerprint"] = hashlib.sha256(
        json.dumps(fingerprint_source, ensure_ascii=False, sort_keys=True, default=str).encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    return state


def infer_tools(route: str, content: dict[str, Any]) -> list[str]:
    """Восстанавливает имена инструментов по strategy и evidence.

    Analytics-подграф не отдаёт список tool_calls в ACL-content, поэтому
    для простых SQL/шаблонов/дриллдауна инструмент выводится из strategy.
    Для multi-tool используются записи evidence вида ``{"type": "tool"}``.
    """
    evidence = [item for item in content.get("evidence", []) if isinstance(item, dict)]
    types = {str(item.get("type", "")) for item in evidence}
    strategy = str(content.get("strategy", "") or "")
    tools: set[str] = set()

    if route == "analytics":
        if strategy in ("generated", "sql"):
            tools.add("run_readonly_sql")
        elif strategy == "script":
            tools.add("run_script_template")
        elif strategy == "drilldown":
            tools.add("get_act_items")
    if route == "retrieval":
        tools.add("search_act_items")
    if "sql_result" in types:
        tools.add("run_readonly_sql")
    if "script_template" in types:
        tools.add("run_script_template")
    if "item" in types:
        tools.add("get_act_items")
    for item in evidence:
        if item.get("type") == "tool" and item.get("name"):
            tools.add(str(item["name"]))
    return sorted(tools)


def _sql_is_valid(content: dict[str, Any]) -> bool:
    sql = content.get("sql")
    if not sql:
        return True
    try:
        from .tools.sql_guard import validate_readonly_sql

        validate_readonly_sql(str(sql))
        return True
    except Exception:  # noqa: BLE001 - любой отказ guard означает невалидный SQL
        return False


def _base_row(case: dict[str, Any], turn: dict[str, Any], step: int) -> dict[str, Any]:
    expected_context = _as_str_list(turn.get("expected_context", []))
    expected_tools = _as_str_list(turn.get("expected_tools", []))
    expected_numbers = turn.get("expected_numbers", [])
    return {
        "case_id": str(case.get("id", "")),
        "tier": str(case.get("tier", "")),
        "title": str(case.get("title", "")),
        "tables": ";".join(_as_str_list(case.get("tables", []))),
        "step": int(step),
        "query": str(turn.get("query", "")),
        "expected_route": str(turn.get("expected_route", "")),
        "route": "",
        "resolved_query": "",
        "strategy": "",
        "expected_strategy": str(turn.get("expected_strategy", "") or ""),
        "tools_actual": "",
        "tools_count": 0,
        "expected_tools": ";".join(expected_tools),
        "forbidden_tools": ";".join(_as_str_list(turn.get("forbidden_tools", []))),
        "tool_names": "",
        "context_tokens": ";".join(expected_context),
        "context_applicable": bool(expected_context),
        "numbers_applicable": bool(expected_numbers),
        "tools_applicable": bool(expected_tools),
        "strategy_applicable": bool(turn.get("expected_strategy")),
        "evidence_applicable": False,
        "rounds_applicable": int(turn.get("min_acl_rounds", 0) or 0) > 0,
        "route_ok": False,
        "context_ok": not expected_context,
        "context_resolved_ok": not expected_context,
        "context_answer_ok": not expected_context,
        "numbers_ok": not expected_numbers,
        "tools_ok": not expected_tools,
        "strategy_ok": not turn.get("expected_strategy"),
        "include_ok": True,
        "exclude_ok": True,
        "evidence_ok": True,
        "rounds_ok": True,
        "sql_ok": True,
        "answer_ok": False,
        "success": False,
        "evidence_count": 0,
        "citations_count": 0,
        "citations_applicable": int(turn.get("min_citations", 0) or 0) > 0,
        "citations_ok": int(turn.get("min_citations", 0) or 0) <= 0,
        "llm_calls": 0,
        "llm_attempts": 0,
        "llm_retries": 0,
        "llm_errors": 0,
        "tool_calls": 0,
        "embedding_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "llm_latency_sec": 0.0,
        "llm_failed_latency_sec": 0.0,
        "tool_latency_sec": 0.0,
        "overhead_sec": 0.0,
        "llm_time_share_pct": 0.0,
        "tool_time_share_pct": 0.0,
        "trace_steps": "",
        "trace_step_count": 0,
        "acl_performative": "",
        "acl_sender": "",
        "acl_receiver": "",
        "state_fingerprint": "",
        "sql_retries": 0,
        "inspector_iterations": 0,
        "retrieval_chunks": 0,
        "prompts": "",
        "steps_ok": True,
        "llm_calls_ok": True,
        "llm_errors_ok": True,
        "tool_calls_ok": True,
        "tokens_ok": True,
        "cost_ok": True,
        "latency_ok": True,
        "forbidden_tools_ok": True,
        "sql_retries_ok": True,
        "acl_rounds_ok": True,
        "max_steps_ok": True,
        "process_success": False,
        "answer_success": False,
        "state": {},
        "process": {},
        "acl_rounds": 0,
        "latency_sec": 0.0,
        "answer": "",
        "error": "",
    }


def evaluate_turn(
    case: dict[str, Any],
    turn: dict[str, Any],
    result: dict[str, Any],
    latency_sec: float,
    step: int,
    process: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Оценивает ответ и процесс: маршрут, контекст, tools, токены, шаги."""
    row = _base_row(case, turn, step)
    content = content_of(result)
    route = str(result.get("route", "") or "")
    answer = str(result.get("final_answer", "") or "")
    resolved = str(result.get("resolved_query", "") or "")
    evidence = extract_evidence(result)
    evidence_types = {str(item.get("type", "")) for item in evidence}
    citations = content.get("citations") or []
    if not isinstance(citations, list):
        citations = []
    process = process or {}
    tokens = process.get("tokens") if isinstance(process.get("tokens"), dict) else {}
    tool_events = process.get("tool_events") or []
    process_tool_names = [
        str(item.get("name"))
        for item in tool_events
        if isinstance(item, dict) and item.get("name")
    ]
    inferred_tools = infer_tools(route, content)
    tools = list(dict.fromkeys(process_tool_names or inferred_tools))
    trace = result.get("trace") or []
    step_names = [
        str(item.get("step"))
        for item in trace
        if isinstance(item, dict) and item.get("step")
    ]
    prompts = process.get("prompts") or []
    prompt_text = ";".join(
        f"{item.get('id')}@v{item.get('version')}:{item.get('hash')}"
        for item in prompts
        if isinstance(item, dict)
    )
    strategy = str(content.get("strategy", "") or "")

    expected_context = _as_str_list(turn.get("expected_context", []))
    expected_tools = _as_str_list(turn.get("expected_tools", []))
    expected_numbers = turn.get("expected_numbers", [])
    must_include = _as_str_list(turn.get("must_include", []))
    must_not_include = _as_str_list(turn.get("must_not_include", []))
    expected_evidence = _as_str_list(turn.get("expected_evidence", []))
    expected_strategy = str(turn.get("expected_strategy", "") or "")

    default_min_evidence = 1 if route in FACTUAL_ROUTES else 0
    min_evidence = int(turn.get("min_evidence", default_min_evidence) or 0)
    min_rounds = int(turn.get("min_acl_rounds", 0) or 0)
    min_citations = int(turn.get("min_citations", 0) or 0)
    metrics = content.get("metrics") if isinstance(content.get("metrics"), dict) else {}
    acl_rounds = int(metrics.get("acl_rounds") or content.get("rounds") or 0)
    sql_retries = int(metrics.get("sql_retries") or 0)
    inspector_iterations = int(metrics.get("inspector_iterations") or 0)
    retrieval_chunks = int(metrics.get("chunks") or 0)
    evidence_applicable = bool(
        route in FACTUAL_ROUTES or expected_evidence or min_evidence
    )

    llm_calls = int(process.get("llm_calls", 0) or 0)
    llm_attempts = int(process.get("llm_attempts", 0) or 0)
    llm_retries = int(process.get("llm_retries", 0) or 0)
    llm_errors = int(process.get("llm_errors", 0) or 0)
    tool_calls = int(process.get("tool_calls", 0) or 0)
    embedding_calls = int(process.get("embedding_calls", 0) or 0)
    input_tokens = int(tokens.get("input_tokens", 0) or 0)
    output_tokens = int(tokens.get("output_tokens", 0) or 0)
    total_tokens = input_tokens + output_tokens
    cost_usd = float(process.get("cost_usd", 0.0) or 0.0)
    llm_latency = float(process.get("llm_latency_sec", 0.0) or 0.0)
    llm_failed_latency = float(process.get("llm_failed_latency_sec", 0.0) or 0.0)
    tool_latency = float(process.get("tool_latency_sec", 0.0) or 0.0)
    overhead = max(0.0, float(latency_sec) - llm_latency - tool_latency)
    latency_safe = max(float(latency_sec), 1e-9)
    llm_share = 100.0 * llm_latency / latency_safe
    tool_share = 100.0 * tool_latency / latency_safe

    route_ok = route == str(turn.get("expected_route", ""))
    context_resolved_ok = all(
        _contains(resolved, token) for token in expected_context
    )
    context_answer_ok = all(_contains(answer, token) for token in expected_context)
    context_ok = context_resolved_ok or context_answer_ok
    numbers_ok = all(answer_has_number(answer, value) for value in expected_numbers)
    tools_ok = set(expected_tools).issubset(set(tools))
    strategy_ok = not expected_strategy or strategy == expected_strategy
    include_ok = all(_contains(answer, token) for token in must_include)
    exclude_ok = all(not _contains(answer, token) for token in must_not_include)
    evidence_ok = (
        not evidence_applicable
        or (
            len(evidence) >= min_evidence
            and all(item in evidence_types for item in expected_evidence)
        )
    )
    rounds_ok = acl_rounds >= min_rounds
    citations_ok = len(citations) >= min_citations
    sql_ok = _sql_is_valid(content)
    answer_ok = bool(answer.strip())

    max_llm_calls = int(turn.get("max_llm_calls", 0) or 0)
    max_llm_errors = int(turn.get("max_llm_errors", 0) or 0)
    max_tool_calls = int(turn.get("max_tool_calls", 0) or 0)
    max_total_tokens = int(turn.get("max_total_tokens", 0) or 0)
    max_sql_retries = int(turn.get("max_sql_retries", 0) or 0)
    max_acl_rounds = int(turn.get("max_acl_rounds", 0) or 0)
    max_steps = int(turn.get("max_steps", 0) or 0)
    max_cost = turn.get("max_cost_usd")
    max_latency = turn.get("max_latency_sec")
    expected_steps = _as_str_list(turn.get("expected_steps", []))
    forbidden_tools = set(_as_str_list(turn.get("forbidden_tools", [])))

    llm_calls_ok = not max_llm_calls or llm_calls <= max_llm_calls
    llm_errors_ok = llm_errors <= max_llm_errors
    tool_calls_ok = not max_tool_calls or tool_calls <= max_tool_calls
    tokens_ok = not max_total_tokens or total_tokens <= max_total_tokens
    cost_ok = max_cost is None or cost_usd <= float(max_cost)
    latency_ok = max_latency is None or float(latency_sec) <= float(max_latency)
    forbidden_tools_ok = not (set(tools) & forbidden_tools)
    sql_retries_ok = not max_sql_retries or sql_retries <= max_sql_retries
    acl_rounds_ok = not max_acl_rounds or acl_rounds <= max_acl_rounds
    steps_ok = all(step_name in step_names for step_name in expected_steps)
    max_steps_ok = not max_steps or len(step_names) <= max_steps

    answer_success = all(
        (
            route_ok,
            context_ok,
            numbers_ok,
            include_ok,
            exclude_ok,
            evidence_ok,
            rounds_ok,
            citations_ok,
            sql_ok,
            answer_ok,
        )
    )
    process_success = all(
        (
            tools_ok,
            strategy_ok,
            steps_ok,
            llm_calls_ok,
            llm_errors_ok,
            tool_calls_ok,
            tokens_ok,
            cost_ok,
            latency_ok,
            forbidden_tools_ok,
            sql_retries_ok,
            acl_rounds_ok,
            max_steps_ok,
        )
    )
    success = answer_success and process_success
    state = extract_agent_state(result, process)
    acl_state = state.get("acl") or {}

    row.update(
        {
            "route": route,
            "resolved_query": resolved,
            "strategy": strategy,
            "tools_actual": ";".join(tools),
            "tools_count": len(tools),
            "tool_names": ";".join(process_tool_names),
            "context_applicable": bool(expected_context),
            "numbers_applicable": bool(expected_numbers),
            "tools_applicable": bool(expected_tools),
            "strategy_applicable": bool(expected_strategy),
            "evidence_applicable": evidence_applicable,
            "rounds_applicable": min_rounds > 0,
            "citations_applicable": min_citations > 0,
            "route_ok": route_ok,
            "context_ok": context_ok,
            "context_resolved_ok": context_resolved_ok,
            "context_answer_ok": context_answer_ok,
            "numbers_ok": numbers_ok,
            "tools_ok": tools_ok,
            "strategy_ok": strategy_ok,
            "include_ok": include_ok,
            "exclude_ok": exclude_ok,
            "evidence_ok": evidence_ok,
            "rounds_ok": rounds_ok,
            "citations_ok": citations_ok,
            "sql_ok": sql_ok,
            "answer_ok": answer_ok,
            "success": success,
            "evidence_count": len(evidence),
            "citations_count": len(citations),
            "llm_calls": llm_calls,
            "llm_attempts": llm_attempts,
            "llm_retries": llm_retries,
            "llm_errors": llm_errors,
            "tool_calls": tool_calls,
            "embedding_calls": embedding_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost_usd": round(cost_usd, 6),
            "llm_latency_sec": round(llm_latency, 3),
            "llm_failed_latency_sec": round(llm_failed_latency, 3),
            "tool_latency_sec": round(tool_latency, 3),
            "overhead_sec": round(overhead, 3),
            "llm_time_share_pct": round(llm_share, 1),
            "tool_time_share_pct": round(tool_share, 1),
            "trace_steps": ";".join(step_names),
            "trace_step_count": len(step_names),
            "acl_performative": str(acl_state.get("performative") or ""),
            "acl_sender": str(acl_state.get("sender") or ""),
            "acl_receiver": str(acl_state.get("receiver") or ""),
            "state_fingerprint": str(state.get("fingerprint") or ""),
            "sql_retries": sql_retries,
            "inspector_iterations": inspector_iterations,
            "retrieval_chunks": retrieval_chunks,
            "prompts": prompt_text,
            "steps_ok": steps_ok,
            "llm_calls_ok": llm_calls_ok,
            "llm_errors_ok": llm_errors_ok,
            "tool_calls_ok": tool_calls_ok,
            "tokens_ok": tokens_ok,
            "cost_ok": cost_ok,
            "latency_ok": latency_ok,
            "forbidden_tools_ok": forbidden_tools_ok,
            "sql_retries_ok": sql_retries_ok,
            "acl_rounds_ok": acl_rounds_ok,
            "max_steps_ok": max_steps_ok,
            "process_success": process_success,
            "answer_success": answer_success,
            "state": state,
            "process": process,
            "acl_rounds": acl_rounds,
            "latency_sec": round(float(latency_sec), 3),
            "answer": answer.replace("\n", " ")[:500],
        }
    )
    return row


def failed_turn_row(
    case: dict[str, Any],
    turn: dict[str, Any],
    step: int,
    error: Exception | str,
    latency_sec: float = 0.0,
) -> dict[str, Any]:
    """Строка для упавшего запроса: ошибка не обрывает весь прогон."""
    row = _base_row(case, turn, step)
    row["error"] = str(error)
    row["latency_sec"] = round(float(latency_sec), 3)
    row["answer_ok"] = False
    row["success"] = False
    return row


def _rate(
    rows: Sequence[dict[str, Any]],
    key: str,
    applicable_key: str | None = None,
) -> float:
    selected = [
        row for row in rows if applicable_key is None or row.get(applicable_key)
    ]
    if not selected:
        return 0.0
    return sum(bool(row.get(key)) for row in selected) / len(selected)


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, float | int]:
    """Считает метрики по ходам и по уровням simple/complex/chain."""
    case_ids = {row["case_id"] for row in rows}
    case_success: dict[str, bool] = {}
    for row in rows:
        case_success[row["case_id"]] = case_success.get(row["case_id"], True) and bool(
            row.get("success")
        )

    latencies = [float(row["latency_sec"]) for row in rows]
    successful = [row for row in rows if row.get("success")]
    successful_count = len(successful)
    total_tokens = sum(int(row.get("total_tokens", 0)) for row in rows)
    total_cost = sum(float(row.get("cost_usd", 0.0)) for row in rows)
    total_llm_calls = sum(int(row.get("llm_calls", 0)) for row in rows)
    total_llm_attempts = sum(int(row.get("llm_attempts", 0)) for row in rows)
    total_llm_retries = sum(int(row.get("llm_retries", 0)) for row in rows)
    total_llm_errors = sum(int(row.get("llm_errors", 0)) for row in rows)
    total_tool_calls = sum(int(row.get("tool_calls", 0)) for row in rows)
    total_embedding_calls = sum(int(row.get("embedding_calls", 0)) for row in rows)
    total_llm_latency = sum(float(row.get("llm_latency_sec", 0.0)) for row in rows)
    total_llm_failed_latency = sum(
        float(row.get("llm_failed_latency_sec", 0.0)) for row in rows
    )
    total_tool_latency = sum(float(row.get("tool_latency_sec", 0.0)) for row in rows)
    total_latency = sum(latencies)
    summary: dict[str, float | int] = {
        "cases": len(case_ids),
        "turns": len(rows),
        "route_accuracy": _rate(rows, "route_ok"),
        "answer_success_rate": _rate(rows, "answer_success"),
        "process_success_rate": _rate(rows, "process_success"),
        "success_rate": _rate(rows, "success"),
        "error_rate": 1.0 - _rate(rows, "success"),
        "case_success_rate": (
            sum(case_success.values()) / len(case_success) if case_success else 0.0
        ),
        "context_retention_rate": _rate(rows, "context_ok", "context_applicable"),
        "context_rewrite_rate": _rate(
            rows, "context_resolved_ok", "context_applicable"
        ),
        "context_answer_rate": _rate(rows, "context_answer_ok", "context_applicable"),
        "context_turns": sum(bool(row.get("context_applicable")) for row in rows),
        "numeric_accuracy": _rate(rows, "numbers_ok", "numbers_applicable"),
        "numeric_turns": sum(bool(row.get("numbers_applicable")) for row in rows),
        "tool_accuracy": _rate(rows, "tools_ok", "tools_applicable"),
        "tool_turns": sum(bool(row.get("tools_applicable")) for row in rows),
        "strategy_accuracy": _rate(rows, "strategy_ok", "strategy_applicable"),
        "evidence_coverage": _rate(rows, "evidence_ok", "evidence_applicable"),
        "citation_coverage": _rate(rows, "citations_ok", "citations_applicable"),
        "citation_turns": sum(bool(row.get("citations_applicable")) for row in rows),
        "latency_total_sec": total_latency,
        "latency_mean_sec": mean(latencies),
        "latency_p50_sec": percentile(latencies, 0.5),
        "latency_p95_sec": percentile(latencies, 0.95),
        "avg_tools_per_turn": mean([int(row.get("tools_count", 0)) for row in rows]),
        "llm_calls_total": total_llm_calls,
        "llm_attempts_total": total_llm_attempts,
        "llm_retries_total": total_llm_retries,
        "llm_errors_total": total_llm_errors,
        "tool_calls_total": total_tool_calls,
        "embedding_calls_total": total_embedding_calls,
        "input_tokens_total": sum(int(row.get("input_tokens", 0)) for row in rows),
        "output_tokens_total": sum(int(row.get("output_tokens", 0)) for row in rows),
        "total_tokens_total": total_tokens,
        "cost_usd_total": round(total_cost, 6),
        "llm_latency_total_sec": round(total_llm_latency, 3),
        "llm_failed_latency_total_sec": round(total_llm_failed_latency, 3),
        "tool_latency_total_sec": round(total_tool_latency, 3),
        "avg_llm_calls_per_turn": mean([int(row.get("llm_calls", 0)) for row in rows]),
        "avg_tool_calls_per_turn": mean([int(row.get("tool_calls", 0)) for row in rows]),
        "avg_total_tokens_per_turn": mean(
            [int(row.get("total_tokens", 0)) for row in rows]
        ),
        "avg_cost_usd_per_turn": mean(
            [float(row.get("cost_usd", 0.0)) for row in rows]
        ),
        "avg_steps_per_turn": mean(
            [int(row.get("trace_step_count", 0)) for row in rows]
        ),
        "avg_llm_latency_sec": mean(
            [float(row.get("llm_latency_sec", 0.0)) for row in rows]
        ),
        "avg_llm_failed_latency_sec": mean(
            [float(row.get("llm_failed_latency_sec", 0.0)) for row in rows]
        ),
        "avg_tool_latency_sec": mean(
            [float(row.get("tool_latency_sec", 0.0)) for row in rows]
        ),
        "avg_overhead_sec": mean(
            [float(row.get("overhead_sec", 0.0)) for row in rows]
        ),
        "llm_time_share_pct": (
            100.0 * total_llm_latency / total_latency if total_latency else 0.0
        ),
        "tool_time_share_pct": (
            100.0 * total_tool_latency / total_latency if total_latency else 0.0
        ),
        "tokens_per_success": (
            total_tokens / successful_count if successful_count else 0.0
        ),
        "cost_per_success_usd": (
            total_cost / successful_count if successful_count else 0.0
        ),
        "llm_calls_per_success": (
            total_llm_calls / successful_count if successful_count else 0.0
        ),
        "tool_calls_per_success": (
            total_tool_calls / successful_count if successful_count else 0.0
        ),
        "sql_retries_total": sum(int(row.get("sql_retries", 0)) for row in rows),
        "acl_rounds_total": sum(int(row.get("acl_rounds", 0)) for row in rows),
        "inspector_iterations_total": sum(
            int(row.get("inspector_iterations", 0)) for row in rows
        ),
    }

    for tier in TIERS:
        tier_rows = [row for row in rows if row.get("tier") == tier]
        tier_cases = {row["case_id"] for row in tier_rows}
        summary[f"{tier}_cases"] = len(tier_cases)
        summary[f"{tier}_turns"] = len(tier_rows)
        summary[f"{tier}_answer_success_rate"] = _rate(tier_rows, "answer_success")
        summary[f"{tier}_process_success_rate"] = _rate(tier_rows, "process_success")
        summary[f"{tier}_success_rate"] = _rate(tier_rows, "success")
        if tier == "chain" and tier_rows:
            summary["chain_context_retention_rate"] = _rate(
                tier_rows, "context_ok", "context_applicable"
            )
    return summary


def summarize_cases(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Сводка по кейсам для отчёта."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["case_id"]), []).append(row)

    result: list[dict[str, Any]] = []
    for case_id, case_rows in groups.items():
        ordered = sorted(case_rows, key=lambda item: int(item["step"]))
        result.append(
            {
                "case_id": case_id,
                "tier": ordered[0].get("tier", ""),
                "title": ordered[0].get("title", ""),
                "turns": len(ordered),
                "success": all(bool(row.get("success")) for row in ordered),
                "answer_success": all(
                    bool(row.get("answer_success")) for row in ordered
                ),
                "process_success": all(
                    bool(row.get("process_success")) for row in ordered
                ),
                "llm_calls": sum(int(row.get("llm_calls", 0)) for row in ordered),
                "llm_attempts": sum(
                    int(row.get("llm_attempts", 0)) for row in ordered
                ),
                "llm_retries": sum(
                    int(row.get("llm_retries", 0)) for row in ordered
                ),
                "llm_errors": sum(int(row.get("llm_errors", 0)) for row in ordered),
                "tool_calls": sum(int(row.get("tool_calls", 0)) for row in ordered),
                "embedding_calls": sum(
                    int(row.get("embedding_calls", 0)) for row in ordered
                ),
                "total_tokens": sum(
                    int(row.get("total_tokens", 0)) for row in ordered
                ),
                "cost_usd": round(
                    sum(float(row.get("cost_usd", 0.0)) for row in ordered), 6
                ),
                "latency_sec": round(
                    sum(float(row.get("latency_sec", 0.0)) for row in ordered), 3
                ),
                "route_accuracy": _rate(ordered, "route_ok"),
                "context_retention": _rate(
                    ordered, "context_ok", "context_applicable"
                ),
                "context_rewrite": _rate(
                    ordered, "context_resolved_ok", "context_applicable"
                ),
                "numeric_accuracy": _rate(
                    ordered, "numbers_ok", "numbers_applicable"
                ),
                "tables": ordered[0].get("tables", ""),
            }
        )
    return result


def summarize_table_coverage(
    cases: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Показывает, какие таблицы/слои покрыты кейсами."""
    result: list[dict[str, Any]] = []
    for table in TABLES:
        table_cases = [
            case for case in cases if table in _as_str_list(case.get("tables", []))
        ]
        result.append(
            {
                "table": table,
                "cases": len(table_cases),
                "turns": sum(len(case.get("turns", [])) for case in table_cases),
            }
        )
    return result


def summarize_prompts(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Собирает, какие версии промптов реально использовались."""
    counts: dict[str, int] = {}
    for row in rows:
        for item in str(row.get("prompts", "") or "").split(";"):
            item = item.strip()
            if item:
                counts[item] = counts.get(item, 0) + 1
    result: list[dict[str, Any]] = []
    for item, count in sorted(counts.items()):
        name, _, version_hash = item.partition("@")
        version, _, digest = version_hash.partition(":")
        result.append(
            {
                "prompt": name,
                "version": version,
                "hash": digest,
                "turns": count,
            }
        )
    return result


def _format_metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def write_reports(
    rows: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    cases: Sequence[dict[str, Any]],
    reports_dir: str | Path,
    environment: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Пишет CSV, JSON и Markdown-отчёт."""
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    case_summary = summarize_cases(rows)

    csv_path = directory / "benchmark.csv"
    if rows:
        excluded = {"state", "process", "llm_events", "tool_events"}
        fieldnames = [key for key in rows[0].keys() if key not in excluded]
        csv_rows = [
            {key: row.get(key) for key in fieldnames}
            for row in rows
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)

    json_path = directory / "benchmark.json"
    json_path.write_text(
        json.dumps(
            {
                "environment": environment or {},
                "summary": summary,
                "cases": case_summary,
                "turns": list(rows),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    md_path = directory / "benchmark.md"
    lines = [
        "# Бенчмарк ассистента аудитора",
        "",
        "Набор: `data/benchmark_cases.jsonl`. "
        "Уровни: simple, medium, complex и chain с контекстом.",
        "",
    ]
    if environment:
        lines += ["## Среда", ""]
        for key, value in environment.items():
            if key == "prompt_versions" and isinstance(value, dict):
                rendered = ", ".join(
                    f"{name}@v{version}" for name, version in sorted(value.items())
                )
            else:
                rendered = str(value)
            lines.append(f"- `{key}`: {rendered}")
        lines.append("")

    lines += [
        "## Итог",
        "",
        "| Метрика | Значение |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        lines.append(f"| `{key}` | {_format_metric(value)} |")

    lines += [
        "",
        "## По уровням",
        "",
        "| Уровень | Кейсов | Реплик | Answer | Process | Success |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for tier in TIERS:
        lines.append(
            f"| {tier} | {summary.get(f'{tier}_cases', 0)} | "
            f"{summary.get(f'{tier}_turns', 0)} | "
            f"{_format_metric(summary.get(f'{tier}_answer_success_rate', 0.0))} | "
            f"{_format_metric(summary.get(f'{tier}_process_success_rate', 0.0))} | "
            f"{_format_metric(summary.get(f'{tier}_success_rate', 0.0))} |"
        )
    if "chain_context_retention_rate" in summary:
        lines += [
            f"| chain: context retention | — | "
            f"{summary.get('context_turns', 0)} | "
            f"{_format_metric(summary['chain_context_retention_rate'])} |",
            f"| chain: context rewrite | — | "
            f"{summary.get('context_turns', 0)} | "
            f"{_format_metric(summary.get('context_rewrite_rate', 0.0))} |",
            f"| chain: context in answer | — | "
            f"{summary.get('context_turns', 0)} | "
            f"{_format_metric(summary.get('context_answer_rate', 0.0))} |",
        ]

    process_keys = (
        "llm_calls_total",
        "llm_attempts_total",
        "llm_retries_total",
        "llm_errors_total",
        "tool_calls_total",
        "embedding_calls_total",
        "input_tokens_total",
        "output_tokens_total",
        "total_tokens_total",
        "cost_usd_total",
        "llm_latency_total_sec",
        "llm_failed_latency_total_sec",
        "tool_latency_total_sec",
        "latency_total_sec",
        "avg_llm_calls_per_turn",
        "avg_tool_calls_per_turn",
        "avg_total_tokens_per_turn",
        "avg_steps_per_turn",
        "avg_llm_latency_sec",
        "avg_llm_failed_latency_sec",
        "avg_tool_latency_sec",
        "avg_overhead_sec",
        "llm_time_share_pct",
        "tool_time_share_pct",
        "tokens_per_success",
        "cost_per_success_usd",
        "llm_calls_per_success",
        "tool_calls_per_success",
        "sql_retries_total",
        "acl_rounds_total",
        "inspector_iterations_total",
    )
    lines += ["", "## Процесс и эффективность", "", "| Метрика | Значение |", "|---|---:|"]
    for key in process_keys:
        if key in summary:
            lines.append(f"| `{key}` | {_format_metric(summary[key])} |")

    prompt_rows = summarize_prompts(rows)
    if prompt_rows:
        lines += [
            "",
            "## Версии промптов",
            "",
            "| Промпт | Версия | Хэш | Реплик |",
            "|---|---:|---|---:|",
        ]
        for item in prompt_rows:
            lines.append(
                f"| {item['prompt']} | {item['version']} | "
                f"{item['hash']} | {item['turns']} |"
            )

    lines += [
        "",
        "## Процесс по кейсам",
        "",
        "| Кейс | Уровень | LLM | Tools | Токены | Время, с | Process |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in case_summary:
        lines.append(
            f"| {item['case_id']} | {item['tier']} | {item['llm_calls']} | "
            f"{item['tool_calls']} | {item['total_tokens']} | "
            f"{_format_metric(item['latency_sec'])} | "
            f"{'✅' if item['process_success'] else '❌'} |"
        )

    coverage = summarize_table_coverage(cases)
    lines += [
        "",
        "## Покрытие таблиц",
        "",
        "| Таблица / слой | Кейсов | Реплик |",
        "|---|---:|---:|",
    ]
    for item in coverage:
        lines.append(f"| {item['table']} | {item['cases']} | {item['turns']} |")

    lines += [
        "",
        "## Кейсы",
        "",
        "| Кейс | Уровень | Шагов | Успех | Route | Context |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for item in case_summary:
        context = (
            _format_metric(item["context_retention"])
            if item["tier"] == "chain"
            else "—"
        )
        lines.append(
            f"| {item['case_id']} | {item['tier']} | {item['turns']} | "
            f"{'✅' if item['success'] else '❌'} | "
            f"{_format_metric(item['route_accuracy'])} | {context} |"
        )

    chain_rows = [row for row in rows if row.get("tier") == "chain"]
    if chain_rows:
        lines += [
            "",
            "## Цепочки: перенос контекста",
            "",
            "| Кейс | Шаг | Вопрос | resolved_query | В запросе | В ответе | Успех |",
            "|---|---:|---|---|---:|---:|---:|",
        ]
        for row in chain_rows:
            query = " ".join(str(row["query"]).split()).replace("|", "\\|")
            resolved = " ".join(str(row["resolved_query"]).split()).replace("|", "\\|")
            if not row.get("context_applicable"):
                in_query = in_answer = "—"
            else:
                in_query = "✅" if row.get("context_resolved_ok") else "❌"
                in_answer = "✅" if row.get("context_answer_ok") else "❌"
            lines.append(
                f"| {row['case_id']} | {row['step']} | {query} | {resolved} | "
                f"{in_query} | {in_answer} | "
                f"{'✅' if row.get('success') else '❌'} |"
            )

    lines += [
        "",
        "## Снимки состояния агента",
        "",
        "`reports/benchmark.json` хранит для каждой реплики поле `state`:",
        "маршрут и `resolved_query`, guardrails, ACL-конверт, evidence, шаги",
        "`trace`, версии промптов, метрики и `fingerprint` состояния.",
        "В CSV вынесены `trace_steps`, `acl_*`, `state_fingerprint`,",
        "`llm_calls`, `tool_calls`, токены и разбивка времени.",
    ]

    failures = [row for row in rows if not row.get("success")]
    if failures:
        lines += ["", "## Ошибки", ""]
        for row in failures:
            reason = " ".join(str(row.get("error") or "проверка не пройдена").split())
            lines.append(
                f"- `{row['case_id']}.{row['step']}`: {reason}; "
                f"route={row.get('route') or '—'}, "
                f"answer={str(row.get('answer', ''))[:160]}"
            )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"csv": csv_path, "json": json_path, "md": md_path}
