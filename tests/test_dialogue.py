"""Юнит-тесты диалогового контекста."""

from __future__ import annotations

from src.dialogue import (
    build_dialogue_context,
    is_followup,
    last_audit_code,
    normalize_client_history,
)


def test_context_excludes_current_question_and_formats_roles():
    messages = [
        {"role": "user", "content": "Сколько проверок по картам в 2026 году?"},
        {"role": "assistant", "content": "Завершённых проверок: 7."},
        {"role": "user", "content": "А за 2025 год?"},
    ]

    context = build_dialogue_context(
        messages,
        [],
        "А за 2025 год?",
        language="ru",
    )

    assert "Пользователь: Сколько проверок по картам в 2026 году?" in context
    assert "Ассистент: Завершённых проверок: 7." in context
    assert "А за 2025 год?" not in context


def test_client_history_used_when_server_thread_is_new():
    history = normalize_client_history(
        [
            {"role": "user", "text": "Сколько проверок по вкладам?"},
            {"role": "assistant", "text": "Всего: 3."},
        ]
    )

    context = build_dialogue_context(
        [{"role": "user", "content": "А за 2025 год?"}],
        history,
        "А за 2025 год?",
        language="ru",
    )

    assert "по вкладам" in context
    assert "Всего: 3." in context


def test_long_context_keeps_conversation_anchor():
    messages = [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"message-{index}",
        }
        for index in range(20)
    ]

    context = build_dialogue_context(
        messages,
        [],
        "message-19",
        max_messages=6,
    )

    assert "message-0" in context
    assert "message-1" in context
    assert "message-18" in context
    assert "…" in context


def test_followup_detection():
    assert is_followup("А за 2025 год?", has_history=True)
    assert is_followup("Почему?", has_history=True)
    assert is_followup("А по картам?", has_history=True)
    assert is_followup("В 2025 году", has_history=True)
    assert is_followup("Покажи их", has_history=True)
    assert is_followup("Ипотека", has_history=True)
    assert not is_followup("Сколько проверок по картам за 2026 год?", has_history=True)
    assert not is_followup("Сколько проверок?", has_history=True)
    assert not is_followup("Спасибо!", has_history=True)
    assert not is_followup("А за 2025 год?", has_history=False)


def test_last_audit_code():
    text = "Сначала AUD-2026-MORTGAGE-01, затем AUD-2026-DEPOSITS-88."
    assert last_audit_code(text) == "AUD-2026-DEPOSITS-88"
    assert last_audit_code("нет кода") == ""
