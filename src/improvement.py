"""Диагностика бенчмарка, сравнение прогонов и gate для доработок.

Модуль работает с `reports/benchmark.json` и не вызывает LLM. Он нужен,
чтобы превратить провалы в приоритизированный backlog, сравнить baseline
и candidate, а затем решить, можно ли принимать изменение.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Sequence

CATEGORY_META: dict[str, dict[str, Any]] = {
    "provider": {
        "title": "Провайдер / лимиты",
        "severity": 0,
        "risk": "external",
        "exclude_from_quality": True,
        "action": "Проверить лимит и backoff, не менять промпты до устранения 429/timeout.",
        "files": ["src/llm.py"],
    },
    "runtime": {
        "title": "Ошибка выполнения",
        "severity": 0,
        "risk": "external",
        "exclude_from_quality": True,
        "action": "Разобрать traceback и окружение; это не ошибка качества ответа.",
        "files": ["scripts/benchmark.py", "src/db_runtime.py"],
    },
    "routing": {
        "title": "Маршрутизация",
        "severity": 5,
        "risk": "medium",
        "exclude_from_quality": False,
        "action": "Добавить deterministic pre-router или few-shot для ошибочных интентов.",
        "files": [
            "src/prompts/router.md",
            "src/graph/main_graph.py",
        ],
    },
    "context": {
        "title": "Перенос контекста",
        "severity": 5,
        "risk": "medium",
        "exclude_from_quality": False,
        "action": "Явно переносить слоты year/theme/item_type/risk/audit_code в resolved_query.",
        "files": [
            "src/prompts/resolve_followup_ru.md",
            "src/prompts/resolve_followup_en.md",
            "src/dialogue.py",
        ],
    },
    "tool_policy": {
        "title": "Выбор инструментов",
        "severity": 4,
        "risk": "medium",
        "exclude_from_quality": False,
        "action": "Уточнить описания tools и приоритет готовых шаблонов над генерацией.",
        "files": [
            "src/prompts/analytics_plan_sql.md",
            "src/prompts/tools_plan.md",
            "src/tools/registry.py",
        ],
    },
    "sql": {
        "title": "SQL",
        "severity": 5,
        "risk": "high",
        "exclude_from_quality": False,
        "action": "Улучшить примеры SQL, self-check и repair-feedback; ограничить retries.",
        "files": [
            "src/prompts/analytics_plan_sql.md",
            "src/prompts/analytics_repair_sql.md",
            "src/tools/sql_guard.py",
        ],
    },
    "evidence": {
        "title": "Evidence",
        "severity": 4,
        "risk": "medium",
        "exclude_from_quality": False,
        "action": "Проверить, что ветка возвращает evidence и что report его сохраняет.",
        "files": [
            "src/graph/analytics_graph.py",
            "src/graph/report_graph.py",
            "src/graph/retrieval_graph.py",
        ],
    },
    "citations": {
        "title": "Цитаты retrieval",
        "severity": 4,
        "risk": "medium",
        "exclude_from_quality": False,
        "action": "Усилить цитирование и critic; проверить hybrid search и chunking.",
        "files": [
            "src/prompts/retrieval_answer.md",
            "src/prompts/retrieval_critique.md",
            "src/rag/vector_store.py",
        ],
    },
    "numeric": {
        "title": "Числа в ответе",
        "severity": 5,
        "risk": "high",
        "exclude_from_quality": False,
        "action": "Проверить SQL-агрегацию и формат ответа; не подменять числа текстом.",
        "files": [
            "src/prompts/analytics_summarize.md",
            "src/graph/analytics_graph.py",
        ],
    },
    "answer": {
        "title": "Содержание ответа",
        "severity": 3,
        "risk": "low",
        "exclude_from_quality": False,
        "action": "Поправить формат/рубрику ответа, не меняя данные.",
        "files": ["src/prompts/format/*.md"],
    },
    "steps": {
        "title": "Шаги агента",
        "severity": 2,
        "risk": "low",
        "exclude_from_quality": False,
        "action": "Проверить ветку графа и состав trace: лишние или пропущенные шаги.",
        "files": ["src/graph/main_graph.py", "src/presentation.py"],
    },
    "efficiency": {
        "title": "Эффективность",
        "severity": 2,
        "risk": "low",
        "exclude_from_quality": False,
        "action": "Сократить контекст, число вызовов или выбрать более дешёвую модель.",
        "files": ["src/llm.py", "src/graph/main_graph.py"],
    },
    "unknown": {
        "title": "Неклассифицированный провал",
        "severity": 1,
        "risk": "medium",
        "exclude_from_quality": False,
        "action": "Разобрать state вручную и добавить новый признак в triage.",
        "files": [],
    },
}


def load_report(path: str | Path) -> dict[str, Any]:
    """Читает benchmark.json."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _num(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(row: dict[str, Any], key: str, default: int = 0) -> int:
    return int(_num(row, key, default))


