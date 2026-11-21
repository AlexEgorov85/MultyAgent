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
