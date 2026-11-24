"""Структурированный план аналитического запроса.

LLM извлекает метрику, измерения и фильтры. SQL строит компилятор, а не
модель. Это отделяет понимание вопроса от генерации SQL.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QueryFilter(BaseModel):
    """Одно условие фильтрации."""

    field: str = Field(min_length=1)
    value: str | int | float | bool
    op: Literal["eq", "contains"] = "eq"


class QueryPlan(BaseModel):
    """План запроса: что считать и по каким разрезам."""

    metric: str = Field(min_length=1)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    order_by: Literal["count_desc", "count_asc", "none"] = "count_desc"
    limit: int = Field(default=200, ge=1, le=200)
    template_key: str = ""
    reason: str = ""


class PlanFilter(BaseModel):
    """Недостающий фильтр, найденный LLM-проверкой плана."""

    field: str = Field(min_length=1)
    value: str
    op: str = "eq"


class PlanGaps(BaseModel):
    """Чего не хватает в QueryPlan по сравнению с вопросом."""

    missing_dimensions: list[str] = Field(default_factory=list)
    missing_filters: list[PlanFilter] = Field(default_factory=list)
    period: str = "none"
    year: int | None = None
    last_years: int | None = None
    issues: list[str] = Field(default_factory=list)

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema["required"] = [
            "missing_dimensions",
            "missing_filters",
            "period",
            "year",
            "last_years",
            "issues",
        ]
        return schema
