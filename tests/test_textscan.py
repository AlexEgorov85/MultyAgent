"""Текстовые сканеры без регулярных выражений."""

from __future__ import annotations

from src.textscan import (
    audit_codes,
    contains_id,
    number_tokens,
    paragraphs,
    reference_ids,
    sentences,
    strip_bracketed_numbers,
    tokens,
    words,
    years,
)


def test_tokens_split_on_punctuation():
    assert tokens("см. AUD-2025-MORTGAGE-03, затем ITM-1.") == [
        "AUD-2025-MORTGAGE-03",
        "ITM-1",
    ]


def test_audit_codes_require_full_structure():
    text = (
        "Проверка aud-2025-mortgage-03 и AUD-25-MORTGAGE-1, "
        "а также AUD-2026-MORTGAGE-04."
    )
    assert audit_codes(text) == [
        "AUD-2025-MORTGAGE-03",
        "AUD-2026-MORTGAGE-04",
    ]


def test_years_ignore_longer_numbers():
    assert years("в 2025, 25-й, 20250 и AUD-2024-IT-01") == [2025, 2024]


def test_number_tokens_keep_decimals_and_item_numbers():
    assert number_tokens("8, 7.5, 1,5 и пункт 5.1.2") == [
        "8",
        "7.5",
        "1.5",
        "5.1",
        "2",
    ]


def test_contains_id_does_not_match_inside_longer_id():
    assert contains_id("См. ACT-2025-01.", "ACT-2025-01")
    assert not contains_id("См. ACT-2025-011.", "ACT-2025-01")


def test_reference_ids_filter_by_prefix():
    text = "ITM-1, ACT-2, AUD-2025-IT-01"
    assert reference_ids(text, ("ITM", "ACT")) == ["ITM-1", "ACT-2"]
    assert reference_ids(text) == ["ITM-1", "ACT-2", "AUD-2025-IT-01"]


def test_reference_ids_skip_trailing_hyphen():
    assert reference_ids("ITM-1-", ("ITM",)) == []


def test_strip_bracketed_numbers_only_for_digits():
    assert strip_bracketed_numbers("Текст [1] и [12], но [abc].") == (
        "Текст  и , но [abc]."
    )


def test_sentences_split_after_terminal_punctuation():
    assert sentences("Первое. Второе! Третье?") == [
        "Первое.",
        "Второе!",
        "Третье?",
    ]


def test_paragraphs_split_on_blank_lines():
    assert paragraphs("Первый\nабзац.\n\nВторой\nабзац.") == [
        "Первый\nабзац.",
        "Второй\nабзац.",
    ]


def test_words_keep_cyrillic_and_digits():
    assert words("Пункт 5.1 — Проверка") == ["Пункт", "5", "1", "Проверка"]
