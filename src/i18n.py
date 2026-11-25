"""Небольшой словарь пользовательских сообщений для RU/EN."""

from __future__ import annotations

from typing import Any

_TEXTS: dict[str, dict[str, str]] = {
    "no_acl": {
        "ru": "нет ACL-запроса",
        "en": "no ACL request",
    },
    "invalid_acl": {
        "ru": "Невалидный ACL: {error}",
        "en": "Invalid ACL: {error}",
    },
    "request_only": {
        "ru": "{agent} принимает только performative=request",
        "en": "{agent} accepts only performative=request",
    },
    "missing_question": {
        "ru": "В ACL-запросе нет question",
        "en": "The ACL request has no question",
    },
    "plan_failed": {
        "ru": "Не удалось построить план: {error}",
        "en": "Could not build a plan: {error}",
    },
    "repair_failed": {
        "ru": "Не удалось исправить SQL: {error}",
        "en": "Could not repair SQL: {error}",
    },
    "tools_failed": {
        "ru": "Не удалось выбрать инструменты: {error}",
        "en": "Could not select tools: {error}",
    },
    "answer_failed": {
        "ru": "Не удалось сформировать ответ: {error}",
        "en": "Could not build an answer: {error}",
    },
    "critic_failed": {
        "ru": "Критик недоступен: {error}",
        "en": "The critic is unavailable: {error}",
    },
    "draft_failed": {
        "ru": "Не удалось подготовить черновик: {error}",
        "en": "Could not prepare a draft: {error}",
    },
    "inspector_failed": {
        "ru": "Inspector недоступен: {error}",
        "en": "Inspector is unavailable: {error}",
    },
    "revise_failed": {
        "ru": "Не удалось исправить черновик: {error}",
        "en": "Could not revise the draft: {error}",
    },
    "synthesis_failed": {
        "ru": "Синтез не выполнен: {error}",
        "en": "Synthesis failed: {error}",
    },
    "request_declined": {
        "ru": "Запрос отклонён",
        "en": "Request declined",
    },
    "request_failed": {
        "ru": "Не удалось выполнить запрос",
        "en": "Could not complete the request",
    },
    "run_failed": {
        "ru": "Ошибка выполнения",
        "en": "Run failed",
    },
    "found_rows": {
        "ru": "Найдено строк: {count}. Первые: {preview}.",
        "en": "Rows found: {count}. First: {preview}.",
    },
    "limit_notice": {
        "ru": "Показано не более {limit} строк: результат ограничен настройкой MAX_ROWS.",
        "en": "Showing at most {limit} rows: the result is capped by MAX_ROWS.",
    },
    "result": {
        "ru": "Результат — {body}.",
        "en": "Result — {body}.",
    },
    "empty_retrieval": {
        "ru": "Подходящих формулировок в актах и методичках не найдено.",
        "en": "No matching wording was found in the acts or methodologies.",
    },
    "relevant_fragment": {
        "ru": "Наиболее релевантный фрагмент «{title}»: {content}",
        "en": "Most relevant fragment “{title}”: {content}",
    },
    "needs_review": {
        "ru": "Требует проверки: {issues}",
        "en": "Needs review: {issues}",
    },
    "missing_audit_code": {
        "ru": "В запросе не указан код проверки (AUD-...).",
        "en": "The request does not specify an audit code (AUD-...).",
    },
    "audit_not_found": {
        "ru": "Проверка {code} не найдена.",
        "en": "Audit {code} was not found.",
    },
    "no_draft_citations": {
        "ru": "В черновике нет ссылок на источники",
        "en": "The draft has no source citations",
    },
    "invalid_ids": {
        "ru": "Несуществующие ID: {ids}",
        "en": "Unknown IDs: {ids}",
    },
    "invalid_sources": {
        "ru": "Несуществующие источники: {ids}",
        "en": "Unknown sources: {ids}",
    },
    "causal_missing": {
        "ru": "Причинный вывод не подтверждён: не хватает {missing}.",
        "en": "The causal conclusion is not confirmed: missing {missing}.",
    },
    "yes": {"ru": "да", "en": "yes"},
    "no": {"ru": "нет", "en": "no"},
    "present_table_title": {
        "ru": "Найдено строк: {count}.",
        "en": "Rows found: {count}.",
    },
    "present_table_more": {
        "ru": "…и ещё {count}.",
        "en": "…and {count} more.",
    },
    "present_empty": {
        "ru": "По заданным условиям ничего не найдено.",
        "en": "No rows match the given conditions.",
    },
    "present_no_answer": {
        "ru": "Не удалось получить ответ.",
        "en": "Could not get an answer.",
    },
    "chart_ready": {
        "ru": "Диаграмма построена по данным предыдущего ответа.",
        "en": "The chart was built from the previous answer data.",
    },
    "chart_ready_current": {
        "ru": "Диаграмма построена по результату запроса.",
        "en": "The chart was built from the query result.",
    },
    "chart_no_previous": {
        "ru": "Нет предыдущего аналитического результата для визуализации. "
        "Сначала задайте вопрос с числами, например: «Сколько проверок по "
        "статусам за 2026 год?».",
        "en": "There is no previous analytics result to visualize. Ask a "
        "numeric question first, e.g. “How many audits by status in 2026?”.",
    },
    "chart_no_data": {
        "ru": "В предыдущих данных нет строк для построения диаграммы.",
        "en": "The previous result has no rows to build a chart.",
    },
    "chart_no_metric": {
        "ru": "В предыдущих данных нет числовой метрики и категории, "
        "по которым можно построить диаграмму.",
        "en": "The previous result has no numeric metric and category "
        "suitable for a chart.",
    },
    "chart_failed": {
        "ru": "Не удалось построить диаграмму: модель не вернула корректные "
        "данные, которых нет в предыдущем ответе.",
        "en": "Could not build the chart: the model returned no data "
        "grounded in the previous answer.",
    },
    "trace_chart": {"ru": "Диаграмма", "en": "Chart"},
    "trace_chart_detail": {
        "ru": "Тип: {kind}, точек: {points}.",
        "en": "Type: {kind}, points: {points}.",
    },
    "chart_bar": {"ru": "столбчатая", "en": "bar"},
    "chart_line": {"ru": "линейная", "en": "line"},
    "chart_pie": {"ru": "круговая", "en": "pie"},
    "trace_acl": {"ru": "Сообщение агента", "en": "Agent message"},
    "trace_route": {"ru": "Выбранный маршрут", "en": "Selected route"},
    "trace_followup": {"ru": "Уточнение вопроса", "en": "Follow-up resolution"},
    "trace_followup_reason": {"ru": "Причина", "en": "Reason"},
    "trace_smalltalk_greeting": {"ru": "приветствие", "en": "greeting"},
    "trace_smalltalk_capabilities": {"ru": "возможности ассистента", "en": "assistant capabilities"},
    "trace_smalltalk_thanks": {"ru": "благодарность", "en": "thanks"},
    "trace_memory": {"ru": "Профиль аудитора", "en": "Auditor profile"},
    "trace_guard": {"ru": "Проверка запроса", "en": "Request check"},
    "trace_sql": {"ru": "SQL-запрос", "en": "SQL query"},
    "trace_result": {"ru": "Результат запроса", "en": "Query result"},
    "trace_retrieval": {"ru": "Поиск по базе знаний", "en": "Knowledge search"},
    "trace_citations": {"ru": "Источники", "en": "Sources"},
    "trace_report": {"ru": "Проект акта", "en": "Act draft"},
    "trace_inspector": {"ru": "Проверка Inspector", "en": "Inspector review"},
    "trace_investigation": {"ru": "Расследование", "en": "Investigation"},
    "trace_answer": {"ru": "Проверка ответа", "en": "Answer check"},
    "trace_latency": {"ru": "Время выполнения", "en": "Elapsed time"},
    "trace_performative": {"ru": "Перформатив", "en": "Performative"},
    "trace_confidence": {"ru": "Уверенность", "en": "Confidence"},
    "trace_facts": {"ru": "Фактов", "en": "Facts"},
    "trace_rows": {"ru": "Строк", "en": "Rows"},
    "trace_columns": {"ru": "Колонок", "en": "Columns"},
    "trace_chunks": {"ru": "Фрагментов", "en": "Chunks"},
    "trace_mode": {"ru": "Режим", "en": "Mode"},
    "trace_retries_short": {"ru": "Повторов", "en": "Retries"},
    "trace_verdict": {"ru": "Вердикт", "en": "Verdict"},
    "trace_iterations": {"ru": "Итераций", "en": "Iterations"},
    "trace_evidence": {"ru": "Подтверждений", "en": "Evidence"},
    "trace_found": {"ru": "Найдено", "en": "Found"},
    "trace_links": {"ru": "Ссылок", "en": "Links"},
    "verdict_ok": {"ru": "принят", "en": "accepted"},
    "verdict_rewrite": {"ru": "на доработку", "en": "needs rewrite"},
    "verdict_revise": {"ru": "на доработку", "en": "needs revision"},
    "route_analytics": {"ru": "Аналитика", "en": "Analytics"},
    "route_retrieval": {"ru": "Поиск в базе знаний", "en": "Knowledge search"},
    "route_report": {"ru": "Формирование акта", "en": "Act generation"},
    "route_investigation": {"ru": "Причинный анализ", "en": "Root-cause analysis"},
    "route_meta": {"ru": "Пояснение ответа", "en": "Answer explanation"},
    "route_memory": {"ru": "Память", "en": "Memory"},
    "route_smalltalk": {"ru": "Общение", "en": "Small talk"},
    "route_unsafe": {"ru": "Запрос отклонён", "en": "Request blocked"},
    "route_out_of_domain": {"ru": "Вне области аудита", "en": "Out of scope"},
    "agent_orchestrator": {"ru": "Оркестратор", "en": "Orchestrator"},
    "agent_memory": {"ru": "Память", "en": "Memory"},
    "agent_guard": {"ru": "Guardrails", "en": "Guardrails"},
    "agent_analytics": {"ru": "Агент аналитики", "en": "Analytics agent"},
    "agent_retrieval": {"ru": "Агент базы знаний", "en": "Knowledge agent"},
    "agent_report": {"ru": "Агент акта", "en": "Report agent"},
    "agent_investigation": {"ru": "Агент расследования", "en": "Investigation agent"},
    "agent_inspector": {"ru": "Inspector", "en": "Inspector"},
    "performative_request": {"ru": "запрос", "en": "request"},
    "performative_inform": {"ru": "ответ", "en": "inform"},
    "performative_refuse": {"ru": "отказ", "en": "refuse"},
    "performative_failure": {"ru": "ошибка", "en": "failure"},
    "trace_memory_detail": {
        "ru": "Загружено фактов: {count}.",
        "en": "Facts loaded: {count}.",
    },
    "trace_safe": {"ru": "запрос безопасен", "en": "request is safe"},
    "trace_failed_generic": {"ru": "не пройдена", "en": "failed"},
    "trace_rows_detail": {
        "ru": "Строк: {rows}, колонок: {columns}.",
        "en": "Rows: {rows}, columns: {columns}.",
    },
    "trace_retries": {
        "ru": "Повторов SQL: {count}.",
        "en": "SQL retries: {count}.",
    },
    "trace_retrieval_detail": {
        "ru": "Режим: {mode}, найдено фрагментов: {chunks}.",
        "en": "Mode: {mode}, chunks found: {chunks}.",
    },
    "trace_citations_detail": {
        "ru": "Подтверждений: {count}.",
        "en": "Citations: {count}.",
    },
    "trace_report_detail": {
        "ru": "Ссылок в черновике: {count}.",
        "en": "Citations in the draft: {count}.",
    },
    "trace_inspector_detail": {
        "ru": "Вердикт: {verdict}, итераций: {iterations}.",
        "en": "Verdict: {verdict}, iterations: {iterations}.",
    },
    "trace_investigation_detail": {
        "ru": "Раундов ACL: {rounds}, подтверждений: {evidence}.",
        "en": "ACL rounds: {rounds}, evidence: {evidence}.",
    },
    "trace_passed": {"ru": "пройдена", "en": "passed"},
    "trace_not_passed": {"ru": "не пройдена", "en": "not passed"},
    "trace_latency_detail": {"ru": "{seconds} с.", "en": "{seconds} s."},
    "trace_missing": {"ru": "Не хватает", "en": "Missing"},
    "trace_rounds": {"ru": "Раундов", "en": "Rounds"},
}


def t(lang: str | None, key: str, **kwargs: Any) -> str:
    """Возвращает сообщение на языке ``lang`` (по умолчанию — русский)."""
    entry = _TEXTS.get(key)
    if entry is None:
        return key
    template = entry["en"] if str(lang).lower() == "en" else entry["ru"]
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template
