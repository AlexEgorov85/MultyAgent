"""Проверки реестра Markdown-промптов и их индивидуальных версий."""

from __future__ import annotations

import re

import pytest

from src.prompts import (
    PROMPTS_DIR,
    PromptFormatError,
    format_guide,
    format_guide_meta,
    load_prompt,
    load_prompt_meta,
    prompt_meta,
    prompt_version,
    prompt_versions,
)
from src.schemas import Route

FORMAT_KINDS = [
    "count",
    "scalar",
    "table_summary",
    "table",
    "items",
    "tools",
    "retrieval",
    "report",
    "investigation",
    "smalltalk",
]


def _prompt_files() -> list[str]:
    return sorted(
        path.relative_to(PROMPTS_DIR).with_suffix("").as_posix()
        for path in PROMPTS_DIR.rglob("*.md")
    )


def test_every_prompt_has_individual_version_and_hash():
    names = _prompt_files()
    assert names
    for name in names:
        prompt = load_prompt_meta(name)
        assert prompt.version >= 1
        assert prompt.name == name
        assert re.fullmatch(r"[0-9a-f]{12}", prompt.hash)
        assert prompt.text
        assert not prompt.text.startswith("---")


def test_prompt_versions_covers_all_files():
    names = set(_prompt_files())
    versions = prompt_versions()
    assert set(versions) == names
    assert all(version >= 1 for version in versions.values())


def test_each_prompt_loads_by_discovered_name():
    for name in _prompt_files():
        assert load_prompt(name)
        assert prompt_meta(name)["id"] == name


def test_router_prompt_mentions_every_route():
    text = load_prompt("router").lower()
    for route in Route.__args__:
        assert route in text


def test_router_prompt_describes_analytics_modes():
    text = load_prompt("router")
    for mode in ("sql", "drilldown", "multi_tool"):
        assert mode in text


def test_format_guides_are_built_from_versioned_prompts():
    for kind in FORMAT_KINDS:
        guide = format_guide(kind)
        assert guide
        meta = format_guide_meta(kind)
        assert "format/common" in meta
        assert all(version >= 1 for version in meta.values())


def test_unknown_format_uses_default():
    guide = format_guide("unknown-kind")
    assert "Дай короткий связный ответ" in guide


def test_missing_prompt_is_reported():
    with pytest.raises(FileNotFoundError):
        load_prompt("no_such_prompt")


def test_prompt_without_front_matter_is_rejected(tmp_path):
    path = tmp_path / "broken.md"
    path.write_text("Просто текст без версии.", encoding="utf-8")
    from src.prompts import _parse_front_matter

    with pytest.raises(PromptFormatError):
        _parse_front_matter(path.read_text(encoding="utf-8"), path)


def test_prompt_version_is_individual():
    """Версия читается из front matter конкретного файла."""
    router = load_prompt_meta("router")
    summarize = load_prompt_meta("analytics_summarize")
    assert router.version == prompt_version("router")
    assert summarize.version == prompt_version("analytics_summarize")
    assert router.path.name == "router.md"
    assert summarize.path.name == "analytics_summarize.md"
