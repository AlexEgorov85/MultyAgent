"""FIPA-ACL-конверт и журнал межагентного обмена (спецификация agent-protocol)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Performative = Literal["request", "inform", "refuse", "failure", "propose", "agree"]


class ACLValidationError(ValueError):
    """Сообщение не соответствует ACL-контракту."""


def new_message_id() -> str:
    """Короткий уникальный идентификатор сообщения."""
    return f"msg-{uuid.uuid4().hex[:12]}"


class ACLMessage(BaseModel):
    """Сообщение между агентами в формате, близком к FIPA-ACL."""

    performative: Performative
    sender: str = Field(min_length=1)
    receiver: str = Field(min_length=1)
    content: dict[str, Any] = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    reply_with: str = Field(min_length=1)
    in_reply_to: str | None = None
    protocol: Literal["fipa-acl"] = "fipa-acl"
    ontology: str = "audit-assistant"
    language: Literal["ru"] = "ru"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("sender", "receiver", "conversation_id", "reply_with")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Поле не может быть пустым")
        return value


def make_acl_message(
    *,
    performative: Performative,
    sender: str,
    receiver: str,
    content: dict[str, Any],
    conversation_id: str,
    reply_with: str | None = None,
    in_reply_to: str | None = None,
) -> ACLMessage:
    """Создаёт и валидирует ACL-сообщение."""
    return ACLMessage(
        performative=performative,
        sender=sender,
        receiver=receiver,
        content=content,
        conversation_id=conversation_id,
        reply_with=reply_with or new_message_id(),
        in_reply_to=in_reply_to,
    )


def make_reply(
    request: ACLMessage,
    *,
    performative: Performative,
    sender: str,
    content: dict[str, Any],
) -> ACLMessage:
    """Строит ответ, сохраняя conversation_id и связывая его с запросом."""
    return make_acl_message(
        performative=performative,
        sender=sender,
        receiver=request.sender,
        content=content,
        conversation_id=request.conversation_id,
        in_reply_to=request.reply_with,
    )


def validate_acl(data: ACLMessage | dict[str, Any]) -> ACLMessage:
    """Валидирует сообщение из модели или словаря."""
    if isinstance(data, ACLMessage):
        return data
    try:
        return ACLMessage.model_validate(data)
    except Exception as exc:  # pydantic.ValidationError и вложенные ошибки
        raise ACLValidationError(str(exc)) from exc


class ACLRecorder:
    """Хранит и, опционально, пишет ACL-обмен в JSONL."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.messages: list[ACLMessage] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def record(self, message: ACLMessage | dict[str, Any]) -> ACLMessage:
        validated = validate_acl(message)
        self.messages.append(validated)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        validated.model_dump(), ensure_ascii=False
                    )
                    + "\n"
                )
        return validated

    def by_conversation(self, conversation_id: str) -> list[ACLMessage]:
        return [
            message
            for message in self.messages
            if message.conversation_id == conversation_id
        ]

    def to_dicts(self) -> list[dict[str, Any]]:
        return [message.model_dump() for message in self.messages]
