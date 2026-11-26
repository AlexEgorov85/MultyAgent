"""Детерминированный compiler QueryPlan → read-only SQL."""

from __future__ import annotations

from typing import Any

from ..semantic.catalog import MetricSpec, get_metric
from .plan import QueryFilter, QueryPlan


class QueryCompileError(ValueError):
    """QueryPlan не соответствует semantic layer."""


_LATEST_YEAR_VALUES = frozenset(
    {"last", "latest", "последний", "последний год"}
)


def _last_years(text: str) -> int | None:
    value = str(text or "").strip().lower()
    if not value.startswith("last_"):
        return None
    digits = value.removeprefix("last_").removesuffix("_years")
    try:
        number = int(digits)
    except ValueError:
        return None
    return number if number > 0 else None


def _canonical_value(spec: MetricSpec, field_name: str, value: Any) -> Any:
    if field_name == "year":
        text = str(value).strip().lower()
        if text in _LATEST_YEAR_VALUES:
            return "last"
        years = _last_years(text)
        if years is not None:
            return f"last_{years}"
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise QueryCompileError(f"year должен быть целым: {value!r}") from exc
    if field_name == "is_repeat":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "1", "да"):
            return True
        if text in ("false", "0", "нет"):
            return False
        raise QueryCompileError(f"is_repeat должен быть boolean: {value!r}")

    text = str(value).strip()
    allowed = spec.allowed_values.get(field_name, ())
    if allowed:
        for candidate in allowed:
            if candidate.lower() == text.lower():
                return candidate
        raise QueryCompileError(
            f"Недопустимое значение {field_name}={value!r}. "
            f"Разрешены: {', '.join(allowed)}"
        )
    return text


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _condition(spec: MetricSpec, query_filter: QueryFilter) -> str:
    field_name = query_filter.field.strip()
    expression = spec.dimensions.get(field_name)
    if expression is None:
        raise QueryCompileError(
            f"Поле {field_name!r} недопустимо для метрики {spec.id!r}. "
            f"Доступны: {', '.join(spec.dimensions)}"
        )
    value = _canonical_value(spec, field_name, query_filter.value)
    if field_name == "year" and value == "last":
        return (
            f"{expression} = ("
            "SELECT max(p_last.pocket_year) FROM audit.audit_pockets p_last"
            ")"
        )
    if field_name == "year":
        years = _last_years(str(value))
        if years is not None:
            return (
                f"{expression} >= ("
                "SELECT max(p_last.pocket_year) - "
                f"{years - 1} FROM audit.audit_pockets p_last"
                ")"
            )
    if query_filter.op == "contains":
        if field_name != "specialization":
            raise QueryCompileError(
                "op=contains поддерживается только для specialization"
            )
        return f"{expression} @> ARRAY[{_literal(value)}]"
    return f"{expression} = {_literal(value)}"


def compile_query_plan(plan: QueryPlan) -> str:
    """Собирает SELECT из QueryPlan. Никакой свободной генерации SQL."""
    spec = get_metric(plan.metric)

    dimensions: list[tuple[str, str]] = []
    seen: set[str] = set()
    for dimension in plan.dimensions:
        field_name = dimension.strip()
        if field_name in seen:
            continue
        expression = spec.dimensions.get(field_name)
        if expression is None:
            raise QueryCompileError(
                f"Измерение {field_name!r} недопустимо для метрики {spec.id!r}. "
                f"Доступны: {', '.join(spec.dimensions)}"
            )
        seen.add(field_name)
        dimensions.append((field_name, expression))

    where_parts = list(spec.extra_where)
    grouped: dict[str, list[QueryFilter]] = {}
    for query_filter in plan.filters:
        field_name = query_filter.field.strip()
        grouped.setdefault(field_name, []).append(query_filter)
    for field_filters in grouped.values():
        if len(field_filters) == 1:
            where_parts.append(_condition(spec, field_filters[0]))
            continue
        # Несколько значений одного поля — это выбор одного из них,
        # а не одновременное выполнение всех условий. AND здесь даёт
        # пустой результат («год=2025 и год=2026»).
        conditions = [
            _condition(spec, query_filter) for query_filter in field_filters
        ]
        where_parts.append("(" + " OR ".join(conditions) + ")")

    select_parts = [f"{expression} AS {name}" for name, expression in dimensions]
    select_parts.append(f"{spec.count_expr} AS cnt")
    sql = f"SELECT {', '.join(select_parts)} FROM {spec.from_sql}"
    if where_parts:
        sql += " WHERE " + " AND ".join(f"({part})" for part in where_parts)
    if dimensions:
        group_by = ", ".join(expression for _, expression in dimensions)
        sql += f" GROUP BY {group_by}"
        if plan.order_by == "count_desc":
            sql += " ORDER BY cnt DESC"
        elif plan.order_by == "count_asc":
            sql += " ORDER BY cnt ASC"
    sql += f" LIMIT {int(plan.limit)}"
    return sql
