"""Единые подписи и форматирование значений для ответа и trace.

Модуль не решает, что считать: он только переводит имя колонки или id
метрики в человеческую подпись и форматирует значение. Один словарь на
весь проект — чтобы presentation и fallback аналитики не расходились.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from .i18n import t
from .semantic.catalog import metric_label

YEAR_COLUMNS = frozenset({"year", "pocket_year", "period_year", "audit_year"})

COLUMN_LABELS: dict[str, dict[str, str]] = {
    "ru": {
        "audit_id": "проверка",
        "audit_code": "проверка",
        "act_id": "акт",
        "act_number": "акт",
        "item_id": "ID пункта",
        "item_number": "пункт",
        "item_type": "тип пункта",
        "test_type": "тип проверки",
        "title": "название",
        "risk_level": "уровень риска",
        "status": "статус",
        "act_status": "статус акта",
        "item_status": "статус пункта",
        "deadline": "срок",
        "closed_at": "закрыт",
        "act_date": "дата акта",
        "year": "год",
        "month": "месяц",
        "period_year": "год",
        "pocket_year": "год",
        "pocket_id": "карман",
        "pocket_title": "карман",
        "pocket": "карман",
        "theme_code": "тема",
        "theme": "тема",
        "theme_name": "тема",
        "audit_count": "Проверок",
        "completed_count": "Завершённых проверок",
        "completed_audits": "Завершённых проверок",
        "completed_audits_count": "Завершённых проверок",
        "closed_audits_count": "Завершённых проверок",
        "count": "Всего",
        "total": "Всего",
        "cnt": "Всего",
        "items_count": "Пунктов",
        "total_items": "Всего пунктов",
        "deviations_count": "Отклонений",
        "overdue_open_items": "Просроченных открытых пунктов",
        "overdue_open_items_count": "Просроченных открытых пунктов",
        "critical_open_count": "Критичных открытых пунктов",
        "overdue_share_pct": "Доля просроченных",
        "avg_risk": "Средний риск",
        "source_id": "источник",
        "source_type": "тип источника",
    },
    "en": {
        "audit_id": "audit",
        "audit_code": "audit",
        "act_id": "act",
        "act_number": "act",
        "item_id": "item ID",
        "item_number": "item",
        "item_type": "item type",
        "test_type": "test type",
        "title": "title",
        "risk_level": "risk level",
        "status": "status",
        "act_status": "act status",
        "item_status": "item status",
        "deadline": "deadline",
        "closed_at": "closed at",
        "act_date": "act date",
        "year": "year",
        "month": "month",
        "period_year": "year",
        "pocket_year": "year",
        "pocket_id": "pocket",
        "pocket_title": "pocket",
        "pocket": "pocket",
        "theme_code": "theme",
        "theme": "theme",
        "theme_name": "theme",
        "audit_count": "Audits",
        "completed_count": "Completed audits",
        "completed_audits": "Completed audits",
        "completed_audits_count": "Completed audits",
        "closed_audits_count": "Completed audits",
        "count": "Total",
        "total": "Total",
        "cnt": "Total",
        "items_count": "Items",
        "total_items": "Total items",
        "deviations_count": "Deviations",
        "overdue_open_items": "Overdue open items",
        "overdue_open_items_count": "Overdue open items",
        "critical_open_count": "Critical open items",
        "overdue_share_pct": "Overdue share",
        "avg_risk": "Average risk",
        "source_id": "source",
        "source_type": "source type",
    },
}

METRIC_LABELS_EN: dict[str, str] = {
    "audit_count": "Audits",
    "auditor_count": "Auditors",
    "act_count": "Acts",
    "item_count": "Items",
    "critical_item_count": "Critical items",
    "overdue_item_count": "Overdue items",
    "repeat_item_count": "Repeat items",
    "no_script_item_count": "Items without scripts",
    "script_count": "Scripts",
    "run_count": "Script runs",
    "run_script_mismatch_count": "Runs with mismatch",
    "deviation_count": "Deviations",
    "deviation_gap_max": "Gap to threshold",
}

_TOTAL_COLUMNS = frozenset({"cnt", "count", "total"})


def language_code(language: str | None) -> str:
    """Нормализует язык подписи: всё, кроме en, считается русским."""
    return "en" if str(language or "").lower() == "en" else "ru"


def is_number(value: Any) -> bool:
    """Число, которое можно сравнивать и форматировать (Decimal тоже)."""
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def display_label(column: str, language: str | None = "ru") -> str:
    """Человеческая подпись колонки; неизвестная колонка — без подчёркиваний."""
    name = str(column or "").strip()
    if not name:
        return "—"
    lang = language_code(language)
    label = COLUMN_LABELS[lang].get(name)
    if label:
        return label
    text = name.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if lang == "ru" else text


def metric_display_label(metric: str, language: str | None = "ru") -> str:
    """Название метрики из каталога на нужном языке."""
    metric_id = str(metric or "").strip()
    if not metric_id:
        return ""
    if language_code(language) == "en":
        return METRIC_LABELS_EN.get(metric_id, "")
    return metric_label(metric_id)


def format_value(value: Any, column: str, language: str | None = "ru") -> str:
    """Форматирует значение без догадок о процентах по имени колонки."""
    lang = language_code(language)
    name = str(column or "")
    if value is None:
        return "—"
    if isinstance(value, bool):
        return t(lang, "yes" if value else "no")
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float):
        text = f"{value:.6g}"
        return text.replace(".", ",") if lang == "ru" else text
    if isinstance(value, int):
        if name in YEAR_COLUMNS or abs(value) < 1000:
            return str(value)
        text = f"{value:,}"
        return text.replace(",", " ") if lang == "ru" else text
    return str(value)


def headline_column(
    row: Mapping[str, Any],
    columns: Sequence[str],
    metric: str = "",
) -> str | None:
    """Колонка, которую можно назвать одним показателем, без списка alias.

    Один числовой столбец — это и есть показатель. Если числовых несколько,
    показателем считается `cnt` только при известной метрике: это контракт
    компилятора, а не угадывание по имени.
    """
    names = list(columns) or list(row)
    numeric = [
        name
        for name in names
        if name not in YEAR_COLUMNS and is_number(row.get(name))
    ]
    if len(numeric) == 1:
        return numeric[0]
    if metric and "cnt" in numeric:
        return "cnt"
    return None


def headline_label(column: str, metric: str, language: str | None = "ru") -> str:
    """Подпись показателя: метрика сильнее общего имени `cnt`."""
    label = metric_display_label(metric, language) if column in _TOTAL_COLUMNS else ""
    return label or display_label(column, language)
