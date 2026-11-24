"""Дополнение QueryPlan детерминированными сигналами вопроса.

LLM отвечает за смысл, но её structured output нестабилен: пустые
dimensions/filters при верном reason — типичный сбой. Слой intent берёт
доменные сигналы из semantic layer (карман, последний год, закрытая
проверка, тема и т.п.) и дополняет план, не меняя уже заданные условия.

Важно: это не подбор под конкретный вопрос. Все правила приходят из
каталога метрик и измерений, а неизвестные конструкции остаются за LLM.
"""

from __future__ import annotations

from ..semantic.catalog import get_metric, question_signals
from .plan import QueryFilter, QueryPlan


def complete_query_plan(question: str, plan: QueryPlan) -> QueryPlan:
    """Дополняет план разрезами/фильтрами, которые явно просит вопрос.

    Существующие условия не перезаписываются: если LLM уже указала год,
    тему или статус, они сохраняются. Функция возвращает новый QueryPlan,
    поэтому исходный план можно безопасно логировать и сравнивать.
    """
    spec = get_metric(plan.metric)
    signals = question_signals(question, spec)

    dimensions = list(plan.dimensions)
    for dimension in signals.dimensions:
        if dimension not in dimensions:
            dimensions.append(dimension)

    filters = list(plan.filters)
    existing_fields = {query_filter.field for query_filter in filters}
    for signal in signals.filters:
        if signal.field in existing_fields:
            continue
        if signal.field in dimensions:
            continue
        filters.append(
            QueryFilter(
                field=signal.field,
                value=signal.value,
                op=signal.op,
            )
        )
        existing_fields.add(signal.field)

    return plan.model_copy(
        update={"dimensions": dimensions, "filters": filters}
    )
