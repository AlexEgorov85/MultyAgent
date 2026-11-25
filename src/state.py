"""Состояния LangGraph-подагентов."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AnalyticsState(TypedDict, total=False):
    """Состояние Analytics-подагента."""

    acl_request: dict[str, Any]
    request: dict[str, Any]
    question: str
    conversation_context: str
    dialogue_slots: dict[str, Any]
    auditor_id: str
    profile_text: str
    language: str
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
    truncated: bool
    max_rows: int
    chart: dict[str, Any]
    chart_source_question: str
    chart_source: str
    facts: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    retries: int
    verify_attempts: int
    verify_retry: bool
    verify_issues: list[str]
    asked_clarifications: list[str]
    answer: str
    answer_source: str  # llm | agent | template
    clarification: dict[str, Any]
    acl_response: dict[str, Any]
    metrics: dict[str, Any]


class RetrievalState(TypedDict, total=False):
    """Состояние Retrieval-подагента."""

    acl_request: dict[str, Any]
    request: dict[str, Any]
    question: str
    conversation_context: str
    dialogue_slots: dict[str, Any]
    auditor_id: str
    profile_text: str
    language: str
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
    conversation_context: str
    dialogue_slots: dict[str, Any]
    auditor_id: str
    profile_text: str
    report_format: str
    signature: str
    language: str
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


class InvestigationState(TypedDict, total=False):
    """Состояние Coordinator расследования (A7)."""

    acl_request: dict[str, Any]
    request: dict[str, Any]
    question: str
    conversation_context: str
    dialogue_slots: dict[str, Any]
    auditor_id: str
    profile_text: str
    language: str
    conversation_id: str
    status: str
    error: str
    plan: dict[str, Any]
    rounds: int
    acl_log: list[dict[str, Any]]
    analytics_content: dict[str, Any]
    retrieval_content: dict[str, Any]
    missing: list[str]
    answer: dict[str, Any]
    evidence: list[dict[str, Any]]
    acl_response: dict[str, Any]
    metrics: dict[str, Any]


class MainState(TypedDict, total=False):
    """Состояние основного графа."""

    messages: Annotated[list[Any], operator.add]
    user_query: str
    resolved_query: str
    resolved_reason: str
    dialogue_context: str
    dialogue_slots: dict[str, Any]
    turn_id: str
    client_history: list[dict[str, Any]]
    auditor_id: str
    language: str
    conversation_id: str
    route: str
    route_reason: str
    route_confidence: float
    route_error: bool
    chart_source: str
    pending_clarification: dict[str, Any]
    clarification: dict[str, Any]
    clarification_assumption: str
    clarification_history: list[str]
    answered_clarification: bool
    meta_query: bool
    analytics_mode: str
    profile: dict[str, str]
    memory_saved: bool
    guardrail: dict[str, Any]
    answer_guardrail: dict[str, Any]
    final_answer: str
    presentation: dict[str, Any]
    trace: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    acl_response: dict[str, Any]
    metrics: dict[str, Any]
