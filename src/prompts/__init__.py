"""Реестр промптов: статические инструкции — в Markdown, данные — в коде.

Каждый промпт лежит отдельным файлом с front matter:

    ---
    id: router
    version: 1
    ---

Версия индивидуальная: изменили `router.md` — поднимите `version` только
у него. Динамические значения (вопрос, профиль, схема, фрагменты, строки
результата) остаются в user-сообщениях в `llm.py`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .. import telemetry

PROMPTS_DIR = Path(__file__).resolve().parent

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


class PromptFormatError(ValueError):
    """У Markdown-промпта нет корректного front matter."""


@dataclass(frozen=True)
class Prompt:
    """Загруженный промпт с метаданными."""

    name: str
    version: int
    text: str
    path: Path
    hash: str


def _parse_front_matter(raw: str, path: Path) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER_RE.match(raw)
    if not match:
        raise PromptFormatError(
            f"Prompt {path.name} has no front matter with id and version"
        )
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise PromptFormatError(
                f"Prompt {path.name} has invalid front matter line: {line!r}"
            )
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    body = raw[match.end() :].strip()
    return meta, body


@lru_cache(maxsize=None)
def _load(name: str) -> Prompt:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt not found: {path}")

    raw = path.read_text(encoding="utf-8")
    meta, text = _parse_front_matter(raw, path)

    prompt_id = meta.get("id", name)
    if prompt_id != name:
        raise PromptFormatError(
            f"Prompt {path.name}: id={prompt_id!r}, expected {name!r}"
        )

    try:
        version = int(meta["version"])
    except (KeyError, ValueError) as exc:
        raise PromptFormatError(
            f"Prompt {path.name}: version must be a positive integer"
        ) from exc
    if version < 1:
        raise PromptFormatError(
            f"Prompt {path.name}: version must be a positive integer"
        )
    if not text:
        raise PromptFormatError(f"Prompt {path.name}: body is empty")

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return Prompt(name=name, version=version, text=text, path=path, hash=digest)


def load_prompt_meta(name: str) -> Prompt:
    """Возвращает промпт вместе с версией и хэшем."""
    prompt = _load(name)
    telemetry.record_prompt(prompt.name, prompt.version, prompt.hash)
    return prompt


def load_prompt(name: str) -> str:
    """Возвращает только текст промпта без front matter."""
    prompt = _load(name)
    telemetry.record_prompt(prompt.name, prompt.version, prompt.hash)
    return prompt.text


def prompt_version(name: str) -> int:
    return _load(name).version


def prompt_meta(name: str) -> dict[str, str | int]:
    prompt = _load(name)
    return {
        "id": prompt.name,
        "version": prompt.version,
        "hash": prompt.hash,
    }


def prompt_versions() -> dict[str, int]:
    """Все промпты и их версии — для логов и проверок."""
    result: dict[str, int] = {}
    for path in sorted(PROMPTS_DIR.rglob("*.md")):
        name = path.relative_to(PROMPTS_DIR).with_suffix("").as_posix()
        result[name] = _load(name).version
    return result


@lru_cache(maxsize=None)
def _format_rule(kind: str) -> str:
    path = PROMPTS_DIR / "format" / f"{kind}.md"
    if not path.is_file():
        return ""
    return _load(f"format/{kind}").text


def format_guide(kind: str) -> str:
    """Инструкция по формату для конкретного типа ответа."""
    common = load_prompt("format/common")
    rule = _format_rule(kind)
    if not rule:
        return f"{common} {load_prompt('format/default')}"
    prompt = _load(f"format/{kind}")
    telemetry.record_prompt(prompt.name, prompt.version, prompt.hash)
    return f"{common}\n\n{rule}"


def format_guide_meta(kind: str) -> dict[str, int]:
    """Версии промптов, из которых собран формат ответа."""
    rule_name = f"format/{kind}"
    if not (PROMPTS_DIR / "format" / f"{kind}.md").is_file():
        rule_name = "format/default"
    return {
        "format/common": prompt_version("format/common"),
        rule_name: prompt_version(rule_name),
    }
