"""Долгосрочная память аудитора (спецификация conversation-memory)."""

from __future__ import annotations

from typing import Mapping

from .. import db_runtime
from ..semantic.catalog import THEMES, find_theme

ALLOWED_KEYS = {"focus_theme", "default_format", "signature"}

DEFAULT_VALUES = {
    "default_format": "подробный",
}


class MemoryError(ValueError):
    """Некорректный ключ или значение памяти."""


def load_stored(server, auditor_id: str) -> dict[str, str]:
    """Читает только сохранённые факты, без значений по умолчанию."""
    if not auditor_id:
        return {}
    with db_runtime.connect(server, role=db_runtime.APP_ROLE) as conn:
        rows = conn.execute(
            "SELECT memory_key, memory_value FROM audit.auditor_memory "
            "WHERE auditor_id = %s ORDER BY memory_key",
            (auditor_id,),
        ).fetchall()
    return {key: value for key, value in rows}


def load_profile(server, auditor_id: str) -> dict[str, str]:
    """Читает профиль аудитора; при отсутствии возвращает значения по умолчанию."""
    profile = dict(DEFAULT_VALUES)
    profile.update(load_stored(server, auditor_id))
    return profile


def save_fact(server, auditor_id: str, key: str, value: str) -> None:
    """Сохраняет факт профиля; писать можно только в auditor_memory."""
    if not auditor_id:
        raise MemoryError("Не задан auditor_id")
    if key not in ALLOWED_KEYS:
        raise MemoryError(f"Недопустимый ключ памяти: {key}")
    if not value.strip():
        raise MemoryError("Значение памяти не может быть пустым")

    with db_runtime.connect(server, role=db_runtime.APP_ROLE) as conn:
        conn.execute(
            "INSERT INTO audit.auditor_memory "
            "(auditor_id, memory_key, memory_value, updated_at) "
            "VALUES (%s, %s, %s, now()) "
            "ON CONFLICT (auditor_id, memory_key) DO UPDATE "
            "SET memory_value = EXCLUDED.memory_value, updated_at = now()",
            (auditor_id, key, value.strip()),
        )


def delete_fact(server, auditor_id: str, key: str) -> None:
    """Удаляет один факт профиля («забудь формат»)."""
    if not auditor_id:
        raise MemoryError("Не задан auditor_id")
    if key not in ALLOWED_KEYS:
        raise MemoryError(f"Недопустимый ключ памяти: {key}")
    with db_runtime.connect(server, role=db_runtime.APP_ROLE) as conn:
        conn.execute(
            "DELETE FROM audit.auditor_memory "
            "WHERE auditor_id = %s AND memory_key = %s",
            (auditor_id, key),
        )


def clear_profile(server, auditor_id: str) -> None:
    """Сбрасывает весь профиль аудитора («забудь всё», кнопка в UI)."""
    if not auditor_id:
        raise MemoryError("Не задан auditor_id")
    with db_runtime.connect(server, role=db_runtime.APP_ROLE) as conn:
        conn.execute(
            "DELETE FROM audit.auditor_memory WHERE auditor_id = %s",
            (auditor_id,),
        )


def normalize_fact(
    key: str, value: str, themes: tuple[str, ...] | list[str] = ()
) -> str | None:
    """Приводит значение к каноническому виду; None — значение не распознано.

    LLM извлекает факты свободно, но в базу попадают только допустимые
    значения: формат — «краткий»/«подробный», тема — из списка тем базы.
    """
    if key not in ALLOWED_KEYS:
        return None
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return None
    if key == "default_format":
        lower = text.lower()
        if any(stem in lower for stem in ("кратк", "коротк", "сжат", "brief", "short")):
            return "краткий"
        if any(
            stem in lower
            for stem in ("подробн", "полн", "развёрнут", "развернут", "detailed", "full")
        ):
            return "подробный"
        return None
    if key == "focus_theme":
        lower = text.lower()
        candidates = tuple(themes)
        for theme in candidates:
            if lower == str(theme).lower():
                return str(theme)
        return find_theme(text, candidates)
    return text[:200]


def profile_text(profile: Mapping[str, str]) -> str:
    """Форматирует профиль для промпта и ответа."""
    parts = []
    if profile.get("focus_theme"):
        parts.append(f"Тема: {profile['focus_theme']}")
    if profile.get("default_format"):
        parts.append(f"Формат: {profile['default_format']}")
    if profile.get("signature"):
        parts.append(f"Подпись: {profile['signature']}")
    return "; ".join(parts)


def infer_memory(question: str) -> dict[str, str]:
    """Аварийный детерминированный fallback без LLM.

    Основной путь извлечения — ``LLMClient.extract_memory`` (маршрут
    ``memory`` выбирает router). Этот парсер используется только когда
    LLM-извлечение недоступно, поэтому намеренно консервативен.
    """
    text = question.lower()
    triggers = (
        "запомни",
        "я проверяю",
        "предпочитаю",
        "акт нужен",
        "нужен кратк",
        "нужен подробн",
        "в кратком формате",
        "в подробном формате",
    )
    if not any(trigger in text for trigger in triggers):
        return {}

    facts: dict[str, str] = {}
    theme = find_theme(text, THEMES)
    if theme:
        facts["focus_theme"] = theme
    if "кратк" in text:
        facts["default_format"] = "краткий"
    elif "подробн" in text:
        facts["default_format"] = "подробный"
    return facts
