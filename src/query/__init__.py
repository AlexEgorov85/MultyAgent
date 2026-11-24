"""Query IR и детерминированный SQL-компилятор."""

from .compiler import QueryCompileError, compile_query_plan
from .intent import apply_plan_gaps
from .plan import PlanFilter, PlanGaps, QueryFilter, QueryPlan
from .templates import (
    TemplateContract,
    template_parameters,
    template_plan_problems,
)

__all__ = [
    "PlanFilter",
    "PlanGaps",
    "QueryCompileError",
    "QueryFilter",
    "QueryPlan",
    "TemplateContract",
    "apply_plan_gaps",
    "compile_query_plan",
    "template_parameters",
    "template_plan_problems",
]
