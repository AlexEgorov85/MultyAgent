"""Структурированные слоты диалога."""

from __future__ import annotations

from src.dialogue_slots import (
    DialogueSlots,
    augment_query,
    extract_slots,
    merge_slots,
    slots_text,
)


def test_extract_slots_from_question():
    slots = extract_slots(
        "Сколько критических проблем по ипотеке в 2025 году "
        "по проверке AUD-2025-MORTGAGE-03?"
    )
    assert slots.year == 2025
    assert slots.theme == "ипотека"
    assert slots.item_type == "проблема"
    assert slots.risk_level == "критический"
    assert slots.audit_code == "AUD-2025-MORTGAGE-03"


def test_merge_preserves_previous_item_type():
    previous = DialogueSlots(
        year=2026,
        theme="ипотека",
        item_type="проблема",
        risk_level="высокий",
    )
    merged = merge_slots(previous, "А за 2025 год?", "Сколько отклонений в 2025?")
    assert merged.year == 2025
    assert merged.theme == "ипотека"
    assert merged.item_type == "проблема"
    assert merged.risk_level == "высокий"


def test_resolver_cannot_overwrite_explicit_current_slot():
    previous = DialogueSlots(item_type="проблема")
    merged = merge_slots(
        previous,
        "Нет, я имел в виду отклонения",
        "Сколько проблем по ипотеке?",
    )
    assert merged.item_type == "отклонение"


def test_augment_query_adds_lost_slots():
    slots = DialogueSlots(
        year=2025,
        theme="ипотека",
        item_type="проблема",
        risk_level="критический",
        audit_code="AUD-2025-MORTGAGE-03",
    )
    text = augment_query("А за 2025 год?", slots)
    assert "2025" in text
    assert "ипотека" in text
    assert "проблема" in text
    assert "критический" in text
    assert "AUD-2025-MORTGAGE-03" in text


def test_slots_text_is_compact():
    text = slots_text(DialogueSlots(year=2026, theme="карты"))
    assert "year=2026" in text
    assert "theme=карты" in text
