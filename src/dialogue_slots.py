"""Структурированные слоты диалога.

Текстовая история полезна LLM, но год и код проверки удобно переносить
структурно. Семантические слоты (тема, тип находки, риск, статус) здесь
намеренно не извлекаются из слов: омонимия («карты» / «картина») делает
regex-угадывание ненадёжным. Их восстанавливает LLM-резолвер в тексте
вопроса, а валидирует код.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

_AUDIT_CODE_RE = re.compile(r"AUD-\d{4}-[A-Z]+-\d{2}", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


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

    code = _AUDIT_CODE_RE.search(text or "")
    if code:
        slots.audit_code = code.group(0).upper()

    years = _YEAR_RE.findall(value)
    if years:
        slots.year = int(years[-1])

    return slots


def merge_slots(
    previous: DialogueSlots | dict[str, Any] | None,
    *questions: str,
) -> DialogueSlots:
    """Сохраняет старые слоты и обновляет их явными упоминаниями.

    Приоритет: явное упоминание в новом тексте → предыдущий слот →
    слот, который восстановила LLM. Поэтому resolver не может «потерять»
    уже известный item_type или заменить его догадкой.
    """
    base = (
        previous
        if isinstance(previous, DialogueSlots)
        else DialogueSlots.model_validate(previous or {})
    )
    merged = base.model_copy(deep=True)

    # Последний текст — результат resolver: он может только заполнить
    # пропуски, но не перезаписать явный текущий или предыдущий слот.
    current_texts = list(questions[:-1]) if len(questions) > 1 else list(questions)
    for text in current_texts:
        extracted = extract_slots(text)
        for field_name in DialogueSlots.model_fields:
            value = getattr(extracted, field_name)
            if value is not None:
                setattr(merged, field_name, value)

    if len(questions) > 1:
        resolved = extract_slots(questions[-1])
        for field_name in DialogueSlots.model_fields:
            if getattr(merged, field_name) is None:
                value = getattr(resolved, field_name)
                if value is not None:
                    setattr(merged, field_name, value)

    return merged


def augment_query(query: str, slots: DialogueSlots) -> str:
    """Добавляет потерянные однозначные слоты: год и код проверки.

    Тема/статус/риск не дописываются: если резолвер их потерял, добавлять
    их по сохранённому значению опасно (пользователь мог сменить тему).
    """
    text = " ".join((query or "").split())
    lower = _normalise(text)
    additions: list[str] = []

    if slots.year is not None and str(slots.year) not in lower:
        additions.append(f"год {slots.year}")
    if slots.audit_code and slots.audit_code.lower() not in lower:
        additions.append(f"проверка {slots.audit_code}")

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
