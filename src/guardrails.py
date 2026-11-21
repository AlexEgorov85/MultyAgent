"""Guardrails: проверка запроса и финального ответа."""

from __future__ import annotations

import re
from typing import Any

from .schemas import GuardrailResult
from .tools.sql_guard import UnsafeSQLError, validate_readonly_sql

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

DOMAIN_HINTS = (
    "аудит",
    "проверк",
    "акт",
    "пункт",
    "отклонен",
    "ипотек",
    "вклад",
    "платеж",
    "карт",
    "кредит",
)


def _matches(patterns: tuple[str, ...], text: str) -> str | None:
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return pattern
    return None


def check_request(question: str) -> GuardrailResult:
    """Блокирует изменение данных, PII и попытки раскрыть промпт."""
    text = question.lower()

    if _matches(UNSAFE_PATTERNS, text):
        return GuardrailResult(
            safe=False,
            final_answer="",
            reason="Запрос пытается изменить данные. Доступны только read-only выборки.",
        )
    if _matches(PII_PATTERNS, text):
        return GuardrailResult(
            safe=False,
            final_answer="",
            reason="Запрос затрагивает персональные данные, которые недоступны ассистенту.",
        )
    if _matches(PROMPT_PATTERNS, text):
        return GuardrailResult(
            safe=False,
            final_answer="",
            reason="Запрос пытается раскрыть внутренние инструкции системы.",
        )
    return GuardrailResult(safe=True, final_answer="", reason="")


def check_final_answer(
    answer: str,
    sql: str | None = None,
    *,
    is_domain: bool = True,
) -> GuardrailResult:
    """Проверяет SQL и текст перед показом пользователю."""
    if sql:
        try:
            validate_readonly_sql(sql)
        except UnsafeSQLError as exc:
            return GuardrailResult(
                safe=False,
                final_answer="Не могу показать результат: SQL не прошёл проверку безопасности.",
                reason=str(exc),
            )

    if _matches(PROMPT_PATTERNS, answer.lower()):
        return GuardrailResult(
            safe=False,
            final_answer="Не могу раскрывать внутренние инструкции системы.",
            reason="Ответ содержит внутренние инструкции",
        )

    if not is_domain:
        return GuardrailResult(
            safe=False,
            final_answer="Я помогаю только по вопросам внутреннего аудита.",
            reason="Ответ вне домена",
        )

    return GuardrailResult(safe=True, final_answer=answer, reason="")


def extract_sql(acl_response: dict[str, Any] | None) -> str | None:
    if not acl_response:
        return None
    content = acl_response.get("content", {})
    sql = content.get("sql")
    return sql if isinstance(sql, str) else None
