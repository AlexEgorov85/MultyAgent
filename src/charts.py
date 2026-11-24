"""Проверка данных для диаграмм, которые выбирает LLM.

ChartSpec строит модель. Код не придумывает тип диаграммы и не строит
эвристическую визуализацию: он только проверяет, что каждая точка
(категория, значение) действительно есть в строках предыдущего ответа.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_year_field(field: str) -> bool:
    lower = str(field or "").lower()
    return any(
        hint in lower
        for hint in ("year", "год", "period", "month", "date", "месяц", "дата")
    )


def _numeric_columns(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
) -> list[str]:
    result: list[str] = []
    for column in columns:
        values = [row.get(column) for row in rows if row.get(column) is not None]
        if values and all(_is_number(value) for value in values):
            result.append(column)
    return result


def _norm_label(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("ё", "е").split())


def _row_chart_pairs(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
) -> set[tuple[str, float]]:
    """Все допустимые пары «категория — число» из исходных строк."""
    numeric = _numeric_columns(rows, columns)
    categorical = [
        column
        for column in columns
        if column not in numeric or _is_year_field(column)
    ]
    pairs: set[tuple[str, float]] = set()
    for row in rows:
        labels: list[str] = []
        for column in categorical:
            value = row.get(column)
            if value is not None and value != "":
                labels.append(_norm_label(value))
        # Модель может соединить два измерения через « · ».
        for left_index, left in enumerate(categorical[:4]):
            for right in categorical[left_index + 1 : 4]:
                left_value = row.get(left)
                right_value = row.get(right)
                if left_value is not None and right_value is not None:
                    labels.append(_norm_label(f"{left_value} · {right_value}"))
        for measure in numeric:
            value = row.get(measure)
            if _is_number(value):
                for label in labels:
                    pairs.add((label, round(float(value), 4)))
    return pairs


def ground_chart_points(
    spec: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
) -> list[dict[str, Any]] | None:
    """Оставляет только точки, которые действительно есть в строках.

    LLM выбирает визуализацию, но числа и категории не должны быть
    выдуманными. Если валидных точек меньше двух — chart не принимается.
    """
    data = spec.get("data")
    if not isinstance(data, list):
        return None
    allowed = _row_chart_pairs(rows, columns)
    grounded: list[dict[str, Any]] = []
    for point in data:
        if not isinstance(point, dict):
            continue
        label = _norm_label(point.get("label"))
        value = point.get("value")
        if not label or not _is_number(value):
            continue
        key = (label, round(float(value), 4))
        if key in allowed:
            grounded.append(
                {"label": str(point.get("label")), "value": float(value)}
            )
    return grounded if len(grounded) >= 2 else None
