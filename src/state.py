"""Состояния LangGraph-подагентов."""

from __future__ import annotations

from typing import Any, TypedDict


class AnalyticsState(TypedDict, total=False):
    """Состояние Analytics-подагента."""

    acl_request: dict[str, Any]
    request: dict[str, Any]
    question: str
    auditor_id: str
    conversation_id: str
    status: str  # ok | refused | failed
    error: str
    mode: str
    retry: bool
    strategy: str
    plan: dict[str, Any]
    sql: str
    rows: list[dict[str, Any]]
    columns: list[str]
    facts: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    retries: int
    answer: str
    acl_response: dict[str, Any]
    metrics: dict[str, Any]


class MainState(TypedDict, total=False):
    """Состояние основного графа."""

    messages: list[Any]
    user_query: str
    auditor_id: str
    conversation_id: str
    route: str
    final_answer: str
    acl_response: dict[str, Any]
    metrics: dict[str, Any]
