"""Долгосрочная память аудитора (спецификация conversation-memory)."""

from __future__ import annotations

from typing import Mapping

from .. import db_runtime

ALLOWED_KEYS = {"focus_theme", "default_format", "signature"}

DEFAULT_VALUES = {
    "default_format": "подробный",
}


class MemoryError(ValueError):
    """Некорректный ключ или значение памяти."""


def load_profile(server, auditor_id: str) -> dict[str, str]:
    """Читает профиль аудитора; при отсутствии возвращает значения по умолчанию."""
    if not auditor_id:
        return dict(DEFAULT_VALUES)
    with db_runtime.connect(server, role=db_runtime.APP_ROLE) as conn:
        rows = conn.execute(
            "SELECT memory_key, memory_value FROM audit.auditor_memory "
            "WHERE auditor_id = %s ORDER BY memory_key",
            (auditor_id,),
        ).fetchall()
    profile = dict(DEFAULT_VALUES)
    profile.update({key: value for key, value in rows})
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
    """Извлекает простые предпочтения, только если пользователь просит запомнить."""
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
    for theme, stem in (
        ("ипотека", "ипотек"),
        ("потребкредитование", "потребкредит"),
        ("платежи", "платеж"),
        ("карты", "карт"),
        ("вклады", "вклад"),
    ):
        if stem in text:
            facts["focus_theme"] = theme
            break
    if "кратк" in text:
        facts["default_format"] = "краткий"
    elif "подробн" in text:
        facts["default_format"] = "подробный"
    return facts
