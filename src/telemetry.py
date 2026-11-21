"""Сбор процессных метрик одного запуска агента.

Метрики складываются в ``RequestMetrics`` текущего контекста:
- вызовы LLM и токены;
- вызовы инструментов и время выполнения;
- эмбеддинги;
- использованные версии промптов;
- шаги, если узел/агент решил их отметить.

Контекст включается на один ход бенчмарка через ``start_run()`` и
снимается ``snapshot()``. В обычной работе приложения телеметрия молчит:
если контекст не создан, все функции ничего не делают.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

from .metrics import RequestMetrics, estimate_cost

_CURRENT: ContextVar[RequestMetrics | None] = ContextVar(
    "agent_run_metrics", default=None
)


def start_run() -> RequestMetrics:
    """Начинает сбор метрик нового хода."""
    metrics = RequestMetrics()
    metrics.metadata.update(
        {
            "prompts": [],
            "tool_events": [],
            "llm_events": [],
            "embedding_events": [],
            "step_events": [],
        }
    )
    _CURRENT.set(metrics)
    return metrics


def stop_run() -> None:
    _CURRENT.set(None)


def current() -> RequestMetrics | None:
    return _CURRENT.get()


def _metadata_list(metrics: RequestMetrics, key: str) -> list[dict[str, Any]]:
    value = metrics.metadata.setdefault(key, [])
    return value if isinstance(value, list) else []


def record_llm(
    *,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    latency_sec: float = 0.0,
    schema: str = "",
) -> None:
    metrics = current()
    if metrics is None:
        return

    metrics.incr("llm_calls")
    metrics.incr("llm_attempts")
    metrics.add_timing("llm", latency_sec)
    metrics.tokens["input_tokens"] = metrics.tokens.get("input_tokens", 0) + int(
        input_tokens
    )
    metrics.tokens["output_tokens"] = metrics.tokens.get("output_tokens", 0) + int(
        output_tokens
    )
    metrics.tokens["cached_tokens"] = metrics.tokens.get("cached_tokens", 0) + int(
        cached_tokens
    )
    metrics.cost_usd += estimate_cost(int(input_tokens), int(output_tokens))
    _metadata_list(metrics, "llm_events").append(
        {
            "model": model,
            "schema": schema,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "cached_tokens": int(cached_tokens),
            "latency_sec": round(float(latency_sec), 4),
        }
    )


def record_llm_retry() -> None:
    metrics = current()
    if metrics is not None:
        metrics.incr("llm_attempts")
        metrics.incr("llm_retries")


def record_llm_error(
    *,
    model: str,
    latency_sec: float,
    schema: str = "",
    error: str = "",
) -> None:
    """Фиксирует неудачную попытку вызова LLM."""
    metrics = current()
    if metrics is None:
        return
    metrics.incr("llm_attempts")
    metrics.incr("llm_errors")
    metrics.add_timing("llm_failed", latency_sec)
    _metadata_list(metrics, "llm_events").append(
        {
            "model": model,
            "schema": schema,
            "status": "error",
            "error": error[:300],
            "latency_sec": round(float(latency_sec), 4),
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
        }
    )


def record_tool(
    name: str,
    latency_sec: float,
    *,
    status: str = "ok",
    details: dict[str, Any] | None = None,
) -> None:
    metrics = current()
    if metrics is None:
        return

    metrics.incr("tool_calls")
    metrics.incr(f"tool.{name}")
    metrics.add_timing("tools", latency_sec)
    _metadata_list(metrics, "tool_events").append(
        {
            "name": name,
            "status": status,
            "latency_sec": round(float(latency_sec), 4),
            "details": details or {},
        }
    )


def record_embedding(
    name: str,
    latency_sec: float,
    *,
    input_tokens: int = 0,
    status: str = "ok",
) -> None:
    metrics = current()
    if metrics is None:
        return

    metrics.incr("embedding_calls")
    metrics.add_timing("embeddings", latency_sec)
    if input_tokens:
        metrics.tokens["embedding_tokens"] = metrics.tokens.get(
            "embedding_tokens", 0
        ) + int(input_tokens)
    _metadata_list(metrics, "embedding_events").append(
        {
            "name": name,
            "status": status,
            "input_tokens": int(input_tokens),
            "latency_sec": round(float(latency_sec), 4),
        }
    )


def record_prompt(name: str, version: int, prompt_hash: str) -> None:
    metrics = current()
    if metrics is None:
        return
    item = {"id": name, "version": int(version), "hash": prompt_hash}
    prompts = _metadata_list(metrics, "prompts")
    if item not in prompts:
        prompts.append(item)


def record_step(
    name: str,
    latency_sec: float = 0.0,
    *,
    status: str = "ok",
    details: dict[str, Any] | None = None,
) -> None:
    metrics = current()
    if metrics is None:
        return
    metrics.incr("steps")
    if latency_sec:
        metrics.add_timing("steps", latency_sec)
    _metadata_list(metrics, "step_events").append(
        {
            "name": name,
            "status": status,
            "latency_sec": round(float(latency_sec), 4),
            "details": details or {},
        }
    )


def timed_tool(name: str) -> Callable:
    """Декоратор для инструментов: имя, статус и время вызова."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            status = "ok"
            try:
                return func(*args, **kwargs)
            except Exception:
                status = "error"
                raise
            finally:
                record_tool(name, time.perf_counter() - started, status=status)

        return wrapper

    return decorator


def timed_embedding(name: str = "embed") -> Callable:
    """Декоратор для эмбеддингов; токены добавляются, если они доступны."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            status = "ok"
            try:
                return func(*args, **kwargs)
            except Exception:
                status = "error"
                raise
            finally:
                record_embedding(name, time.perf_counter() - started, status=status)

        return wrapper

    return decorator


def snapshot() -> dict[str, Any]:
    """Снимок метрик текущего хода для отчёта."""
    metrics = current()
    if metrics is None:
        return {}
    data = metrics.to_dict()
    counters = data.get("counters") or {}
    for key, value in counters.items():
        data.setdefault(key, value)
    for key in (
        "llm_calls",
        "llm_attempts",
        "llm_errors",
        "llm_retries",
        "tool_calls",
        "embedding_calls",
        "steps",
    ):
        data.setdefault(key, 0)
    input_tokens = int(data["tokens"].get("input_tokens", 0))
    output_tokens = int(data["tokens"].get("output_tokens", 0))
    tool_events = list(data["metadata"].get("tool_events", []))
    llm_events = list(data["metadata"].get("llm_events", []))
    prompts = list(data["metadata"].get("prompts", []))
    data.update(
        {
            "total_tokens": input_tokens + output_tokens,
            "tool_names": [item.get("name", "") for item in tool_events],
            "tool_events": tool_events,
            "llm_events": llm_events,
            "prompts": prompts,
            "llm_latency_sec": round(
                float(data["timings"].get("llm", 0.0))
                + float(data["timings"].get("llm_failed", 0.0)),
                4,
            ),
            "llm_failed_latency_sec": round(
                float(data["timings"].get("llm_failed", 0.0)), 4
            ),
            "tool_latency_sec": round(float(data["timings"].get("tools", 0.0)), 4),
            "embedding_latency_sec": round(
                float(data["timings"].get("embeddings", 0.0)), 4
            ),
        }
    )
    return data
