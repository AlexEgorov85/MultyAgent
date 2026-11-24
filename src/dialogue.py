"""Диалоговый контекст: история, уточняющие вопросы и перенос сущностей.

Модуль намеренно не зависит от LangGraph и LLM: его функции легко тестировать
отдельно. Основной граф использует их, чтобы:

* собрать компактный контекст последних реплик;
* перенести код проверки из предыдущего ответа, если модель не сделала это
  сама.

Является ли вопрос уточнением, решает LLM-резолвер: код больше не
угадывает это по словам «а», «почему», «эти».
"""

from __future__ import annotations

import re
from typing import Any

MAX_CONTEXT_MESSAGES = 12
MAX_CONTEXT_CHARS = 6000
MAX_MESSAGE_CHARS = 900

_AUDIT_CODE_RE = re.compile(r"AUD-\d{4}-[A-Z]+-\d{2}", re.IGNORECASE)


def content_text(content: Any) -> str:
    """Достаёт текст из строки или списка content-блоков LangChain."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") in ("text", "text_delta"):
                parts.append(str(item.get("text", "")))
        return " ".join(part for part in parts if part).strip()
    return "" if content is None else str(content)


def _normalize(role: Any, content: Any) -> dict[str, str] | None:
    value = str(role or "").strip().lower()
    if value in ("user", "human"):
        normalized = "user"
    elif value in ("assistant", "ai"):
        normalized = "assistant"
    else:
        return None
    text = content_text(content).strip()
    return {"role": normalized, "text": text} if text else None


def normalize_messages(messages: Any) -> list[dict[str, str]]:
    """Приводит сообщения LangGraph/LangChain к ``{role, text}``."""
    result: list[dict[str, str]] = []
    for message in (messages or [])[-32:]:
        if isinstance(message, dict):
            item = _normalize(
                message.get("role") or message.get("type"),
                message.get("content", ""),
            )
        else:
            item = _normalize(
                getattr(message, "type", ""),
                getattr(message, "content", ""),
            )
        if item:
            result.append(item)
    return result


def normalize_client_history(history: Any) -> list[dict[str, str]]:
    """Нормализует историю, которую UI присылает на случай потери треда."""
    result: list[dict[str, str]] = []
    if not isinstance(history, list):
        return result
    for message in history[-32:]:
        if not isinstance(message, dict):
            continue
        item = _normalize(
            message.get("role"),
            message.get("text") if "text" in message else message.get("content", ""),
        )
        if item:
            result.append(item)
    return result


def _trim(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def build_dialogue_context(
    messages: Any,
    client_history: Any,
    current_question: str,
    *,
    language: str = "ru",
    max_messages: int = MAX_CONTEXT_MESSAGES,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> str:
    """Собирает предыдущие реплики без текущего вопроса.

    Серверная история LangGraph — основной источник. Если тред потерян
    (например, backend перезапустился), используется история из UI.
    """
    server_history = normalize_messages(messages)
    current = (current_question or "").strip()
    if (
        server_history
        and server_history[-1]["role"] == "user"
        and server_history[-1]["text"].strip() == current
    ):
        server_history = server_history[:-1]

    history = server_history or normalize_client_history(client_history)
    if not history:
        return ""

    truncated = len(history) > max_messages
    if truncated:
        # Держим начало разговора как якорь темы и последние реплики.
        history = history[:2] + history[-(max_messages - 2) :]
    english = str(language).lower() == "en"
    user_label = "User" if english else "Пользователь"
    assistant_label = "Assistant" if english else "Ассистент"

    lines: list[str] = []
    used = 0
    for index, item in enumerate(history):
        if truncated and index == 2:
            lines.append("…")
        text = _trim(item["text"], MAX_MESSAGE_CHARS)
        label = user_label if item["role"] == "user" else assistant_label
        line = f"{label}: {text}"
        if used + len(line) > max_chars:
            remaining = max_chars - used
            if remaining > 40:
                lines.append(line[: remaining - 1].rstrip() + "…")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def last_audit_code(text: str) -> str:
    """Последний AUD-код в тексте — для переноса контекста акта/проверки."""
    matches = _AUDIT_CODE_RE.findall(text or "")
    return matches[-1].upper() if matches else ""
