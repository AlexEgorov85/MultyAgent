"""Морфологически аккуратный матчер тем: без ложных срабатываний."""

from __future__ import annotations

from src.semantic.catalog import theme_in_text


def test_bank_cards_are_recognized():
    for text in (
        "проверки по картам",
        "банковские карты",
        "операции по карте",
        "выпуск кредитных карт",
    ):
        assert theme_in_text("карты", text)


def test_card_homonyms_are_not_theme():
    for text in (
        "картина отклонений",
        "карточка проверки",
        "карта проверок",
        "карта рисков",
        "дорожная карта устранения",
        "карты местности",
        "игральные карты",
    ):
        assert not theme_in_text("карты", text), text


def test_theme_inflections_and_adjectives():
    assert theme_in_text("ипотека", "ипотечных кредитов")
    assert theme_in_text("ипотека", "по ипотеке")
    assert theme_in_text("потребкредитование", "потребительских кредитов")
    assert theme_in_text("платежи", "платёжные поручения")
    assert theme_in_text("вклады", "данные по вкладчикам")
    assert not theme_in_text("вклады", "открой вкладку настроек")
