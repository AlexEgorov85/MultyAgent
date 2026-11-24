"""Структурированные слоты диалога.

Текстовая история полезна LLM, но год и код проверки удобно переносить
структурно. Семантические слоты (тема, тип находки, риск, статус) здесь
намеренно не извлекаются из слов: омонимия («карты» / «картина») делает
regex-угадывание ненадёжным. Их восстанавливает LLM-резолвер в тексте
вопроса, а валидирует код.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .textscan import audit_codes, years


class DialogueSlots(BaseModel):
    """Слоты, которые переносятся между репликами."""

    year: int | None = None
    theme: str | None = None
    item_type: str | None = None
    risk_level: str | None = None
    status: str | None = None
    audit_code: str | None = None


def _normalise(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def extract_slots(text: str) -> DialogueSlots:
    """Извлекает только однозначные слоты: год и код проверки.

    Тема, тип находки, риск и статус — семантические: их определяет
    LLM-резолвер по смыслу вопроса, а не совпадение стемов.
    """
    value = _normalise(text)
    slots = DialogueSlots()

    codes = audit_codes(text)
    if codes:
        slots.audit_code = codes[0]

    found_years = years(value)
    if found_years:
        slots.year = found_years[-1]

    return slots


def merge_slots(
    previous: DialogueSlots | dict[str, Any] | None,
    *questions: str,
) -> DialogueSlots:
    """Сохраняет старые слоты и обновляет их явными упоминаниями.

    Приоритет: явный слот из текущей реплики → слот, который восстановил
    LLM-резолвер → значение из прошлого хода. Резолвер сильнее прошлого
    хода, потому что он читает смысл: «а за 25-й год?» не содержит
    `20\\d{2}`, и без этого правила прошлый год молча перебил бы новый.
    """
    base = (
        previous
        if isinstance(previous, DialogueSlots)
        else DialogueSlots.model_validate(previous or {})
    )
    merged = base.model_copy(deep=True)

    current = extract_slots(questions[0]) if questions else DialogueSlots()
    resolved = (
        extract_slots(questions[-1])
        if len(questions) > 1
        else DialogueSlots()
    )

    for field_name in DialogueSlots.model_fields:
        value = getattr(current, field_name)
        if value is None:
            value = getattr(resolved, field_name)
        if value is not None:
            setattr(merged, field_name, value)

    return merged


def augment_query(query: str, source_text: str) -> str:
    """Возвращает год и код проверки, которые резолвер потерял.

    Дописываются только однозначные токены из текущей реплики
    пользователя. Переносить их из прошлых ходов нельзя: «за последние
    2 года» не содержит года, и подстановка прошлого года исказила бы
    вопрос. Тема/статус/риск не дописываются никогда: пользователь мог
    сменить предмет, а это решает LLM.
    """
    explicit = extract_slots(source_text)
    text = " ".join((query or "").split())
    lower = _normalise(text)
    additions: list[str] = []

    if explicit.year is not None and str(explicit.year) not in lower:
        additions.append(f"год {explicit.year}")
    if explicit.audit_code and explicit.audit_code.lower() not in lower:
        additions.append(f"проверка {explicit.audit_code}")

    if not additions:
        return text
    suffix = "Уточнение: " + ", ".join(additions) + "."
    return f"{text} {suffix}".strip()


def slots_text(slots: DialogueSlots) -> str:
    """Компактное представление слотов для промптов и логов."""
    parts = []
    for field_name in DialogueSlots.model_fields:
        value = getattr(slots, field_name)
        if value is not None:
            parts.append(f"{field_name}={value}")
    return ", ".join(parts)