def classify_turn(row: dict[str, Any]) -> list[str]:
    """Определяет категории провала одной реплики.

    Провайдер и runtime-ошибка отделяются от ошибок качества: остальные
    проверки в такой реплике недостоверны и не должны попадать в backlog
    как «плохой router» или «плохой SQL».
    """
    if _int(row, "llm_errors") > 0:
        return ["provider"]
    if row.get("error"):
        return ["runtime"]

    categories: list[str] = []
    if not bool(row.get("route_ok", True)):
        categories.append("routing")
    if row.get("context_applicable") and not bool(
        row.get("context_resolved_ok", True)
    ):
        categories.append("context")
    if not bool(row.get("tools_ok", True)) or not bool(
        row.get("strategy_ok", True)
    ) or not bool(row.get("forbidden_tools_ok", True)):
        categories.append("tool_policy")
    if not bool(row.get("steps_ok", True)) or not bool(
        row.get("max_steps_ok", True)
    ):
        categories.append("steps")
    if not bool(row.get("sql_ok", True)) or not bool(
        row.get("sql_retries_ok", True)
    ):
        categories.append("sql")
    elif _int(row, "sql_retries") > 0 and not bool(row.get("success", True)):
        categories.append("sql")
    if not bool(row.get("evidence_ok", True)):
        categories.append("evidence")
    if not bool(row.get("citations_ok", True)):
        categories.append("citations")
    if not bool(row.get("numbers_ok", True)):
        categories.append("numeric")
    if not bool(row.get("include_ok", True)) or not bool(
        row.get("exclude_ok", True)
    ):
        categories.append("answer")
    if not all(
        bool(row.get(key, True))
        for key in (
            "llm_calls_ok",
            "tool_calls_ok",
            "tokens_ok",
            "cost_ok",
            "latency_ok",
            "acl_rounds_ok",
        )
    ):
        categories.append("efficiency")

    if not categories and not bool(row.get("success", True)):
        if not bool(row.get("answer_success", True)):
            categories.append("answer")
        elif not bool(row.get("process_success", True)):
            categories.append("efficiency")
        else:
            categories.append("unknown")
    return list(dict.fromkeys(categories))


def _validation_command(cluster: dict[str, Any]) -> str:
    cases = cluster.get("cases", [])
    tier = cluster.get("tier", "")
    if len(cases) <= 3 and cases:
        joined = " ".join(cases)
        return f".venv\\Scripts\\python.exe scripts\\benchmark.py --only {joined}"
    if tier:
        return f".venv\\Scripts\\python.exe scripts\\benchmark.py --tier {tier}"
    return ".venv\\Scripts\\python.exe scripts\\benchmark.py --limit 5"


