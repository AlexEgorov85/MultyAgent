"""Typed capabilities: готовые шаблоны и их deterministic matcher."""

from .registry import CAPABILITIES, Capability, CapabilityMatch, match_capability

__all__ = [
    "CAPABILITIES",
    "Capability",
    "CapabilityMatch",
    "match_capability",
]
