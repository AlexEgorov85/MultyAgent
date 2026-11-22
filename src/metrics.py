"""Метрики эффективности запроса."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterable

import os


@dataclass
class RequestMetrics:
    """Метрики одного запроса."""

    timings: dict[str, float] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_timing(self, name: str, seconds: float) -> None:
        self.timings[name] = self.timings.get(name, 0.0) + max(0.0, seconds)

    def incr(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def merge(self, other: "RequestMetrics") -> "RequestMetrics":
        for key, value in other.timings.items():
            self.add_timing(key, value)
        for key, value in other.counters.items():
            self.incr(key, value)
        for key, value in other.tokens.items():
            self.tokens[key] = self.tokens.get(key, 0) + value
        self.cost_usd += other.cost_usd
        self.metadata.update(other.metadata)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "timings": dict(self.timings),
            "counters": dict(self.counters),
            "tokens": dict(self.tokens),
            "cost_usd": round(self.cost_usd, 6),
            "metadata": dict(self.metadata),
        }


@contextmanager
def timer(metrics: RequestMetrics, name: str):
    """Замеряет длительность блока в секундах."""
    started = time.perf_counter()
    try:
        yield
    finally:
        metrics.add_timing(name, time.perf_counter() - started)


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    *,
    input_price_per_1m: float | None = None,
    output_price_per_1m: float | None = None,
) -> float:
    """Оценивает стоимость по учебным ценам из окружения."""
    price_in = (
        input_price_per_1m
        if input_price_per_1m is not None
        else float(os.getenv("INPUT_PRICE_PER_1M_TOKENS", "0.25"))
    )
    price_out = (
        output_price_per_1m
        if output_price_per_1m is not None
        else float(os.getenv("OUTPUT_PRICE_PER_1M_TOKENS", "2.00"))
    )
    return input_tokens / 1_000_000 * price_in + output_tokens / 1_000_000 * price_out


def percentile(values: Iterable[float], p: float) -> float:
    """Линейно интерполированный перцентиль (p в диапазоне 0..1)."""
    data = sorted(values)
    if not data:
        return 0.0
    if len(data) == 1:
        return float(data[0])
    index = (len(data) - 1) * p
    lower = int(index)
    upper = min(lower + 1, len(data) - 1)
    weight = index - lower
    return float(data[lower] * (1 - weight) + data[upper] * weight)


def mean(values: Iterable[float]) -> float:
    """Среднее арифметическое; для пустого набора возвращает 0.0."""
    data = list(values)
    return sum(data) / len(data) if data else 0.0
