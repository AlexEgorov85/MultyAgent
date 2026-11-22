"""Структурированные слоты диалога.

Текстовая история полезна LLM, но для переноса года/темы/типа находки
нужна структура. Слоты обновляются из текущего вопроса и результата
resolver, а затем добавляются в resolved_query, чтобы контекст не терялся.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

_AUDIT_CODE_RE = re.compile(r"AUD-\d{4}-[A-Z]+-\d{2}", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")

_THEME_STEMS: tuple[tuple[str, str], ...] = (
    ("потребкредит", "потребкредитование"),
    ("ипотек", "ипотека"),
    ("вклад", "вклады"),
    ("платеж", "платежи"),
    ("карт", "карты"),
)
_RISK_STEMS: tuple[tuple[str, str], ...] = (
    ("критическ", "критический"),
    ("высок", "высокий"),
    ("средн", "средний"),
    ("низк", "низкий"),
)
_ITEM_TYPES: tuple[tuple[str, str], ...] = (
    ("проблем", "проблема"),
    ("отклон", "отклонение"),
)
_STATUS_WORDS: tuple[tuple[str, str], ...] = (
    ("на согласовании", "на согласовании"),
    ("в работе", "в работе"),
    ("черновик", "черновик"),
    ("утвержд", "утверждён"),
    ("заверш", "завершена"),
    ("отмен", "отменена"),
    ("закрыт", "закрыт"),
    ("открыт", "открыт"),
)


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
    """Извлекает только явно упомянутые в тексте слоты."""
    value = _normalise(text)
    slots = DialogueSlots()

    code = _AUDIT_CODE_RE.search(text or "")
    if code:
        slots.audit_code = code.group(0).upper()

    years = _YEAR_RE.findall(value)
    if years:
        slots.year = int(years[-1])

    for stem, theme in _THEME_STEMS:
        if stem in value:
            slots.theme = theme
            break

    for stem, item_type in _ITEM_TYPES:
        if stem in value:
            slots.item_type = item_type
            break

    for stem, risk in _RISK_STEMS:
        if stem in value:
            slots.risk_level = risk
            break

    for phrase, status in _STATUS_WORDS:
        if phrase in value:
            slots.status = status
            break

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
    """Добавляет потерянные слоты в resolved_query.

    Это не заменяет нормальную переформулировку, а страхует от потери
    сущности: Analytics и benchmark видят её в тексте запроса.
    """
    text = " ".join((query or "").split())
    lower = _normalise(text)
    additions: list[str] = []

    if slots.year is not None and str(slots.year) not in lower:
        additions.append(f"год {slots.year}")
    if slots.theme and slots.theme[:4] not in lower:
        additions.append(f"тема {slots.theme}")
    if slots.item_type and slots.item_type[:7] not in lower:
        additions.append(f"тип находки {slots.item_type}")
    if slots.risk_level and slots.risk_level[:5] not in lower:
        additions.append(f"риск {slots.risk_level}")
    if slots.status and slots.status[:5] not in lower:
        additions.append(f"статус {slots.status}")
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
