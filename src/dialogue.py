"""Диалоговый контекст: история, уточняющие вопросы и перенос сущностей.

Модуль намеренно не зависит от LangGraph и LLM: его функции легко тестировать
отдельно. Основной граф использует их, чтобы:

* собрать компактный контекст последних реплик;
* понять, является ли вопрос уточнением («а за 2025?», «почему?»);
* перенести код проверки из предыдущего ответа, если модель не сделала это
  сама.
"""

from __future__ import annotations

import re
from typing import Any

MAX_CONTEXT_MESSAGES = 8
MAX_CONTEXT_CHARS = 4000
MAX_MESSAGE_CHARS = 700

_AUDIT_CODE_RE = re.compile(r"AUD-\d{4}-[A-Z]+-\d{2}", re.IGNORECASE)

_SMALLTALK_RE = re.compile(
    r"^(привет|здравствуй|добрый (день|вечер)|доброе утро|хай|hello|hi|hey|"
    r"спасибо|благодарю|thanks|thank you|что ты умеешь|что ты можешь|"
    r"чем ты можешь помочь|твои возможности|кто ты|расскажи о себе|"
    r"what can you do|who are you)\b",
    re.IGNORECASE,
)

_FOLLOWUP_START_RE = re.compile(
    r"^(а|и|но|тогда|ещё|еще|теперь|также|по|за|с|без|для|почему|"
    r"а если|а сколько|а какие|а покажи|а что)\b",
    re.IGNORECASE,
)

_FOLLOWUP_ANY_RE = re.compile(
    r"\b(этот|эта|эти|тот|та|те|там|тогда|ним|нему|ней|них|"
    r"этому|этой|той|их)\b",
    re.IGNORECASE,
)

_FOLLOWUP_PERIOD_RE = re.compile(
    r"^(в|за|с|до|после)\s+(20\d{2}|прошл\w*|этом|этого|прошлом)",
    re.IGNORECASE,
)

_DOMAIN_RE = re.compile(
    r"(проверк|аудит|акт|пункт|отклонен|риск|ипотек|вклад|платеж|"
    r"карт|кредит|просроч|доля|динамик|год|20\d{2}|aud-)",
    re.IGNORECASE,
)


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
    for message in messages or []:
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
    for message in history:
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

    history = history[-max_messages:]
    english = str(language).lower() == "en"
    user_label = "User" if english else "Пользователь"
    assistant_label = "Assistant" if english else "Ассистент"

    lines: list[str] = []
    used = 0
    for item in history:
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


def is_followup(question: str, has_history: bool) -> bool:
    """Похож ли вопрос на уточнение предыдущей реплики."""
    if not has_history:
        return False
    text = " ".join((question or "").split()).strip(" !?.,…")
    if not text:
        return False
    if _SMALLTALK_RE.match(text):
        return False
    if _FOLLOWUP_START_RE.match(text) or _FOLLOWUP_PERIOD_RE.match(text):
        return True
    if _FOLLOWUP_ANY_RE.search(text):
        return True
    if not _DOMAIN_RE.search(text) and len(text) <= 60:
        return True
    return False


def last_audit_code(text: str) -> str:
    """Последний AUD-код в тексте — для переноса контекста акта/проверки."""
    matches = _AUDIT_CODE_RE.findall(text or "")
    return matches[-1].upper() if matches else ""
