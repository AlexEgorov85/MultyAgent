"""Pydantic-схемы structured output."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Route = Literal["analytics", "retrieval", "report", "investigation", "out_of_domain", "unsafe"]


class RouteDecision(BaseModel):
    """Решение маршрутизатора."""

    route: Route
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class SQLPlan(BaseModel):
    """План аналитического запроса: готовый шаблон или сгенерированный SQL."""

    strategy: Literal["script", "generated"]
    template_key: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    sql: str | None = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_strategy(self) -> "SQLPlan":
        if self.strategy == "script" and not self.template_key:
            raise ValueError("Для strategy=script нужен template_key")
        if self.strategy == "generated" and not (self.sql and self.sql.strip()):
            raise ValueError("Для strategy=generated нужен sql")
        return self


class ToolCall(BaseModel):
    """Один вызов инструмента, выбранный LLM."""

    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolPlan(BaseModel):
    """Набор инструментов, запрошенных одним вызовом LLM."""

    calls: list[ToolCall] = Field(min_length=1)
    reason: str = ""


class AnswerDraft(BaseModel):
    """Ответ агента по результатам инструментов."""

    text: str = Field(min_length=1)


class RetrievalAnswer(BaseModel):
    """Ответ RAG-агента со ссылками на источники."""

    text: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)


class Critique(BaseModel):
    """Результат критика (используется в retrieval/report)."""
    verdict: Literal["ok", "rewrite"]
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    grounded: bool = True
    citations_ok: bool = True


class ReportReview(BaseModel):
    """Результат Inspector."""

    verdict: Literal["ok", "revise"]
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    citations_ok: bool = True


class ReportDraft(BaseModel):
    """Проект раздела акта."""

    text: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)


class GuardrailResult(BaseModel):
    """Результат финальной проверки."""

    safe: bool
    final_answer: str
    reason: str = ""
