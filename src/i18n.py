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
    "trace_acl": {"ru": "ACL-сообщение", "en": "ACL message"},
    "trace_route": {"ru": "Маршрут", "en": "Route"},
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
