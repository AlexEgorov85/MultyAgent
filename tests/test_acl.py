"""Проверки спецификации agent-protocol."""

from __future__ import annotations

import json

import pytest

from src.acl import (
    ACLMessage,
    ACLRecorder,
    ACLValidationError,
    make_acl_message,
    make_reply,
    validate_acl,
)


def _request(**overrides):
    payload = {
        "performative": "request",
        "sender": "orchestrator",
        "receiver": "analytics_agent",
        "content": {"question": "Сколько проверок завершено?"},
        "conversation_id": "conv-001",
        "reply_with": "msg-0001",
    }
    payload.update(overrides)
    return payload


def test_valid_message_passes():
    message = validate_acl(_request())
    assert message.sender == "orchestrator"
    assert message.language == "ru"
    assert message.protocol == "fipa-acl"


def test_missing_required_field_rejected():
    payload = _request()
    payload.pop("conversation_id")
    with pytest.raises(ACLValidationError):
        validate_acl(payload)


def test_unknown_performative_rejected():
    with pytest.raises(ACLValidationError):
        validate_acl(_request(performative="execute"))


def test_empty_content_rejected():
    with pytest.raises(ACLValidationError):
        validate_acl(_request(content={}))


def test_blank_sender_rejected():
    with pytest.raises(ACLValidationError):
        validate_acl(_request(sender="   "))


def test_reply_correlation():
    request = make_acl_message(**_request())
    reply = make_reply(
        request,
        performative="inform",
        sender="analytics_agent",
        content={"answer": "12"},
    )
    assert reply.conversation_id == request.conversation_id
    assert reply.in_reply_to == request.reply_with
    assert reply.receiver == request.sender
    assert reply.reply_with != request.reply_with


def test_refuse_has_reason():
    message = make_acl_message(
        performative="refuse",
        sender="guardrail",
        receiver="orchestrator",
        content={"reason": "Запрос пытается изменить данные."},
        conversation_id="conv-001",
    )
    assert message.performative == "refuse"
    assert message.content["reason"]


def test_recorder_keeps_dialog_and_writes_jsonl(tmp_path):
    path = tmp_path / "acl.jsonl"
    recorder = ACLRecorder(path)
    request = recorder.record(_request())
    reply = recorder.record(
        make_reply(
            request,
            performative="inform",
            sender="analytics_agent",
            content={"answer": "12"},
        )
    )

    assert len(recorder.by_conversation("conv-001")) == 2
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    stored = [json.loads(line) for line in lines]
    assert stored[1]["in_reply_to"] == request.reply_with
    assert stored[1]["conversation_id"] == reply.conversation_id