def build_backlog(
    report: dict[str, Any],
    *,
    include_provider: bool = True,
) -> list[dict[str, Any]]:
    """Строит приоритизированный backlog по провалам прогона."""
    clusters: dict[tuple[str, str, str], dict[str, Any]] = {}

    for row in report.get("turns", []):
        if row.get("success"):
            continue
        categories = classify_turn(row) or ["unknown"]
        for category in categories:
            if category == "provider" and not include_provider:
                continue
            meta = CATEGORY_META.get(category, CATEGORY_META["unknown"])
            key = (
                category,
                str(row.get("tier", "")),
                str(row.get("expected_route", "")),
            )
            cluster = clusters.setdefault(
                key,
                {
                    "category": category,
                    "title": meta["title"],
                    "severity": meta["severity"],
                    "risk": meta["risk"],
                    "exclude_from_quality": meta["exclude_from_quality"],
                    "action": meta["action"],
                    "target_files": list(meta["files"]),
                    "tier": key[1],
                    "route": key[2],
                    "cases": set(),
                    "steps": [],
                    "queries": [],
                    "errors": [],
                    "prompts": set(),
                    "count": 0,
                    "tokens": 0,
                    "latency_sec": 0.0,
                    "llm_calls": 0,
                    "tool_calls": 0,
                },
            )
            cluster["count"] += 1
            cluster["cases"].add(str(row.get("case_id", "")))
            cluster["steps"].append(
                {
                    "case_id": row.get("case_id"),
                    "step": row.get("step"),
                    "route": row.get("route"),
                    "latency_sec": _num(row, "latency_sec"),
                    "total_tokens": _int(row, "total_tokens"),
                    "llm_calls": _int(row, "llm_calls"),
                    "tool_calls": _int(row, "tool_calls"),
                }
            )
            if row.get("query") and row["query"] not in cluster["queries"]:
                cluster["queries"].append(str(row["query"]))
            if row.get("error"):
                cluster["errors"].append(str(row["error"])[:500])
            for item in str(row.get("prompts", "") or "").split(";"):
                if item.strip():
                    cluster["prompts"].add(item.strip())
            cluster["tokens"] += _int(row, "total_tokens")
            cluster["latency_sec"] += _num(row, "latency_sec")
            cluster["llm_calls"] += _int(row, "llm_calls")
            cluster["tool_calls"] += _int(row, "tool_calls")

    backlog: list[dict[str, Any]] = []
    for cluster in clusters.values():
        cluster["cases"] = sorted(item for item in cluster["cases"] if item)
        cluster["prompts"] = sorted(cluster["prompts"])
        cluster["queries"] = cluster["queries"][:5]
        cluster["errors"] = list(dict.fromkeys(cluster["errors"]))[:5]
        cluster["validation"] = _validation_command(cluster)
        backlog.append(cluster)

    backlog.sort(
        key=lambda item: (
            -int(item.get("severity", 0)),
            -int(item.get("count", 0)),
            -float(item.get("tokens", 0)),
            -float(item.get("latency_sec", 0.0)),
        )
    )
    return backlog


def _turn_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in report.get("turns", []):
        key = f"{row.get('case_id')}.{row.get('step')}"
        result[key] = row
    return result


def _summary_delta(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, float]:
    base = baseline.get("summary") or {}
    cand = candidate.get("summary") or {}
    result: dict[str, float] = {}
    for key in sorted(set(base) | set(cand)):
        base_value = base.get(key)
        cand_value = cand.get(key)
        if isinstance(base_value, (int, float)) and isinstance(
            cand_value, (int, float)
        ):
            result[key] = float(cand_value) - float(base_value)
    return result


