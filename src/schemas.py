"""Pydantic-схемы structured output."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Route = Literal[
    "analytics",
    "retrieval",
    "report",
    "investigation",
    "memory",
    "smalltalk",
    "out_of_domain",
    "unsafe",
]

AnalyticsMode = Literal["sql", "drilldown", "multi_tool", "chart"]


class RouteDecision(BaseModel):
    """Решение маршрутизатора."""

    route: Route
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    analytics_mode: AnalyticsMode = "sql"


class ChartPoint(BaseModel):
    """Одна точка диаграммы: категория и числовое значение.

    `row_index` и `measure` — ссылка на строку результата и числовую
    колонку. По ней код берёт значение сам, поэтому подпись может быть
    человеческой («Ипотека») без риска потерять точку при сверке.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "required": ["label", "value", "row_index", "measure"],
        }
    )

    label: str = Field(min_length=1, max_length=120)
    value: float
    row_index: int | None = None
    measure: str = ""


class ChartSpec(BaseModel):
    """Спецификация диаграммы, которую выбирает LLM по готовым данным."""

    type: Literal["bar", "line", "pie"] = "bar"
    title: str = Field(min_length=1, max_length=200)
    subtitle: str = ""
    category: str = ""
    category_label: str = ""
    value_label: str = ""
    unit: str = ""
    data: list[ChartPoint] = Field(default_factory=list)

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = [
            "type",
            "title",
            "subtitle",
            "category",
            "category_label",
            "value_label",
            "unit",
            "data",
        ]
        return schema


class ResolvedQuery(BaseModel):
    """Уточняющий вопрос, переформулированный как самостоятельный."""

    question: str = Field(min_length=1)
    is_followup: bool
    reason: str


MemoryKey = Literal["focus_theme", "default_format", "signature"]


class MemoryFact(BaseModel):
    """Одно предпочтение аудитора для долгосрочной памяти."""

    key: MemoryKey
    value: str = Field(min_length=1, max_length=200)


class MemoryUpdate(BaseModel):
    """Извлечённые предпочтения и ключи памяти, которые нужно забыть."""

    facts: list[MemoryFact] = Field(default_factory=list)
    forget: list[MemoryKey] = Field(default_factory=list)
    reason: str = ""

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = ["facts", "forget", "reason"]
        return schema


class SQLPlan(BaseModel):
    """План аналитического запроса: готовый шаблон или сгенерированный SQL."""

    strategy: Literal["script", "generated"]
    template_key: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    sql: str = ""
    reason: str = Field(min_length=1)

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = [
            "strategy",
            "template_key",
            "parameters",
            "sql",
            "reason",
        ]
        return schema


class ToolCall(BaseModel):
    """Один вызов инструмента, выбранный LLM."""

    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolPlan(BaseModel):
    """Набор инструментов, запрошенных одним вызовом LLM."""

    calls: list[ToolCall] = Field(min_length=1)
    reason: str = ""


class AnswerDraft(BaseModel):
    """Ответ агента по результатам инструментов.

    `numbers_used` — все числа, которые модель использовала в тексте,
    включая записанные словами. Код сверяет их со строками результата:
    недекларированное число или число вне таблицы отклоняет ответ.
    """

    text: str = Field(min_length=1)
    numbers_used: list[float] = Field(default_factory=list)

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = ["text", "numbers_used"]
        return schema


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


class InvestigationPlan(BaseModel):
    """План расследования: подвопросы и обязательные доказательства."""

    analytics_question: str = Field(min_length=1)
    retrieval_question: str = Field(min_length=1)
    required_evidence: list[str] = Field(
        default_factory=lambda: ["sql_result", "item"]
    )
    reason: str = ""


class InvestigationAnswer(BaseModel):
    """Итог расследования с явным признаком причинного утверждения."""

    text: str = Field(min_length=1)
    causal_claim: bool = False


class GuardrailResult(BaseModel):
    """Результат финальной проверки."""

    safe: bool
    final_answer: str
    reason: str = ""
    warnings: list[str] = Field(default_factory=list)
