"""Capability registry и deterministic matcher.

Capability — это typed-действие, а не свободный template_key. Matcher
выбирает его по явным фразам и слотам до LLM-планировщика.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .. import config


@dataclass(frozen=True)
class Capability:
    """Typed-действие, которое matcher выбирает до LLM-планировщика."""

    id: str
    title: str
    description: str
    required_parameters: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CapabilityMatch:
    """Результат сопоставления вопроса с capability и извлечёнными параметрами."""

    capability: Capability
    parameters: dict[str, Any]
    reason: str


CAPABILITIES: dict[str, Capability] = {
    "status_summary": Capability(
        id="status_summary",
        title="Сводка по статусам проверок",
        description="Количество проверок по статусам за год.",
        required_parameters=("year",),
    ),
    "top_findings": Capability(
        id="top_findings",
        title="Топ видов отклонений",
        description="Самые частые формулировки отклонений.",
        required_parameters=("date_from", "limit"),
    ),
    "theme_dynamics": Capability(
        id="theme_dynamics",
        title="Динамика по темам и годам",
        description="Количество пунктов и критических находок по темам и годам.",
    ),
    "overdue_items": Capability(
        id="overdue_items",
        title="Просроченные открытые пункты",
        description="Открытые пункты с истёкшим сроком устранения.",
    ),
    "items_without_scripts": Capability(
        id="items_without_scripts",
        title="Пункты без скриптов",
        description="Пункты актов без приложенного скрипта-доказательства.",
    ),
    "risk_by_pocket": Capability(
        id="risk_by_pocket",
        title="Риски по карманам",
        description="Сводка проверок, пунктов, критических и просроченных по карманам.",
    ),
}


def _normalise(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def _year(question: str, slots: dict[str, Any] | None) -> int | None:
    years = re.findall(r"\b(20\d{2})\b", question or "")
    if years:
        return int(years[-1])
    if slots and slots.get("year"):
        try:
            return int(slots["year"])
        except (TypeError, ValueError):
            return None
    return None


def _limit(question: str, default: int) -> int:
    text = _normalise(question)
    match = re.search(r"топ[-\s]?(\d+)", text) or re.search(
        r"(\d+)\s+вид", text
    )
    if match:
        return max(1, min(int(match.group(1)), 50))
    return default


def match_capability(
    question: str,
    slots: dict[str, Any] | None = None,
) -> CapabilityMatch | None:
    """Сопоставляет вопрос с capability только по явным признакам."""
    text = _normalise(question)
    year = _year(question, slots)

    if (
        (("без" in text and "скрипт" in text) or "без доказательств" in text)
        and ("пункт" in text or "акт" in text)
    ):
        return CapabilityMatch(
            CAPABILITIES["items_without_scripts"],
            {},
            "явная фраза «пункты без скриптов»",
        )

    if (
        "просроч" in text
        and ("пункт" in text or "открыт" in text)
        and ("покаж" in text or "какие" in text or "список" in text)
    ):
        return CapabilityMatch(
            CAPABILITIES["overdue_items"],
            {},
            "явная фраза «просроченные открытые пункты»",
        )

    if (
        "топ" in text
        and ("отклон" in text or "наход" in text)
        and ("вид" in text or "част" in text)
    ):
        return CapabilityMatch(
            CAPABILITIES["top_findings"],
            {
                "date_from": f"{year or config.DEFAULT_AS_OF_DATE.year}-01-01",
                "limit": _limit(question, 10),
            },
            "явная фраза «топ видов отклонений»",
        )

    if "динамик" in text and ("тем" in text or "год" in text):
        return CapabilityMatch(
            CAPABILITIES["theme_dynamics"],
            {},
            "явная фраза «динамика по темам/годам»",
        )

    if (
        ("сводк" in text or "покаж" in text)
        and "статус" in text
        and ("провер" in text or "аудит" in text)
    ):
        return CapabilityMatch(
            CAPABILITIES["status_summary"],
            {"year": year or config.DEFAULT_AS_OF_DATE.year},
            "явная фраза «сводка по статусам проверок»",
        )

    if "риск" in text and "карман" in text:
        return CapabilityMatch(
            CAPABILITIES["risk_by_pocket"],
            {},
            "явная фраза «риски по карманам»",
        )

    return None
