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


def test_resolved_year_overrides_previous_without_regex_match():
    """«25-й год» не ловится `20\\\\d{2}`, но резолвер понимает смысл."""
    previous = DialogueSlots(year=2026, theme="ипотека")
    merged = merge_slots(
        previous,
        "А за 25-й год?",
        "Сколько отклонений по ипотеке за 2025 год?",
    )
    assert merged.year == 2025


def test_augment_query_adds_only_explicit_year_and_audit_code():
    text = augment_query(
        "Что там по этому вопросу?",
        "Критические проблемы по ипотеке в 2025 году "
        "по проверке AUD-2025-MORTGAGE-03?",
    )
    assert "2025" in text
    assert "AUD-2025-MORTGAGE-03" in text
    # Семантические слоты не дописываются: пользователь мог сменить тему.
    assert "ипотека" not in text
    assert "проблема" not in text
    assert "критический" not in text


def test_augment_query_does_not_restore_previous_year():
    """Прошлый год нельзя дописывать, если в текущей реплике его нет."""
    text = augment_query(
        "Сколько закрытых проверок по картам за последние 2 года?",
        "А по картам за последние 2 года?",
    )
    assert "Уточнение" not in text
    assert "2026" not in text


def test_slots_text_is_compact():
    text = slots_text(DialogueSlots(year=2026, theme="карты"))
    assert "year=2026" in text
    assert "theme=карты" in text
