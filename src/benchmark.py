"""Многоуровневый бенчмарк: простые, сложные и цепочечные вопросы.

Модуль не зависит от LangGraph и LLM: он читает и проверяет набор кейсов,
а также оценивает уже полученные ответы графа. Запуск — ``scripts/benchmark.py``.

Три уровня:
* ``simple`` — один факт или один инструмент;
* ``complex`` — multi-tool, отчёт, расследование, динамика;
* ``chain`` — несколько реплик в одной нити, где проверяется перенос
  сущностей (год, тема, код проверки) в ``resolved_query`` и в ответ.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Sequence

from .metrics import mean, percentile

TIERS: tuple[str, ...] = ("simple", "complex", "chain")
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

            for field in ("min_evidence", "min_acl_rounds"):
                value = turn.get(field, 0)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    errors.append(f"{prefix}: {field} должен быть неотрицательным целым")

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
) -> dict[str, Any]:
    """Оценивает один ход: маршрут, контекст, числа, tools, evidence."""
    row = _base_row(case, turn, step)
    content = content_of(result)
    route = str(result.get("route", "") or "")
    answer = str(result.get("final_answer", "") or "")
    resolved = str(result.get("resolved_query", "") or "")
    evidence = extract_evidence(result)
    evidence_types = {str(item.get("type", "")) for item in evidence}
    tools = infer_tools(route, content)
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
    metrics = content.get("metrics") if isinstance(content.get("metrics"), dict) else {}
    acl_rounds = int(metrics.get("acl_rounds") or content.get("rounds") or 0)
    evidence_applicable = bool(
        route in FACTUAL_ROUTES or expected_evidence or min_evidence
    )

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
    sql_ok = _sql_is_valid(content)
    answer_ok = bool(answer.strip())
    success = all(
        (
            route_ok,
            context_ok,
            numbers_ok,
            tools_ok,
            strategy_ok,
            include_ok,
            exclude_ok,
            evidence_ok,
            rounds_ok,
            sql_ok,
            answer_ok,
        )
    )

    row.update(
        {
            "route": route,
            "resolved_query": resolved,
            "strategy": strategy,
            "tools_actual": ";".join(tools),
            "tools_count": len(tools),
            "context_applicable": bool(expected_context),
            "numbers_applicable": bool(expected_numbers),
            "tools_applicable": bool(expected_tools),
            "strategy_applicable": bool(expected_strategy),
            "evidence_applicable": evidence_applicable,
            "rounds_applicable": min_rounds > 0,
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
            "sql_ok": sql_ok,
            "answer_ok": answer_ok,
            "success": success,
            "evidence_count": len(evidence),
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
    summary: dict[str, float | int] = {
        "cases": len(case_ids),
        "turns": len(rows),
        "route_accuracy": _rate(rows, "route_ok"),
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
        "latency_mean_sec": mean(latencies),
        "latency_p50_sec": percentile(latencies, 0.5),
        "latency_p95_sec": percentile(latencies, 0.95),
        "avg_tools_per_turn": mean([int(row.get("tools_count", 0)) for row in rows]),
    }

    for tier in TIERS:
        tier_rows = [row for row in rows if row.get("tier") == tier]
        tier_cases = {row["case_id"] for row in tier_rows}
        summary[f"{tier}_cases"] = len(tier_cases)
        summary[f"{tier}_turns"] = len(tier_rows)
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
) -> dict[str, Path]:
    """Пишет CSV, JSON и Markdown-отчёт."""
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    case_summary = summarize_cases(rows)

    csv_path = directory / "benchmark.csv"
    if rows:
        fieldnames = list(rows[0].keys())
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    json_path = directory / "benchmark.json"
    json_path.write_text(
        json.dumps(
            {
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
        "Уровни: простые вопросы, сложные вопросы и цепочки с контекстом.",
        "",
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
        "| Уровень | Кейсов | Шагов | Success |",
        "|---|---:|---:|---:|",
    ]
    for tier in TIERS:
        lines.append(
            f"| {tier} | {summary.get(f'{tier}_cases', 0)} | "
            f"{summary.get(f'{tier}_turns', 0)} | "
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
            query = str(row["query"]).replace("|", "\\|")
            resolved = str(row["resolved_query"]).replace("|", "\\|")
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

    failures = [row for row in rows if not row.get("success")]
    if failures:
        lines += ["", "## Ошибки", ""]
        for row in failures:
            reason = row.get("error") or "проверка не пройдена"
            lines.append(
                f"- `{row['case_id']}.{row['step']}`: {reason}; "
                f"route={row.get('route') or '—'}, "
                f"answer={str(row.get('answer', ''))[:160]}"
            )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"csv": csv_path, "json": json_path, "md": md_path}