def diff_runs(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Сравнивает два benchmark.json по репликам и summary."""
    base_turns = _turn_map(baseline)
    cand_turns = _turn_map(candidate)
    improvements: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    new_turns: list[str] = []
    missing_turns: list[str] = []
    metric_deltas: list[dict[str, Any]] = []

    for key in sorted(set(base_turns) | set(cand_turns)):
        if key not in base_turns:
            new_turns.append(key)
            continue
        if key not in cand_turns:
            missing_turns.append(key)
            continue
        before = base_turns[key]
        after = cand_turns[key]
        change = {}
        for field in ("success", "answer_success", "process_success"):
            before_value = bool(before.get(field))
            after_value = bool(after.get(field))
            if before_value != after_value:
                change[field] = {"before": before_value, "after": after_value}
        if change:
            item = {
                "key": key,
                "case_id": before.get("case_id"),
                "step": before.get("step"),
                "tier": before.get("tier"),
                "query": before.get("query"),
                "changes": change,
                "before_route": before.get("route"),
                "after_route": after.get("route"),
                "before_answer": before.get("answer"),
                "after_answer": after.get("answer"),
            }
            if bool(after.get("success")) and not bool(before.get("success")):
                improvements.append(item)
            elif bool(before.get("success")) and not bool(after.get("success")):
                regressions.append(item)

        for field in (
            "total_tokens",
            "latency_sec",
            "cost_usd",
            "llm_calls",
            "tool_calls",
        ):
            delta = _num(after, field) - _num(before, field)
            if abs(delta) > 0:
                metric_deltas.append(
                    {
                        "key": key,
                        "metric": field,
                        "before": _num(before, field),
                        "after": _num(after, field),
                        "delta": delta,
                    }
                )

    return {
        "baseline_run_id": (baseline.get("environment") or {}).get("run_id", ""),
        "candidate_run_id": (candidate.get("environment") or {}).get("run_id", ""),
        "summary_delta": _summary_delta(baseline, candidate),
        "improvements": improvements,
        "regressions": regressions,
        "new_turns": new_turns,
        "missing_turns": missing_turns,
        "metric_deltas": metric_deltas,
        "regression_count": len(regressions),
        "improvement_count": len(improvements),
    }


def evaluate_gate(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    max_success_drop: float = 0.0,
    max_token_increase: float = 0.10,
    max_latency_increase: float = 0.10,
    max_cost_increase: float = 0.10,
    max_regressions: int = 0,
) -> dict[str, Any]:
    """Regression-gate: можно ли принимать candidate."""
    diff = diff_runs(baseline, candidate)
    base = baseline.get("summary") or {}
    cand = candidate.get("summary") or {}
    checks: list[dict[str, Any]] = []

    def add_check(
        name: str,
        passed: bool,
        before: Any,
        after: Any,
        threshold: str,
    ) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "before": before,
                "after": after,
                "threshold": threshold,
            }
        )

    for key, limit in (
        ("success_rate", max_success_drop),
        ("answer_success_rate", max_success_drop),
        ("process_success_rate", max_success_drop),
    ):
        before = float(base.get(key, 0.0))
        after = float(cand.get(key, 0.0))
        add_check(
            key,
            after >= before - limit,
            before,
            after,
            f">= {before - limit:.3f}",
        )

    for key, limit in (
        ("total_tokens_total", max_token_increase),
        ("latency_p95_sec", max_latency_increase),
        ("cost_usd_total", max_cost_increase),
    ):
        before = float(base.get(key, 0.0))
        after = float(cand.get(key, 0.0))
        allowed = before * (1.0 + limit) if before > 0 else after
        add_check(
            key,
            after <= allowed,
            before,
            after,
            f"<= {allowed:.3f}",
        )

    add_check(
        "regressions",
        diff["regression_count"] <= max_regressions,
        diff["regression_count"],
        diff["regression_count"],
        f"<= {max_regressions}",
    )

    passed = all(item["passed"] for item in checks)
    return {
        "passed": passed,
        "checks": checks,
        "reasons": [item["name"] for item in checks if not item["passed"]],
        "diff": diff,
    }


def format_backlog_md(
    backlog: Sequence[dict[str, Any]],
    *,
    source: str = "reports/benchmark.json",
) -> str:
    """Формирует Markdown-backlog провалов бенчмарка с командами проверки."""
    lines = [
        "# Backlog доработок по бенчмарку",
        "",
        f"Источник: `{source}`.",
        "",
        "| # | Приоритет | Категория | Уровень | Маршрут | Кейсов | Реплик | Токены |",
        "|---:|---:|---|---|---|---:|---:|---:|",
    ]
    for index, item in enumerate(backlog, start=1):
        lines.append(
            f"| {index} | {item['severity']} | {item['title']} | "
            f"{item['tier'] or '—'} | {item['route'] or '—'} | "
            f"{len(item['cases'])} | {item['count']} | {item['tokens']} |"
        )

    for index, item in enumerate(backlog, start=1):
        lines += [
            "",
            f"## {index}. {item['title']}",
            "",
            f"- Категория: `{item['category']}`",
            f"- Приоритет: **{item['severity']}**, риск: `{item['risk']}`",
            f"- Уровень: `{item['tier'] or '—'}`, маршрут: `{item['route'] or '—'}`",
            f"- Реплик: {item['count']}, кейсов: {len(item['cases'])}",
            f"- Токены: {item['tokens']}, latency: {item['latency_sec']:.3f} с",
            f"- LLM/tools: {item['llm_calls']} / {item['tool_calls']}",
        ]
        if item.get("exclude_from_quality"):
            lines.append(
                "- **Не ошибка качества агента:** сначала устранить провайдера."
            )
        lines += [
            "",
            f"**Что делать:** {item['action']}",
            "",
            "**Файлы:**",
        ]
        for path in item.get("target_files") or []:
            lines.append(f"- `{path}`")
        if not item.get("target_files"):
            lines.append("- определить по `state` вручную")
        lines += ["", "**Кейсы:** " + ", ".join(f"`{case}`" for case in item["cases"])]
        if item.get("queries"):
            lines += ["", "**Примеры запросов:**"]
            for query in item["queries"]:
                lines.append(f"- {query}")
        if item.get("errors"):
            lines += ["", "**Ошибки:**"]
            for error in item["errors"]:
                lines.append(f"- `{error}`")
        lines += [
            "",
            "**Проверка:**",
            "```powershell",
            item["validation"],
            "```",
        ]
    return "\n".join(lines) + "\n"


def format_diff_md(diff: dict[str, Any], gate: dict[str, Any] | None = None) -> str:
    """Формирует Markdown-отчёт о разнице двух прогонов и regression-gate."""
    lines = [
        "# Сравнение прогонов бенчмарка",
        "",
        f"Baseline: `{diff['baseline_run_id'] or '—'}`, "
        f"candidate: `{diff['candidate_run_id'] or '—'}`.",
        "",
        f"Улучшений: **{diff['improvement_count']}**, "
        f"регрессий: **{diff['regression_count']}**.",
        "",
        "## Изменение summary",
        "",
        "| Метрика | Δ |",
        "|---|---:|",
    ]
    for key, value in diff["summary_delta"].items():
        lines.append(f"| `{key}` | {value:+.3f} |")

    if gate is not None:
        lines += [
            "",
            "## Gate",
            "",
            f"Итог: **{'PASS' if gate['passed'] else 'FAIL'}**.",
            "",
            "| Проверка | Было | Стало | Порог | Итог |",
            "|---|---:|---:|---|---:|",
        ]
        for check in gate["checks"]:
            lines.append(
                f"| `{check['name']}` | {check['before']} | {check['after']} | "
                f"{check['threshold']} | {'✅' if check['passed'] else '❌'} |"
            )
        if gate["reasons"]:
            lines += ["", "Причины отказа: " + ", ".join(gate["reasons"])]

    if diff["improvements"]:
        lines += ["", "## Улучшения", ""]
        for item in diff["improvements"]:
            lines.append(
                f"- `{item['key']}`: route `{item['before_route']}` → "
                f"`{item['after_route']}`"
            )

    if diff["regressions"]:
        lines += ["", "## Регрессии", ""]
        for item in diff["regressions"]:
            lines.append(
                f"- `{item['key']}`: route `{item['before_route']}` → "
                f"`{item['after_route']}`"
            )
            if item.get("after_answer"):
                lines.append(f"  - ответ: {str(item['after_answer'])[:240]}")

    if diff["new_turns"]:
        lines += ["", "Новые реплики: " + ", ".join(diff["new_turns"])]
    if diff["missing_turns"]:
        lines += ["", "Пропавшие реплики: " + ", ".join(diff["missing_turns"])]
    return "\n".join(lines) + "\n"
