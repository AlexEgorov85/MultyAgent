"""Контракты готовых шаблонов и детерминированный выбор способа выполнения.

LLM больше не выбирает ``template_key``: шаблон — это execution strategy,
а не часть смысла вопроса. Код сопоставляет проверенный QueryPlan с
контрактом шаблона и запускает шаблон только если тот покрывает план.
Иначе SQL собирает компилятор.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..semantic.catalog import get_metric, question_metric_hint, question_signals
from .plan import QueryFilter, QueryPlan

_LATEST_YEAR_VALUES = frozenset(
    {"last", "latest", "последний", "последний год"}
)


@dataclass(frozen=True)
class TemplateContract:
    """Что шаблон умеет считать.

    ``required_dimensions`` должны присутствовать в плане, ``allowed_dimensions``
    ограничивают остальные разрезы, ``allowed_filters`` — допустимые фильтры.
    Если план содержит что-то вне контракта, шаблон не подходит.
    """

    key: str
    metrics: tuple[str, ...]
    required_dimensions: tuple[str, ...] = ()
    allowed_dimensions: tuple[str, ...] = ()
    allowed_filters: tuple[str, ...] = ()
    parameters: tuple[str, ...] = field(default_factory=tuple)
    # Явные сигналы вопроса, для которых шаблон и предназначен. Без них
    # несколько шаблонов с пустым контрактом (overdue/without_scripts)
    # могли бы матчиться на один и тот же план.
    intent_any: tuple[re.Pattern[str], ...] = field(default_factory=tuple)
    intent_all: tuple[re.Pattern[str], ...] = field(default_factory=tuple)


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


TEMPLATE_CONTRACTS: tuple[TemplateContract, ...] = (
    TemplateContract(
        key="status_summary",
        metrics=("audit_count",),
        required_dimensions=("status",),
        allowed_dimensions=("status",),
        allowed_filters=("year",),
        parameters=("year",),
        intent_any=(
            _p(r"(?<![а-яё])по\s+статусам\b"),
            _p(r"(?<![а-яё])сводк\w*[\s\S]*\bстатус\w*"),
        ),
    ),
    TemplateContract(
        key="top_findings",
        metrics=("deviation_count", "item_count", "critical_item_count"),
        required_dimensions=("title",),
        allowed_dimensions=("title",),
        allowed_filters=("year", "item_type"),
        parameters=("date_from", "limit"),
        intent_any=(
            _p(r"(?<![а-яё])топ\s*[-‑]?\s*\d*\s*(?:видов|формулировок)"),
        ),
    ),
    TemplateContract(
        key="theme_dynamics",
        metrics=("item_count", "critical_item_count", "repeat_item_count"),
        required_dimensions=("theme",),
        allowed_dimensions=("theme", "year"),
        parameters=(),
        intent_any=(_p(r"(?<![а-яё])динамик\w*"),),
    ),
    TemplateContract(
        key="overdue_items",
        metrics=("overdue_item_count",),
        allowed_dimensions=(
            "title",
            "risk_level",
            "status",
            "item_type",
            "responsible_unit",
        ),
        parameters=(),
        intent_any=(_p(r"(?<![а-яё])просроч\w*"),),
    ),
    TemplateContract(
        key="items_without_scripts",
        metrics=("no_script_item_count",),
        allowed_dimensions=(
            "title",
            "item_type",
            "risk_level",
            "responsible_unit",
        ),
        parameters=(),
        intent_any=(
            _p(
                r"(?<![а-яё])без\s+(?:скрипт|доказательств)\w*"
                r"|(?<![а-яё])без\s+приложенн\w*\s+скрипт\w*"
            ),
        ),
    ),
    TemplateContract(
        key="risk_by_pocket",
        metrics=(
            "audit_count",
            "item_count",
            "critical_item_count",
            "overdue_item_count",
        ),
        required_dimensions=("pocket",),
        allowed_dimensions=("pocket",),
        parameters=(),
        intent_all=(
            _p(r"(?<![а-яё])риск\w*"),
            _p(r"(?<![а-яё])карман\w*"),
        ),
    ),
)


def _plan_year(plan: QueryPlan, latest_year: int) -> int:
    for query_filter in plan.filters:
        if query_filter.field != "year":
            continue
        text = str(query_filter.value).strip().lower()
        if text in _LATEST_YEAR_VALUES:
            return latest_year
        try:
            return int(query_filter.value)
        except (TypeError, ValueError):
            continue
    return latest_year


def _contract_score(
    contract: TemplateContract,
    question: str,
    plan: QueryPlan,
) -> int | None:
    """Совпадение контракта и приоритет среди подходящих шаблонов."""
    normalized = " ".join(question.lower().replace("ё", "е").split())

    hint = question_metric_hint(question)
    if hint and not set(hint) & set(contract.metrics):
        return None

    dimensions = set(plan.dimensions)
    if not set(contract.required_dimensions) <= dimensions:
        return None
    if contract.allowed_dimensions and not dimensions <= set(
        contract.allowed_dimensions
    ):
        return None

    filter_fields = {query_filter.field for query_filter in plan.filters}
    if not filter_fields <= set(contract.allowed_filters):
        return None

    if any(not pattern.search(normalized) for pattern in contract.intent_all):
        return None
    if contract.intent_any and not any(
        pattern.search(normalized) for pattern in contract.intent_any
    ):
        return None

    score = 0
    # Точное совпадение метрики важнее «подходящей по сущности».
    if plan.metric in contract.metrics:
        score += 10
    score += len(contract.required_dimensions)
    if contract.intent_any or contract.intent_all:
        score += 1
    return score


def _intent_matches(contract: TemplateContract, question: str) -> bool:
    normalized = " ".join(question.lower().replace("ё", "е").split())
    if any(not pattern.search(normalized) for pattern in contract.intent_all):
        return False
    if contract.intent_any and not any(
        pattern.search(normalized) for pattern in contract.intent_any
    ):
        return False
    return True


def _plan_from_question(question: str, metric: str) -> QueryPlan:
    spec = get_metric(metric)
    signals = question_signals(question, spec)
    filters = [
        QueryFilter(
            field=signal.field,
            value=signal.value,
            op=signal.op,
        )
        for signal in signals.filters
    ]
    return QueryPlan(
        metric=metric,
        dimensions=list(signals.dimensions),
        filters=filters,
        reason="план собран из доменных сигналов вопроса",
    )


def select_template_from_question(
    question: str,
    latest_year: int,
) -> tuple[str, dict[str, int], QueryPlan] | None:
    """Детерминированный fast path: шаблон выбирается без LLM.

    Нужен, чтобы template-вопросы не зависели от structured output модели.
    Если явных сигналов шаблона нет, возвращает ``None`` и работает
    обычный Query IR.
    """
    for contract in TEMPLATE_CONTRACTS:
        if not _intent_matches(contract, question):
            continue
        plan = _plan_from_question(question, contract.metrics[0])
        selection = select_template(question, plan, latest_year)
        if selection is not None and selection[0] == contract.key:
            return selection[0], selection[1], plan
    return None


def select_template(
    question: str,
    plan: QueryPlan,
    latest_year: int,
) -> tuple[str, dict[str, int]] | None:
    """Возвращает ``(template_key, parameters)`` или ``None``.

    Выбор детерминированный: LLM не участвует. Шаблон допускается только
    при совпадении контракта с планом; при нескольких кандидатах
    выигрывает точное совпадение метрики и более специфичный контракт.
    """
    candidates: list[tuple[int, int, TemplateContract]] = []
    for index, contract in enumerate(TEMPLATE_CONTRACTS):
        score = _contract_score(contract, question, plan)
        if score is not None:
            candidates.append((score, -index, contract))

    if not candidates:
        return None

    _, _, contract = max(candidates, key=lambda item: (item[0], item[1]))
    if contract.key == "status_summary":
        return contract.key, {"year": _plan_year(plan, latest_year)}
    if contract.key == "top_findings":
        limit = plan.limit if plan.limit != 200 else 10
        return contract.key, {
            "date_from": f"{_plan_year(plan, latest_year)}-01-01",
            "limit": limit,
        }
    return contract.key, {}
