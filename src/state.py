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


class RetrievalState(TypedDict, total=False):
    """Состояние Retrieval-подагента."""

    acl_request: dict[str, Any]
    request: dict[str, Any]
    question: str
    auditor_id: str
    conversation_id: str
    status: str
    error: str
    chunks: list[dict[str, Any]]
    answer: dict[str, Any]
    critique: dict[str, Any]
    citations: list[str]
    citation_issues: list[str]
    critic_issues: list[str]
    iterations: int
    warnings: list[str]
    evidence: list[dict[str, Any]]
    search_mode: str
    acl_response: dict[str, Any]
    metrics: dict[str, Any]


class ReportState(TypedDict, total=False):
    """Состояние Report-подагента и Inspector."""

    acl_request: dict[str, Any]
    request: dict[str, Any]
    question: str
    auditor_id: str
    conversation_id: str
    status: str
    error: str
    audit_code: str
    facts: list[dict[str, Any]]
    facts_text: str
    allowed_ids: list[str]
    draft: dict[str, Any]
    review: dict[str, Any]
    review_issues: list[str]
    citation_issues: list[str]
    iterations: int
    citations: list[str]
    evidence: list[dict[str, Any]]
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
