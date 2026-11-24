"""Применение LLM-проверки плана к QueryPlan.

LLM возвращает ``PlanGaps``: каких разрезов/фильтров не хватает.
Код применяет их к плану, проверяя поля и значения по semantic layer.
Никакого regex-разбора вопроса здесь нет.
"""

from __future__ import annotations

from ..semantic.catalog import get_metric
from .plan import PlanGaps, QueryFilter, QueryPlan

_LATEST_YEAR_VALUES = frozenset(
    {"last", "latest", "последний", "последний год"}
)


def _split_values(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    for separator in (",", ";", "/"):
        if separator in text:
            return [
                part.strip()
                for part in text.split(separator)
                if part.strip()
            ]
    return [text]


def _canonical_value(
    field: str,
    value: str,
    allowed: tuple[str, ...],
) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    if field == "year":
        if text.lower() in _LATEST_YEAR_VALUES:
            return "last"
        try:
            return str(int(text))
        except (TypeError, ValueError):
            return None
    if not allowed:
        return text
    lower = text.lower()
    for candidate in allowed:
        if candidate.lower() == lower:
            return candidate
    return None


def apply_plan_gaps(plan: QueryPlan, gaps: PlanGaps) -> QueryPlan:
    """Дополняет план недостающими разрезами/фильтрами.

    Значения проверяются по каталогу метрики. Если LLM предложила поле
    или значение вне каталога, оно отбрасывается, а не попадает в SQL.
    """
    spec = get_metric(plan.metric)
    dimensions = list(plan.dimensions)
    filters = list(plan.filters)

    for dimension in gaps.missing_dimensions:
        name = str(dimension or "").strip()
        if name in spec.dimensions and name not in dimensions:
            dimensions.append(name)

    grouped: dict[str, list[str]] = {}
    for gap_filter in gaps.missing_filters:
        name = str(gap_filter.field or "").strip()
        if not name or name not in spec.dimensions:
            continue
        grouped.setdefault(name, []).extend(_split_values(gap_filter.value))

    for name, raw_values in grouped.items():
        if name in dimensions:
            continue
        allowed = tuple(spec.allowed_values.get(name, ()))
        values = [
            canonical
            for value in raw_values
            if (canonical := _canonical_value(name, value, allowed)) is not None
        ]
        values = list(dict.fromkeys(values))
        if not values:
            continue
        # Проверка плана может не только добавить, но и исправить условие
        # (например, «нет, я имею в виду проблемы»). Поэтому старые
        # фильтры этого поля заменяются новым решением.
        filters = [
            query_filter
            for query_filter in filters
            if query_filter.field != name
        ]
        if len(values) > 1:
            # Несколько значений одного поля — это разрез, а не AND-фильтры.
            if name not in dimensions:
                dimensions.append(name)
            continue
        op = "contains" if name == "specialization" else "eq"
        filters.append(QueryFilter(field=name, value=values[0], op=op))

    period_years: int | None = None
    if gaps.last_years and gaps.last_years > 0:
        period_years = int(gaps.last_years)
    elif gaps.period == "last_year":
        period_years = 1
    elif gaps.period.startswith("last_") and gaps.period.endswith("_years"):
        try:
            candidate = int(
                gaps.period.removeprefix("last_").removesuffix("_years")
            )
        except ValueError:
            candidate = 0
        if candidate > 0:
            period_years = candidate

    if period_years is not None and "year" not in dimensions:
        filters = [
            query_filter
            for query_filter in filters
            if query_filter.field != "year"
        ]
        filters.append(
            QueryFilter(
                field="year",
                value="last" if period_years == 1 else f"last_{period_years}",
            )
        )
    elif gaps.period == "year" and gaps.year is not None:
        if "year" not in dimensions:
            filters = [
                query_filter
                for query_filter in filters
                if query_filter.field != "year"
            ]
            filters.append(QueryFilter(field="year", value=int(gaps.year)))

    return plan.model_copy(
        update={"dimensions": dimensions, "filters": filters}
    )
