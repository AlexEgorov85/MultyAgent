"""Структурированные слоты диалога."""

from __future__ import annotations

from src.dialogue_slots import (
    DialogueSlots,
    augment_query,
    extract_slots,
    merge_slots,
    slots_text,
)


def test_extract_slots_only_unambiguous_entities():
    slots = extract_slots(
        "Сколько критических проблем по ипотеке в 2025 году "
        "по проверке AUD-2025-MORTGAGE-03?"
    )
    assert slots.year == 2025
    assert slots.audit_code == "AUD-2025-MORTGAGE-03"
    # Тема, тип находки и риск — семантика, её определяет LLM-резолвер.
    assert slots.theme is None
    assert slots.item_type is None
    assert slots.risk_level is None
    assert slots.status is None


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


def test_semantic_slots_are_not_guessed_from_words():
    slots = extract_slots("Нет, я имел в виду отклонения по ипотеке")
    assert slots.item_type is None
    assert slots.theme is None


def test_merge_keeps_known_semantic_slots_from_state():
    previous = DialogueSlots(item_type="проблема", theme="ипотека")
    merged = merge_slots(previous, "А за 2025 год?")
    assert merged.item_type == "проблема"
    assert merged.theme == "ипотека"
    assert merged.year == 2025


def test_augment_query_adds_only_year_and_audit_code():
    slots = DialogueSlots(
        year=2025,
        theme="ипотека",
        item_type="проблема",
        risk_level="критический",
        audit_code="AUD-2025-MORTGAGE-03",
    )
    text = augment_query("Что там по этому вопросу?", slots)
    assert "2025" in text
    assert "AUD-2025-MORTGAGE-03" in text
    # Семантические слоты не дописываются: пользователь мог сменить тему.
    assert "ипотека" not in text
    assert "проблема" not in text
    assert "критический" not in text


def test_slots_text_is_compact():
    text = slots_text(DialogueSlots(year=2026, theme="карты"))
    assert "year=2026" in text
    assert "theme=карты" in text
