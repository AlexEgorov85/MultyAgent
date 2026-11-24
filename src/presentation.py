"""Презентационный узел: превращает сырые ответы агентов в текст для человека.

Политика зависит от типа результата:

* ``count``   — одна строка, одна счётная метрика → «Завершённых проверок: 5.»;
* ``scalar``  — одна строка без счётной метрики → подписи «поле: значение»;
* ``table``   — несколько строк → заголовок и первые строки списком;
* ``text``    — готовый текст агента (retrieval) без изменений;
* ``report``  — черновик акта без изменений;
* ``investigation`` — вывод координатора без изменений;
* ``memory``  — подтверждение профиля без изменений;
* ``refusal`` / ``error`` — причина отказа/ошибки;
* ``empty``   — данных нет.

Правила: никаких технических имён колонок с подчёркиваниями, условия
вопроса не дублируются, длинные значения не раздувают ответ.

Дополнительно узел собирает ``trace`` — пошаговый путь работы агента для
раскрываемого блока в интерфейсе.
"""

from __future__ import annotations

import time
from typing import Any

from .i18n import t

_AUDIT_COUNT_COLUMNS = {
    "audit_count",
    "completed_count",
    "completed_audits_count",
}

_HEADLINE_COLUMNS = (
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

# Порядок колонок в таблице: сначала то, что осмысленно для человека,
# затем остальные поля запроса. Иначе первыми попадают служебные ID.
_TABLE_PREFERRED_COLUMNS = (
    "item_number",
    "title",
    "risk_level",
    "status",
    "deadline",
    "audit_code",
    "act_number",
    "pocket_year",
    "pocket",
    "year",
    "theme_code",
    "completed_audits_count",
    "audit_count",
    "deviations_count",
    "items_count",
)


def _table_columns(columns: list[str]) -> list[str]:
    preferred = [column for column in _TABLE_PREFERRED_COLUMNS if column in columns]
    return preferred + [column for column in columns if column not in preferred]

_LABELS_RU: dict[str, str] = {
    "audit_id": "проверка",
    "audit_code": "проверка",
    "act_id": "акт",
    "act_number": "акт",
    "item_id": "ID пункта",
    "item_number": "пункт",
    "item_type": "тип пункта",
    "test_type": "тип проверки",
    "title": "название",
    "risk_level": "уровень риска",
    "status": "статус",
    "act_status": "статус акта",
    "item_status": "статус пункта",
    "deadline": "срок",
    "closed_at": "закрыт",
    "act_date": "дата акта",
    "year": "год",
    "period_year": "год",
    "pocket_year": "год",
    "pocket_id": "карман",
    "pocket_title": "карман",
    "pocket": "карман",
    "theme_code": "тема",
    "theme": "тема",
    "theme_name": "тема",
    "audit_count": "Проверок",
    "completed_count": "Завершённых проверок",
    "completed_audits_count": "Завершённых проверок",
    "count": "Всего",
    "total": "Всего",
    "cnt": "Всего",
    "items_count": "Пунктов",
    "total_items": "Всего пунктов",
    "deviations_count": "Отклонений",
    "overdue_open_items": "Просроченных открытых пунктов",
    "overdue_open_items_count": "Просроченных открытых пунктов",
    "critical_open_count": "Критичных открытых пунктов",
    "overdue_share_pct": "Доля просроченных, %",
    "avg_risk": "Средний риск",
    "source_id": "источник",
    "source_type": "тип источника",
}

_LABELS_EN: dict[str, str] = {
    "audit_id": "audit",
    "audit_code": "audit",
    "act_id": "act",
    "act_number": "act",
    "item_id": "item ID",
    "item_number": "item",
    "item_type": "item type",
    "test_type": "test type",
    "title": "title",
    "risk_level": "risk level",
    "status": "status",
    "act_status": "act status",
    "item_status": "item status",
    "deadline": "deadline",
    "closed_at": "closed at",
    "act_date": "act date",
    "year": "year",
    "period_year": "year",
    "pocket_year": "year",
    "pocket_id": "pocket",
    "pocket_title": "pocket",
    "pocket": "pocket",
    "theme_code": "theme",
    "theme": "theme",
    "theme_name": "theme",
    "audit_count": "Audits",
    "completed_count": "Completed audits",
    "completed_audits_count": "Completed audits",
    "count": "Total",
    "total": "Total",
    "cnt": "Total",
    "items_count": "Items",
    "total_items": "Total items",
    "deviations_count": "Deviations",
    "overdue_open_items": "Overdue open items",
    "overdue_open_items_count": "Overdue open items",
    "critical_open_count": "Critical open items",
    "overdue_share_pct": "Overdue share, %",
    "avg_risk": "Average risk",
    "source_id": "source",
    "source_type": "source type",
}


_ROUTE_KEYS = {
    "analytics": "route_analytics",
    "retrieval": "route_retrieval",
    "report": "route_report",
    "investigation": "route_investigation",
    "memory": "route_memory",
    "smalltalk": "route_smalltalk",
    "unsafe": "route_unsafe",
    "out_of_domain": "route_out_of_domain",
}

_SMALLTALK_REASON_KEYS = {
    "smalltalk:greeting": "trace_smalltalk_greeting",
    "smalltalk:capabilities": "trace_smalltalk_capabilities",
    "smalltalk:thanks": "trace_smalltalk_thanks",
}

_AGENT_KEYS = {
    "orchestrator": "agent_orchestrator",
    "memory": "agent_memory",
    "guardrail": "agent_guard",
    "guardrails": "agent_guard",
    "analytics_agent": "agent_analytics",
    "retrieval_agent": "agent_retrieval",
    "report_agent": "agent_report",
    "investigation_coordinator": "agent_investigation",
    "investigation_agent": "agent_investigation",
    "inspector": "agent_inspector",
}

_PERFORMATIVE_KEYS = {
    "request": "performative_request",
    "inform": "performative_inform",
    "refuse": "performative_refuse",
    "failure": "performative_failure",
}

_VERDICT_KEYS = {
    "ok": "verdict_ok",
    "rewrite": "verdict_rewrite",
    "revise": "verdict_revise",
}


def _lang(state: dict[str, Any]) -> str:
    return str(state.get("language") or "ru")


def _route_label(lang: str, route: str) -> str:
    key = _ROUTE_KEYS.get(str(route or "").strip().lower())
    return t(lang, key) if key else (str(route or "").strip() or "—")


def _reason_label(lang: str, route: str, reason: str) -> str:
    """Убирает технические префиксы служебных маршрутов."""
    key = _SMALLTALK_REASON_KEYS.get(reason.strip().lower())
    if key and str(route).lower() == "smalltalk":
        return t(lang, key)
    return reason


def _agent_label(lang: str, value: str) -> str:
    key = _AGENT_KEYS.get(str(value or "").strip().lower())
    return t(lang, key) if key else str(value or "").strip()


def _performative_label(lang: str, value: str) -> str:
    key = _PERFORMATIVE_KEYS.get(str(value or "").strip().lower())
    return t(lang, key) if key else str(value or "").strip()


def _verdict_label(lang: str, value: str) -> str:
    key = _VERDICT_KEYS.get(str(value or "").strip().lower())
    return t(lang, key) if key else str(value or "").strip()


def _chips(*pairs: tuple[str, Any]) -> list[dict[str, str]]:
    """Компактные пары «подпись — значение» для строки шага."""
    return [
        {"label": label, "value": str(value)}
        for label, value in pairs
        if value is not None and str(value).strip()
    ]


def _english(state: dict[str, Any]) -> bool:
    return _lang(state).lower() == "en"


def _dynamic_label(column: str, state: dict[str, Any]) -> str | None:
    """Подпись по смыслу алиаса, когда точного совпадения нет.

    LLM свободно называет колонки (``completed_audits``, ``total_deviations``),
    поэтому опираемся на ключевые слова, а не только на точный словарь.
    """
    lower = column.lower()
    english = _english(state)
    completed = (
        "completed" in lower
        or "closed" in lower
        or "заверш" in lower
        or "закрыт" in lower
    )
    if "audit" in lower or "провер" in lower:
        if english:
            return "Completed audits" if completed else "Audits"
        return "Завершённых проверок" if completed else "Проверок"
    if "item" in lower or "пункт" in lower:
        return "Items" if english else "Пунктов"
    if "deviation" in lower or "отклон" in lower:
        return "Deviations" if english else "Отклонений"
    if "act" in lower or lower.endswith("акт"):
        return "Acts" if english else "Актов"
    if "count" in lower or lower.startswith(("cnt", "total")):
        return "Total" if english else "Всего"
    return None


def _label(column: str, state: dict[str, Any]) -> str:
    labels = _LABELS_EN if _english(state) else _LABELS_RU
    exact = labels.get(column)
    if exact:
        return exact
    dynamic = _dynamic_label(column, state)
    if dynamic:
        return dynamic
    return column.replace("_", " ").strip().capitalize()


def _fmt(value: Any, column: str, state: dict[str, Any]) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return t(_lang(state), "yes" if value else "no")
    if isinstance(value, float):
        number = f"{value:.1f}" if column.endswith("_pct") else f"{value:g}"
        if not _english(state):
            number = number.replace(".", ",")
        return f"{number} %" if column.endswith("_pct") else number
    if isinstance(value, int):
        if "year" in column or abs(value) < 1000:
            return str(value)
        text = f"{value:,}"
        return text.replace(",", " ") if not _english(state) else text
    return str(value)


def _content(state: dict[str, Any]) -> dict[str, Any]:
    acl = state.get("acl_response") or {}
    content = acl.get("content")
    return content if isinstance(content, dict) else {}


def _acl(state: dict[str, Any]) -> dict[str, Any]:
    acl = state.get("acl_response")
    return acl if isinstance(acl, dict) else {}


def _truncate(text: str, limit: int = 1200) -> str:
    clean = " ".join(str(text).split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def _is_table_boilerplate(answer: str) -> bool:
    """Служебная фраза «Найдено строк: N. Первые: …» не нужна перед таблицей."""
    text = answer.strip().lower()
    return not text or text.startswith(("найдено строк", "rows found"))


def _escape_md(value: str) -> str:
    """Экранирует значение для ячейки Markdown-таблицы."""
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _contextual_count_label(state: dict[str, Any], fallback: str) -> str:
    """Уточняет счётную подпись по формулировке вопроса.

    SQL может вернуть нейтральный алиас (``count``), но пользователь
    спрашивал про завершённые проверки — подпись должна это отражать.
    """
    query = str(state.get("user_query") or "").lower()
    if _english(state):
        if "audit" in query:
            if "completed" in query:
                return "Completed audits"
            if "overdue" in query:
                return "Overdue audits"
        if "item" in query and "overdue" in query:
            return "Overdue items"
        return fallback
    if "провер" in query or "аудит" in query:
        if "заверш" in query or "закрыт" in query:
            return "Завершённых проверок"
        if "просроч" in query:
            return "Просроченных проверок"
        if "открыт" in query:
            return "Открытых проверок"
        return fallback
    if "пункт" in query:
        if "просроч" in query:
            return "Просроченных пунктов"
        if "открыт" in query:
            return "Открытых пунктов"
    return fallback


def _present_analytics(state: dict[str, Any]) -> dict[str, Any]:
    content = _content(state)
    rows = content.get("rows") or []
    columns = content.get("columns") or []
    answer = str(content.get("answer") or "").strip()
    sql = content.get("sql")

    if rows:
        if len(rows) == 1:
            row = rows[0]
            source = str(content.get("answer_source") or "")
            # LLM/агент уже сформулировали ответ словами — не заменяем его
            # сухим шаблоном. Шаблон остаётся для fallback и старых payload'ов
            # без answer_source.
            use_answer = bool(answer) and not _is_table_boilerplate(answer) and (
                source in ("llm", "agent") or not source
            )
            headline = next(
                (key for key in _HEADLINE_COLUMNS if key in row and row[key] is not None),
                None,
            )
            single_numeric = False
            if headline is None and len(row) == 1:
                headline = next(iter(row))
                value = row[headline]
                single_numeric = isinstance(value, (int, float)) and not isinstance(
                    value, bool
                )
            if headline is not None:
                label = _label(headline, state)
                status_value = str(
                    row.get("status") or row.get("act_status") or ""
                ).strip().lower()
                if headline in _AUDIT_COUNT_COLUMNS:
                    if status_value.startswith("заверш"):
                        label = "Завершённых проверок"
                    elif status_value.startswith("complet"):
                        label = "Completed audits"
                value = _fmt(row[headline], headline, state)
                is_count = headline in _HEADLINE_COLUMNS or single_numeric
                if is_count:
                    label = _contextual_count_label(state, label)
                return {
                    "kind": "count" if is_count else "scalar",
                    "text": answer if use_answer else f"{label}: {value}.",
                    "facts": [{"label": label, "value": value}],
                    "sql": sql,
                }
            parts = [
                f"{_label(column, state)}: {_fmt(row[column], column, state)}"
                for column in columns
                if row.get(column) is not None
            ]
            if parts:
                body = ", ".join(parts)
                return {
                    "kind": "scalar",
                    "text": answer if use_answer else t(_lang(state), "result", body=body),
                    "facts": [],
                    "sql": sql,
                }

        shown_columns = _table_columns([column for column in columns if column])[:5]
        lines: list[str] = []
        if answer and not _is_table_boilerplate(answer):
            lines.extend([answer, ""])
        lines.extend([t(_lang(state), "present_table_title", count=len(rows)), ""])
        if shown_columns:
            headers = [_label(column, state) for column in shown_columns]
            lines.append("| " + " | ".join(_escape_md(item) for item in headers) + " |")
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            preview_rows = 20
            for row in rows[:preview_rows]:
                cells = [
                    _escape_md(_fmt(row.get(column), column, state))
                    for column in shown_columns
                ]
                lines.append("| " + " | ".join(cells) + " |")
            if len(rows) > preview_rows:
                lines.append("")
                lines.append(
                    t(
                        _lang(state),
                        "present_table_more",
                        count=len(rows) - preview_rows,
                    )
                )
        return {
            "kind": "table",
            "text": "\n".join(lines),
            "facts": [],
            "sql": sql,
        }

    if answer:
        return {"kind": "text", "text": answer, "facts": [], "sql": sql}
    if sql:
        return {
            "kind": "empty",
            "text": t(_lang(state), "present_empty"),
            "facts": [],
            "sql": sql,
        }
    return {"kind": "empty", "text": t(_lang(state), "present_empty"), "facts": []}


def _present_retrieval(state: dict[str, Any]) -> dict[str, Any]:
    content = _content(state)
    answer = str(content.get("answer") or "").strip()
    citations = [str(item) for item in content.get("citations") or []]
    if not answer:
        return {
            "kind": "empty",
            "text": t(_lang(state), "empty_retrieval"),
            "facts": [],
            "citations": citations,
        }
    return {
        "kind": "text",
        "text": answer,
        "facts": [{"label": t(_lang(state), "trace_citations"), "value": str(len(citations))}]
        if citations
        else [],
        "citations": citations,
        "search_mode": content.get("search_mode"),
    }


def _present_report(state: dict[str, Any]) -> dict[str, Any]:
    content = _content(state)
    draft = str(content.get("draft") or "").strip()
    citations = [str(item) for item in content.get("citations") or []]
    if not draft:
        return {
            "kind": "error",
            "text": t(_lang(state), "present_no_answer"),
            "facts": [],
        }
    return {
        "kind": "report",
        "text": draft,
        "facts": [],
        "citations": citations,
    }


def _present_investigation(state: dict[str, Any]) -> dict[str, Any]:
    content = _content(state)
    answer = str(content.get("answer") or "").strip()
    missing = [str(item) for item in content.get("missing") or []]
    if not answer:
        return {
            "kind": "error",
            "text": t(_lang(state), "present_no_answer"),
            "facts": [],
        }
    facts = [
        {"label": t(_lang(state), "trace_rounds"), "value": str(content.get("rounds", 0))}
    ]
    if missing:
        facts.append(
            {"label": t(_lang(state), "trace_missing"), "value": ", ".join(missing[:5])}
        )
    return {"kind": "investigation", "text": answer, "facts": facts}


def build_presentation(state: dict[str, Any]) -> dict[str, Any]:
    """Собирает представление ответа по маршруту и типу данных."""
    acl = _acl(state)
    performative = str(acl.get("performative") or "").lower()
    route = str(state.get("route") or "")

    if performative in ("refuse", "failure") or route in ("unsafe", "out_of_domain"):
        text = (
            str(state.get("final_answer") or "").strip()
            or str(_content(state).get("reason") or "").strip()
            or t(_lang(state), "present_no_answer")
        )
        kind = "refusal" if performative == "refuse" or route == "unsafe" else "error"
        if route == "out_of_domain":
            kind = "refusal"
        if performative == "inform" and route not in ("unsafe", "out_of_domain"):
            kind = "text"
        return {"kind": kind, "text": text, "facts": []}

    if route == "memory":
        return {
            "kind": "memory",
            "text": str(state.get("final_answer") or "").strip()
            or t(_lang(state), "present_no_answer"),
            "facts": [],
        }
    if route == "smalltalk":
        return {
            "kind": "text",
            "text": str(state.get("final_answer") or "").strip()
            or t(_lang(state), "present_no_answer"),
            "facts": [],
        }
    if route == "analytics":
        return _present_analytics(state)
    if route == "retrieval":
        return _present_retrieval(state)
    if route == "report":
        return _present_report(state)
    if route == "investigation":
        return _present_investigation(state)

    return {
        "kind": "text",
        "text": str(state.get("final_answer") or "").strip()
        or t(_lang(state), "present_no_answer"),
        "facts": [],
    }


def _memory_facts(profile: dict[str, Any] | None) -> str:
    if not profile:
        return "0"
    return str(len(profile))


def build_trace(state: dict[str, Any], presentation: dict[str, Any]) -> list[dict[str, Any]]:
    """Пошаговый путь работы агента для раскрываемого блока в UI.

    Каждый шаг кроме текста получает сведения для визуальной цепочки:
    ``agent`` (кто выполнял), ``kind`` (иконка), ``chips`` (короткие метрики)
    и, для SQL, отдельное поле ``code``.
    """
    lang = _lang(state)
    acl = _acl(state)
    content = _content(state)
    steps: list[dict[str, Any]] = []

    route = str(state.get("route") or "")
    route_label = _route_label(lang, route)

    original_query = str(state.get("user_query") or "").strip()
    resolved_query = str(state.get("resolved_query") or "").strip()
    if resolved_query and resolved_query != original_query:
        steps.append(
            {
                "step": "followup",
                "title": t(lang, "trace_followup"),
                "detail": (
                    f"{_truncate(original_query, 160)} → "
                    f"{_truncate(resolved_query, 220)}"
                ),
                "status": "ok",
                "agent": t(lang, "agent_orchestrator"),
                "kind": "route",
                "chips": _chips(
                    (
                        t(lang, "trace_followup_reason"),
                        _truncate(str(state.get("resolved_reason") or ""), 120),
                    )
                ),
            }
        )

    reason = _truncate(str(state.get("route_reason") or ""), 240)
    reason = _reason_label(lang, route, reason)
    confidence = state.get("route_confidence")
    route_detail = f"{route_label} — {reason}" if reason else route_label
    confidence_chip = None
    if (
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and confidence > 0
    ):
        confidence_chip = f"{confidence * 100:.0f}%"
    chips = _chips((t(lang, "trace_confidence"), confidence_chip))
    if route == "analytics":
        mode = str(state.get("analytics_mode") or "").strip()
        if mode:
            chips.append({"label": t(lang, "trace_mode"), "value": mode})
    steps.append(
        {
            "step": "route",
            "title": t(lang, "trace_route"),
            "detail": route_detail,
            "status": "ok",
            "agent": t(lang, "agent_orchestrator"),
            "kind": "route",
            "route": route,
            "route_label": route_label,
            "chips": chips,
        }
    )

    profile = state.get("profile") or {}
    profile_size = len(profile)
    steps.append(
        {
            "step": "memory",
            "title": t(lang, "trace_memory"),
            "detail": t(lang, "trace_memory_detail", count=_memory_facts(profile)),
            "status": "ok",
            "agent": t(lang, "agent_memory"),
            "kind": "memory",
            "chips": _chips((t(lang, "trace_facts"), profile_size)),
        }
    )

    guardrail = state.get("guardrail") or {}
    if guardrail:
        request_safe = bool(guardrail.get("safe", True))
        steps.append(
            {
                "step": "guard_request",
                "title": t(lang, "trace_guard"),
                "detail": t(lang, "trace_safe")
                if request_safe
                else str(
                    guardrail.get("reason") or t(lang, "trace_failed_generic")
                ),
                "status": "ok" if request_safe else "warn",
                "agent": t(lang, "agent_guard"),
                "kind": "shield",
            }
        )

    if route == "analytics":
        sql = content.get("sql")
        if sql:
            steps.append(
                {
                    "step": "sql",
                    "title": t(lang, "trace_sql"),
                    "detail": _truncate(str(sql), 1500),
                    "code": _truncate(str(sql), 1500),
                    "status": "ok",
                    "agent": t(lang, "agent_analytics"),
                    "kind": "database",
                }
            )
        rows = content.get("rows") or []
        columns = content.get("columns") or []
        metrics = content.get("metrics") or {}
        detail = t(
            lang,
            "trace_rows_detail",
            rows=len(rows),
            columns=len(columns),
        )
        retries = int(metrics.get("sql_retries") or 0)
        if retries:
            detail += " " + t(lang, "trace_retries", count=retries)
        steps.append(
            {
                "step": "sql_result",
                "title": t(lang, "trace_result"),
                "detail": detail,
                "status": "ok" if rows else "warn",
                "agent": t(lang, "agent_analytics"),
                "kind": "table",
                "chips": _chips(
                    (t(lang, "trace_rows"), len(rows)),
                    (t(lang, "trace_columns"), len(columns)),
                    (t(lang, "trace_retries_short"), retries or None),
                ),
            }
        )

    if route == "retrieval":
        citations = content.get("citations") or []
        chunks = int((content.get("metrics") or {}).get("chunks") or 0)
        search_mode = str(content.get("search_mode") or "—")
        steps.append(
            {
                "step": "retrieval",
                "title": t(lang, "trace_retrieval"),
                "detail": t(
                    lang,
                    "trace_retrieval_detail",
                    mode=search_mode,
                    chunks=chunks,
                ),
                "status": "ok",
                "agent": t(lang, "agent_retrieval"),
                "kind": "search",
                "chips": _chips(
                    (t(lang, "trace_mode"), search_mode),
                    (t(lang, "trace_chunks"), chunks),
                ),
            }
        )
        steps.append(
            {
                "step": "citations",
                "title": t(lang, "trace_citations"),
                "detail": t(lang, "trace_citations_detail", count=len(citations)),
                "status": "ok" if citations else "warn",
                "agent": t(lang, "agent_retrieval"),
                "kind": "book",
                "chips": _chips((t(lang, "trace_found"), len(citations))),
            }
        )

    if route == "report":
        citations = content.get("citations") or []
        review = content.get("review") or {}
        iterations = int((content.get("metrics") or {}).get("inspector_iterations") or 0)
        verdict = str(review.get("verdict") or "—")
        verdict_label = _verdict_label(lang, verdict)
        steps.append(
            {
                "step": "report",
                "title": t(lang, "trace_report"),
                "detail": t(lang, "trace_report_detail", count=len(citations)),
                "status": "ok",
                "agent": t(lang, "agent_report"),
                "kind": "file",
                "chips": _chips((t(lang, "trace_links"), len(citations))),
            }
        )
        steps.append(
            {
                "step": "inspector",
                "title": t(lang, "trace_inspector"),
                "detail": t(
                    lang,
                    "trace_inspector_detail",
                    verdict=verdict_label,
                    iterations=iterations,
                ),
                "status": "ok" if verdict == "ok" else "warn",
                "agent": t(lang, "agent_inspector"),
                "kind": "check",
                "chips": _chips(
                    (t(lang, "trace_verdict"), verdict_label),
                    (t(lang, "trace_iterations"), iterations),
                ),
            }
        )

    if route == "investigation":
        content_rounds = int(content.get("rounds") or 0)
        evidence = content.get("evidence") or []
        steps.append(
            {
                "step": "investigation",
                "title": t(lang, "trace_investigation"),
                "detail": t(
                    lang,
                    "trace_investigation_detail",
                    rounds=content_rounds,
                    evidence=len(evidence),
                ),
                "status": "ok",
                "agent": t(lang, "agent_investigation"),
                "kind": "compass",
                "chips": _chips(
                    (t(lang, "trace_rounds"), content_rounds),
                    (t(lang, "trace_evidence"), len(evidence)),
                ),
            }
        )

    sender = str(acl.get("sender") or "")
    performative = str(acl.get("performative") or "")
    if sender or performative:
        sender_label = _agent_label(lang, sender)
        receiver_label = _agent_label(
            lang, str(acl.get("receiver") or "orchestrator")
        )
        detail = " → ".join(
            part for part in (sender_label, receiver_label) if part
        )
        performative_label = _performative_label(lang, performative)
        steps.append(
            {
                "step": "acl",
                "title": t(lang, "trace_acl"),
                "detail": detail or performative_label,
                "status": "ok",
                "agent": sender_label or t(lang, "agent_orchestrator"),
                "kind": "message",
                "chips": _chips(
                    (t(lang, "trace_performative"), performative_label)
                ),
            }
        )

    answer_guard = state.get("answer_guardrail") or guardrail
    if answer_guard:
        answer_safe = bool(answer_guard.get("safe", True))
        steps.append(
            {
                "step": "guard_answer",
                "title": t(lang, "trace_answer"),
                "detail": t(lang, "trace_passed")
                if answer_safe
                else str(
                    answer_guard.get("reason") or t(lang, "trace_not_passed")
                ),
                "status": "ok" if answer_safe else "warn",
                "agent": t(lang, "agent_guard"),
                "kind": "shield",
            }
        )

    metrics = state.get("metrics") or {}
    started = metrics.get("started_at")
    if isinstance(started, (int, float)):
        seconds = max(0.0, time.perf_counter() - float(started))
        steps.append(
            {
                "step": "latency",
                "title": t(lang, "trace_latency"),
                "detail": t(lang, "trace_latency_detail", seconds=f"{seconds:.1f}"),
                "status": "ok",
                "agent": t(lang, "agent_orchestrator"),
                "kind": "clock",
                "duration_s": round(seconds, 1),
            }
        )

    return steps


def present(state: dict[str, Any]) -> dict[str, Any]:
    """Узел графа: финальный текст + представление + путь работы."""
    presentation = build_presentation(state)
    text = str(presentation.get("text") or "").strip()
    if not text:
        text = t(_lang(state), "present_no_answer")
    presentation["text"] = text
    return {
        "presentation": presentation,
        "trace": build_trace(state, presentation),
        "final_answer": text,
    }
