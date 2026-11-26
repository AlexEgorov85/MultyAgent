"""Guardrails: проверка запроса и финального ответа."""

from __future__ import annotations

import logging
import re
from typing import Any

from .schemas import GuardrailResult
from .tools.sql_guard import UnsafeSQLError, validate_readonly_sql

logger = logging.getLogger(__name__)

UNSAFE_PATTERNS = (
    r"\bудали\b",
    r"\bудалить\b",
    r"\bизмени\b",
    r"\bобнови\b",
    r"\bвставь\b",
    r"\bdrop\b",
    r"\bdelete\b",
    r"\btruncate\b",
    r"\binsert\b",
    r"\bupdate\b",
)

PII_PATTERNS = (
    r"зарплат",
    r"паспорт",
    r"снилс",
    r"инн\b",
    r"персональн",
    r"телефон",
    r"домашний адрес",
)

PROMPT_PATTERNS = (
    r"системн[а-я]+ промпт",
    r"покажи инструкц",
    r"игнорируй инструкц",
    r"reveal prompt",
)


def _matches(patterns: tuple[str, ...], text: str) -> str | None:
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return pattern
    return None


def _blocked(
    final_answer: str,
    reason: str,
    *,
    route: str | None = None,
    log_reason: str | None = None,
    conversation_id: str = "",
) -> GuardrailResult:
    """Возвращает блокирующий результат и пишет лог без текста запроса/ответа."""
    logger.warning(
        "guardrail blocked: %s (route=%s, conversation_id=%s)",
        log_reason or reason,
        route or "unknown",
        conversation_id or "unknown",
    )
    return GuardrailResult(safe=False, final_answer=final_answer, reason=reason)


def check_request(
    question: str, *, conversation_id: str = ""
) -> GuardrailResult:
    """Блокирует изменение данных, PII и попытки раскрыть промпт."""
    text = question.lower()

    if _matches(UNSAFE_PATTERNS, text):
        return _blocked(
            "",
            "Запрос пытается изменить данные. Доступны только read-only выборки.",
            route="request",
            conversation_id=conversation_id,
        )
    if _matches(PII_PATTERNS, text):
        return _blocked(
            "",
            "Запрос затрагивает персональные данные, которые недоступны ассистенту.",
            route="request",
            conversation_id=conversation_id,
        )
    if _matches(PROMPT_PATTERNS, text):
        return _blocked(
            "",
            "Запрос пытается раскрыть внутренние инструкции системы.",
            route="request",
            conversation_id=conversation_id,
        )
    return GuardrailResult(safe=True, final_answer="", reason="")


def check_final_answer(
    answer: str,
    sql: str | None = None,
    *,
    is_domain: bool = True,
    evidence: list | None = None,
    is_factual: bool = False,
    route: str | None = None,
    conversation_id: str = "",
) -> GuardrailResult:
    """Проверяет SQL и текст перед показом пользователю.

    Args:
        answer: текст ответа.
        sql: SQL, использованный для ответа (если был).
        is_domain: относится ли ответ к внутреннему аудиту.
        evidence: собранные доказательства (например, ``["sql_result"]``).
            Пустой список/``None`` при ``is_factual=True`` даёт warning, но не блокирует.
        is_factual: ответ содержит фактические утверждения, требующие evidence.
        route: маршрут запроса — только для контекста в логе.
        conversation_id: идентификатор диалога для журнала инцидента.
    """
    route_context = route or ("domain" if is_domain else "out_of_domain")

    if sql:
        try:
            validate_readonly_sql(sql)
        except UnsafeSQLError as exc:
            return _blocked(
                "Не могу показать результат: SQL не прошёл проверку безопасности.",
                str(exc),
                route=route_context,
                log_reason="SQL не прошёл проверку безопасности",
                conversation_id=conversation_id,
            )

    if _matches(PROMPT_PATTERNS, answer.lower()):
        return _blocked(
            "Не могу раскрывать внутренние инструкции системы.",
            "Ответ содержит внутренние инструкции",
            route=route_context,
            conversation_id=conversation_id,
        )

    if _matches(PII_PATTERNS, answer.lower()):
        return _blocked(
            "Не могу показать ответ: он содержит персональные данные.",
            "Ответ содержит персональные данные",
            route=route_context,
            conversation_id=conversation_id,
        )

    if not is_domain:
        return _blocked(
            "Я помогаю только по вопросам внутреннего аудита.",
            "Ответ вне домена",
            route=route_context,
            conversation_id=conversation_id,
        )

    warnings: list[str] = []
    if is_factual and not evidence:
        warnings.append("Ответ сформирован без evidence")

    return GuardrailResult(
        safe=True,
        final_answer=answer,
        reason="",
        warnings=warnings,
    )


def extract_sql(acl_response: dict[str, Any] | None) -> str | None:
    """Достаёт SQL из ACL-ответа агента, если он там есть."""
    if not acl_response:
        return None
    content = acl_response.get("content", {})
    sql = content.get("sql")
    return sql if isinstance(sql, str) else None
