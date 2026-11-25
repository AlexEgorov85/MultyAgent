"""Pydantic-схемы structured output."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class ToolArguments(BaseModel):
    """Аргументы инструментов в плоской схеме.

    Свободный `dict` в strict JSON модель заполняла пустым объектом, из-за
    чего терялись `item_type`, `query` и другие фильтры. Плоская схема с
    известными полями заполняется предсказуемо.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "required": [
                "audit_code",
                "query",
                "item_type",
                "risk_level",
                "status",
                "pocket_id",
                "sql",
                "limit",
                "max_rows",
            ]
        }
    )

    audit_code: str = ""
    query: str = ""
    item_type: str = ""
    risk_level: str = ""
    status: str = ""
    pocket_id: str = ""
    sql: str = ""
    limit: int = 0
    max_rows: int = 0

    def as_call_arguments(self) -> dict[str, Any]:
        """Только заполненные аргументы: пустые строки и нули не передаём."""
        result: dict[str, Any] = {}
        for name, value in self.model_dump().items():
            if isinstance(value, str) and not value.strip():
                continue
            if name in ("limit", "max_rows") and not value:
                continue
            result[name] = value
        return result


class Clarification(BaseModel):
    """Уточняющий вопрос вместо догадки."""

    question: str = Field(min_length=1, max_length=300)
    missing: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    original_query: str = ""
    route: str = ""
    attempts: int = 0

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = [
            "question",
            "missing",
            "options",
            "original_query",
            "route",
            "attempts",
        ]
        return schema


class ClarificationResolution(BaseModel):
    """Разбор ответа пользователя на уточняющий вопрос."""

    resolved: bool
    question: str = ""
    topic_changed: bool = False
    clarification_question: str = ""
    assumption: str = ""
    reason: str = ""

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = [
            "resolved",
            "question",
            "topic_changed",
            "clarification_question",
            "assumption",
            "reason",
        ]
        return schema


class ResultCheck(BaseModel):
    """Проверка: отвечает ли выполненный SQL на заданный вопрос."""

    complete: bool
    missing_conditions: list[str] = Field(default_factory=list)
    wrong_metric: bool = False
    corrected_question: str = ""
    clarification: str = ""
    reason: str = ""

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = [
            "complete",
            "missing_conditions",
            "wrong_metric",
            "corrected_question",
            "clarification",
            "reason",
        ]
        return schema


class ToolArgumentHints(BaseModel):
    """Фильтры инструментов, извлечённые из вопроса отдельным LLM-вызовом."""

    audit_code: str = ""
    item_type: str = ""
    query: str = ""

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = ["audit_code", "item_type", "query"]
        return schema


class ToolCall(BaseModel):
    """Один вызов инструмента, выбранный LLM."""

    name: str = Field(min_length=1)
    arguments: ToolArguments = Field(default_factory=ToolArguments)

    @field_validator("arguments", mode="before")
    @classmethod
    def _empty_arguments(cls, value: Any) -> Any:
        return {} if value is None else value


class ToolPlan(BaseModel):
    """Набор инструментов, запрошенных одним вызовом LLM."""

    calls: list[ToolCall] = Field(min_length=1)
    reason: str = ""

    @field_validator("calls", mode="before")
    @classmethod
    def _string_calls(cls, value: Any) -> Any:
        """Модель иногда присылает имена строкой вместо объекта."""
        if isinstance(value, list):
            return [
                {"name": item} if isinstance(item, str) else item
                for item in value
            ]
        return value


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
