"""Контракты готовых шаблонов и проверка выбора LLM.

Шаблон выбирает LLM (`QueryPlan.template_key`), но запускается он только
если контракт покрывает смысл плана: метрику, разрезы и фильтры.
Иначе Analytics откатывается на SQL по QueryPlan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .plan import QueryPlan

_LATEST_YEAR_VALUES = frozenset(
    {"last", "latest", "последний", "последний год"}
)


def _is_year_range(value: object) -> bool:
    """True для диапазона ``last_N``: шаблоны поддерживают только один год."""
    text = str(value or "").strip().lower()
    if text in _LATEST_YEAR_VALUES:
        return False
    if not text.startswith("last_"):
        return False
    number = text.removeprefix("last_").removesuffix("_years")
    return number.isdigit() and int(number) > 1


@dataclass(frozen=True)
class TemplateContract:
    """Что шаблон умеет считать."""

    key: str
    metrics: tuple[str, ...]
    required_dimensions: tuple[str, ...] = ()
    allowed_dimensions: tuple[str, ...] = ()
    allowed_filters: tuple[str, ...] = ()
    parameters: tuple[str, ...] = field(default_factory=tuple)


TEMPLATE_CONTRACTS: tuple[TemplateContract, ...] = (
    TemplateContract(
        key="status_summary",
        metrics=("audit_count",),
        required_dimensions=("status",),
        allowed_dimensions=("status",),
        allowed_filters=("year",),
        parameters=("year",),
    ),
    TemplateContract(
        key="top_findings",
        metrics=("deviation_count", "item_count", "critical_item_count"),
        required_dimensions=("title",),
        allowed_dimensions=("title",),
        allowed_filters=("year", "item_type"),
        parameters=("date_from", "limit"),
    ),
    TemplateContract(
        key="theme_dynamics",
        metrics=("item_count", "critical_item_count", "repeat_item_count"),
        required_dimensions=("theme",),
        allowed_dimensions=("theme", "year"),
        parameters=(),
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
    ),
)

TEMPLATE_CONTRACTS_BY_KEY: dict[str, TemplateContract] = {
    contract.key: contract for contract in TEMPLATE_CONTRACTS
}


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


def template_plan_problems(template_key: str, plan: QueryPlan) -> list[str]:
    """Почему выбранный LLM шаблон не покрывает план."""
    contract = TEMPLATE_CONTRACTS_BY_KEY.get(template_key)
    if contract is None:
        return [f"неизвестный шаблон {template_key}"]

    problems: list[str] = []
    if plan.metric not in contract.metrics:
        problems.append(
            f"шаблон {template_key} не считает метрику {plan.metric}"
        )

    dimensions = set(plan.dimensions)
    missing = set(contract.required_dimensions) - dimensions
    if missing:
        problems.append("нет разрезов: " + ", ".join(sorted(missing)))
    if contract.allowed_dimensions and not dimensions <= set(
        contract.allowed_dimensions
    ):
        extra = dimensions - set(contract.allowed_dimensions)
        problems.append("лишние разрезы: " + ", ".join(sorted(extra)))

    filter_fields = {query_filter.field for query_filter in plan.filters}
    if not filter_fields <= set(contract.allowed_filters):
        extra_filters = filter_fields - set(contract.allowed_filters)
        problems.append(
            "шаблон не поддерживает фильтры: "
            + ", ".join(sorted(extra_filters))
        )

    # Шаблон принимает один год, поэтому ``year=last_2`` нельзя
    # молча превращать в последний год: это даст неверное число.
    if any(
        query_filter.field == "year"
        and _is_year_range(query_filter.value)
        for query_filter in plan.filters
    ):
        problems.append("шаблон не поддерживает диапазон лет last_N")
    return problems


def template_parameters(
    template_key: str,
    plan: QueryPlan,
    latest_year: int,
) -> dict[str, int]:
    """Параметры шаблона из проверенного плана, без догадок LLM."""
    if template_key == "status_summary":
        return {"year": _plan_year(plan, latest_year)}
    if template_key == "top_findings":
        limit = plan.limit if plan.limit != 200 else 10
        return {
            "date_from": f"{_plan_year(plan, latest_year)}-01-01",
            "limit": limit,
        }
    return {}
