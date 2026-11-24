"""Диаграммы по табличным данным: определение запроса и построение спецификации.

Chart spec — это данные, а не картинка: UI сам рисует bar/line/pie.
Сервер не вызывает LLM для визуализации, поэтому диаграмма всегда
соответствует строкам предыдущего ответа.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Mapping, Sequence

# «Построй диаграмму», «покажи на графике», «визуализируй» и т.п.
_CHART_REQUEST_RE = re.compile(
    r"(?<![а-яё])диаграмм\w*"
    r"|(?<![а-яё])визуализ\w*"
    r"|(?<![а-яё])(?:построй|построить|покажи|показать|сделай|сделать|"
    r"нарисуй|нарисовать)\w*\s+(?:график|диаграмм)\w*"
    r"|(?<![а-яё])график\w*\s+(?:по|для|на)\b"
    r"|(?<![а-яё])на\s+графике\b"
    r"|(?<![a-zа-яё])(?:chart|plot|visuali[sz]e)(?![a-zа-яё])",
    re.IGNORECASE,
)
_PIE_RE = re.compile(
    r"(?<![а-яё])кругов\w*|(?<![а-яё])дол\w*|(?<![а-яё])структур\w*"
    r"|(?<![а-яё])распредел\w*|(?<![а-яё])состав\w*"
    r"|(?<![a-zа-яё])(?:pie|donut)(?![a-zа-яё])",
    re.IGNORECASE,
)
_LINE_RE = re.compile(
    r"(?<![а-яё])динамик\w*|(?<![а-яё])тренд\w*"
    r"|(?<![а-яё])во\s+времени\b|(?<![а-яё])по\s+(?:годам|месяцам|датам)\b"
    r"|(?<![a-zа-яё])(?:line|trend)(?![a-zа-яё])",
    re.IGNORECASE,
)

_YEAR_HINTS = ("year", "год", "period", "month", "date", "месяц", "дата")
_CATEGORY_PRIORITY = (
    "pocket",
    "pocket_title",
    "theme_code",
    "theme",
    "theme_name",
    "status",
    "act_status",
    "item_type",
    "risk_level",
    "severity",
    "audit_type",
    "language",
    "audit_code",
    "title",
    "year",
    "pocket_year",
    "period_year",
)
_MEASURE_PRIORITY = (
    "cnt",
    "count",
    "total",
    "audit_count",
    "closed_audits_count",
    "completed_audits_count",
    "completed_count",
    "items_count",
    "total_items",
    "deviations_count",
    "critical_count",
    "item_count",
)

_CHART_LABELS_RU = {
    "pocket": "карман",
    "pocket_title": "карман",
    "theme_code": "тема",
    "theme": "тема",
    "theme_name": "тема",
    "status": "статус",
    "act_status": "статус акта",
    "item_type": "тип находки",
    "risk_level": "уровень риска",
    "severity": "уровень критичности",
    "audit_type": "тип проверки",
    "language": "язык",
    "audit_code": "проверка",
    "title": "название",
    "year": "год",
    "pocket_year": "год",
    "period_year": "год",
    "cnt": "Всего",
    "count": "Всего",
    "total": "Всего",
    "audit_count": "Проверок",
    "closed_audits_count": "Завершённых проверок",
    "completed_audits_count": "Завершённых проверок",
    "completed_count": "Завершённых проверок",
    "items_count": "Пунктов",
    "total_items": "Всего пунктов",
    "deviations_count": "Отклонений",
    "critical_count": "Критических",
    "item_count": "Пунктов",
}
_CHART_LABELS_EN = {
    "pocket": "pocket",
    "pocket_title": "pocket",
    "theme_code": "theme",
    "theme": "theme",
    "theme_name": "theme",
    "status": "status",
    "act_status": "act status",
    "item_type": "item type",
    "risk_level": "risk level",
    "severity": "severity",
    "audit_type": "audit type",
    "language": "language",
    "audit_code": "audit",
    "title": "title",
    "year": "year",
    "pocket_year": "year",
    "period_year": "year",
    "cnt": "Total",
    "count": "Total",
    "total": "Total",
    "audit_count": "Audits",
    "closed_audits_count": "Completed audits",
    "completed_audits_count": "Completed audits",
    "completed_count": "Completed audits",
    "items_count": "Items",
    "total_items": "Total items",
    "deviations_count": "Deviations",
    "critical_count": "Critical",
    "item_count": "Items",
}


def chart_requested(text: str) -> bool:
    """Просит ли пользователь визуализацию, а не только числа."""
    return bool(_CHART_REQUEST_RE.search(str(text or "")))


def chart_type(question: str, category_fields: Sequence[str] = ()) -> str:
    """bar | line | pie по формулировке и типу категории."""
    text = str(question or "")
    if _PIE_RE.search(text):
        return "pie"
    if _LINE_RE.search(text):
        return "line"
    if any(_is_year_field(field) for field in category_fields):
        return "line"
    return "bar"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_year_field(field: str) -> bool:
    lower = str(field or "").lower()
    return any(hint in lower for hint in _YEAR_HINTS)


def _unique(values: Iterable[Any]) -> list[Any]:
    seen: list[Any] = []
    for value in values:
        if value is None or value == "":
            continue
        if value not in seen:
            seen.append(value)
    return seen


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


def _category_candidates(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    numeric: Sequence[str],
) -> list[str]:
    candidates: list[str] = []
    for column in columns:
        values = _unique(row.get(column) for row in rows)
        if len(values) < 2 or len(values) > 30:
            continue
        if column in numeric and not _is_year_field(column):
            continue
        candidates.append(column)
    return candidates


def _pick_category(candidates: Sequence[str]) -> list[str]:
    if not candidates:
        return []
    ordered = sorted(
        enumerate(candidates),
        key=lambda item: (
            _CATEGORY_PRIORITY.index(item[1])
            if item[1] in _CATEGORY_PRIORITY
            else len(_CATEGORY_PRIORITY),
            item[0],
        ),
    )
    # До двух измерений: «тема + год» читается лучше, чем терять год.
    return [item[1] for item in ordered[:2]]


def _pick_measure(numeric: Sequence[str], categories: Sequence[str]) -> str | None:
    measures = [column for column in numeric if column not in categories]
    if not measures:
        return None
    for preferred in _MEASURE_PRIORITY:
        if preferred in measures:
            return preferred
    return measures[0]


def _label(
    column: str,
    language: str,
    labeler: Callable[[str], str] | None,
) -> str:
    if labeler is not None:
        try:
            text = str(labeler(column) or "").strip()
            if text:
                return text
        except Exception:
            pass
    labels = _CHART_LABELS_EN if str(language).lower() == "en" else _CHART_LABELS_RU
    return labels.get(column, column.replace("_", " ").strip().capitalize())


def _short(text: str, limit: int = 120) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def _norm_label(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("ё", "е").split())


def _row_chart_pairs(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
) -> set[tuple[str, float]]:
    numeric = _numeric_columns(rows, columns)
    categorical = [
        column
        for column in columns
        if column not in numeric
        or _is_year_field(column)
    ]
    pairs: set[tuple[str, float]] = set()
    for row in rows:
        labels: list[str] = []
        for column in categorical:
            value = row.get(column)
            if value is not None and value != "":
                labels.append(_norm_label(value))
        for left_index, left in enumerate(categorical[:4]):
            for right in categorical[left_index + 1 : 4]:
                left_value = row.get(left)
                right_value = row.get(right)
                if left_value is not None and right_value is not None:
                    labels.append(
                        _norm_label(f"{left_value} · {right_value}")
                    )
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
            grounded.append({"label": str(point.get("label")), "value": float(value)})
    return grounded if len(grounded) >= 2 else None


def build_chart_spec(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    *,
    question: str = "",
    previous_question: str = "",
    language: str = "ru",
    labeler: Callable[[str], str] | None = None,
) -> dict[str, Any] | None:
    """Строит chart spec из строк предыдущего ответа.

    Возвращает ``None``, если в данных нет числовой метрики и категории.
    """
    if not rows or not columns:
        return None
    if len(rows) < 2:
        return None

    numeric = _numeric_columns(rows, columns)
    if not numeric:
        return None

    candidates = _category_candidates(rows, columns, numeric)
    category_fields = _pick_category(candidates)
    measure = _pick_measure(numeric, category_fields)
    if measure is None:
        return None

    # Если категории нет, но есть год — используем его как ось.
    if not category_fields:
        years = [column for column in numeric if _is_year_field(column)]
        if years:
            category_fields = [years[0]]
        else:
            return None

    points: list[dict[str, Any]] = []
    for row in rows:
        label = " · ".join(
            str(row.get(field))
            for field in category_fields
            if row.get(field) is not None
        ).strip()
        value = row.get(measure)
        if not label or not _is_number(value):
            continue
        points.append({"label": label, "value": float(value)})
    if len(points) < 2:
        return None

    kind = chart_type(
        f"{question} {previous_question}".strip(),
        category_fields,
    )
    if kind == "line":
        points = points[:24]
    else:
        points.sort(key=lambda point: point["value"], reverse=True)
        points = points[:20]

    category_label = " · ".join(
        _label(field, language, labeler) for field in category_fields
    )
    value_label = _label(measure, language, labeler)
    source = previous_question or question
    title = (
        f"Диаграмма: {_short(source, 110)}"
        if source
        else f"Диаграмма: {value_label}"
    )
    if str(language).lower() == "en":
        title = (
            f"Chart: {_short(source, 110)}" if source else f"Chart: {value_label}"
        )

    return {
        "type": kind,
        "title": title,
        "subtitle": f"{value_label} — {category_label}",
        "category_fields": list(category_fields),
        "category_label": category_label,
        "value_field": measure,
        "value_label": value_label,
        "data": points,
    }
