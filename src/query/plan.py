"""Структурированный план аналитического запроса.

LLM извлекает метрику, измерения и фильтры. SQL строит компилятор, а не
модель. Это отделяет понимание вопроса от генерации SQL.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class QueryFilter(BaseModel):
    """Одно условие фильтрации."""

    field: str = Field(min_length=1)
    value: str | int | float | bool
    op: Literal["eq", "contains"] = "eq"


class QueryPlan(BaseModel):
    """План запроса: что считать и по каким разрезам."""

    metric: str = Field(min_length=1)
    unsupported: bool = False
    dimensions: list[str] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    order_by: Literal["count_desc", "count_asc", "none"] = "count_desc"
    limit: int = Field(default=200, ge=1, le=200)
    template_key: str = ""
    reason: str = ""

    @field_validator("dimensions", "filters", mode="before")
    @classmethod
    def _missing_list(cls, value: Any) -> Any:
        """Модель иногда присылает null вместо пустого списка."""
        return [] if value is None else value

    @field_validator("template_key", "reason", mode="before")
    @classmethod
    def _missing_text(cls, value: Any) -> Any:
        return "" if value is None else value

    @field_validator("order_by", mode="before")
    @classmethod
    def _unknown_order(cls, value: Any) -> Any:
        """Сортировку задаёт компилятор; необычная форма не должна ломать план."""
        if value in ("count_desc", "count_asc", "none"):
            return value
        return "none"

    @field_validator("limit", mode="before")
    @classmethod
    def _invalid_limit(cls, value: Any) -> Any:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return 200
        return max(1, min(200, number))

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = [
            "metric",
            "unsupported",
            "dimensions",
            "filters",
            "order_by",
            "limit",
            "template_key",
            "reason",
        ]
        return schema


class PlanFilter(BaseModel):
    """Недостающий фильтр, найденный LLM-проверкой плана."""

    field: str = Field(min_length=1)
    value: str
    op: str = "eq"


class PlanGaps(BaseModel):
    """Чего не хватает в QueryPlan по сравнению с вопросом."""

    metric: str = ""
    clarification: str = ""
    missing_dimensions: list[str] = Field(default_factory=list)
    missing_filters: list[PlanFilter] = Field(default_factory=list)
    period: str = "none"
    year: int | None = None
    last_years: int | None = None
    issues: list[str] = Field(default_factory=list)

    @field_validator("missing_dimensions", "issues", mode="before")
    @classmethod
    def _missing_list(cls, value: Any) -> Any:
        """Модель иногда присылает строку вместо списка."""
        if value is None:
            return []
        return [value] if isinstance(value, str) else value

    @field_validator("year", "last_years", mode="before")
    @classmethod
    def _optional_int(cls, value: Any) -> Any:
        """Одно число — ок; диапазон или пустая строка — не добавляем год."""
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = [
            "metric",
            "clarification",
            "missing_dimensions",
            "missing_filters",
            "period",
            "year",
            "last_years",
            "issues",
        ]
        return schema
