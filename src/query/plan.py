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
    """План запроса: только смысл, без выбора способа выполнения.

    Шаблон — это execution strategy, а не часть intent. LLM не выбирает
    ``template_key``: иначе шаблон может подменить разрез/фильтры вопроса.
    Способ выполнения выбирает код по контракту уже проверенного плана.
    """

    metric: str = Field(min_length=1)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    order_by: Literal["count_desc", "count_asc", "none"] = "count_desc"
    limit: int = Field(default=200, ge=1, le=200)
    reason: str = ""
