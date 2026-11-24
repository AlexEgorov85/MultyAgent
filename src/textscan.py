"""Текстовые сканеры без регулярных выражений.

Регулярки в агенте остаются только как политика безопасности
(`guardrails`). Всё, что связано с разбором текста, ID, чисел и чанков,
живёт здесь и работает на обычных операциях со строками: это проще
тестировать и не создаёт скрытых «почти совпало».
"""

from __future__ import annotations

from typing import Iterable

_ID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789-_"
)
_ASCII_DIGITS = frozenset("0123456789")
_ASCII_LETTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def _is_ascii_alnum(char: str) -> bool:
    return char in _ASCII_DIGITS or char in _ASCII_LETTERS


def _is_ascii_id_char(char: str) -> bool:
    return _is_ascii_alnum(char) or char in "-_"


def tokens(text: str) -> list[str]:
    """Делит текст на токены из латиницы, цифр, дефиса и подчёркивания."""
    result: list[str] = []
    current: list[str] = []
    for char in text or "":
        if char in _ID_CHARS:
            current.append(char)
        elif current:
            result.append("".join(current))
            current = []
    if current:
        result.append("".join(current))
    return result


def _is_audit_code(token: str) -> bool:
    """`AUD-2025-MORTGAGE-03`: префикс, год, модуль, номер."""
    parts = token.split("-")
    if len(parts) != 4:
        return False
    prefix, year, module, number = parts
    return (
        prefix.upper() == "AUD"
        and len(year) == 4
        and all(char in _ASCII_DIGITS for char in year)
        and bool(module)
        and all(char in _ASCII_LETTERS for char in module)
        and len(number) == 2
        and all(char in _ASCII_DIGITS for char in number)
    )


def audit_codes(text: str) -> list[str]:
    """Все коды проверок в порядке появления."""
    return [
        token.upper() for token in tokens(text) if _is_audit_code(token)
    ]


def years(text: str) -> list[int]:
    """Годы 2000–2099 как отдельные четырёхзначные числа."""
    result: list[int] = []
    digits: list[str] = []
    for char in (text or "") + " ":
        if char in _ASCII_DIGITS:
            digits.append(char)
            continue
        if len(digits) == 4:
            value = int("".join(digits))
            if 2000 <= value <= 2099:
                result.append(value)
        digits = []
    return result


def number_tokens(text: str) -> list[str]:
    """Числа в тексте: цифры с необязательной дробной частью.

    Возвращает строки, потому что не каждое «число» приводится к float
    (например, номер пункта `5.1.2`).
    """
    result: list[str] = []
    current: list[str] = []
    has_separator = False
    raw = text or ""
    for index, char in enumerate(raw):
        if char in _ASCII_DIGITS:
            current.append(char)
            continue
        if (
            char in ".,"
            and current
            and not has_separator
            and index + 1 < len(raw)
            and raw[index + 1] in _ASCII_DIGITS
        ):
            current.append(".")
            has_separator = True
            continue
        if current:
            result.append("".join(current))
            current = []
            has_separator = False
    if current:
        result.append("".join(current))
    return result


def contains_id(text: str, value: str) -> bool:
    """Есть ли `value` отдельным ID, а не частью другого идентификатора."""
    haystack = (text or "").lower()
    needle = (value or "").lower()
    if not needle:
        return False
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index == -1:
            return False
        before = haystack[index - 1] if index > 0 else ""
        after_index = index + len(needle)
        after = haystack[after_index] if after_index < len(haystack) else ""
        if not (before and _is_ascii_id_char(before)) and not (
            after and _is_ascii_id_char(after)
        ):
            return True
        start = index + 1


def reference_ids(
    text: str,
    prefixes: Iterable[str] = (),
) -> list[str]:
    """ID-подобные токены: `AUD-...`, `ITM-...`, `ACT-...`.

    Если заданы `prefixes`, берутся только они; иначе — любой заголовок
    из 2–4 латинских букв. Тело ID должно состоять из латиницы и цифр.
    """
    allowed = {prefix.upper() for prefix in prefixes}
    result: list[str] = []
    for token in tokens(text):
        parts = token.split("-")
        if len(parts) < 2 or not all(parts):
            continue
        head = parts[0].upper()
        if allowed:
            if head not in allowed:
                continue
        elif not (2 <= len(head) <= 4 and head.isalpha() and head.isupper()):
            continue
        if all(all(_is_ascii_alnum(char) for char in part) for part in parts[1:]):
            result.append(token.upper())
    return result


def strip_bracketed_numbers(text: str) -> str:
    """Убирает сноски вида `[1]`, `[12]`."""
    raw = text or ""
    result: list[str] = []
    index = 0
    while index < len(raw):
        if raw[index] == "[":
            end = index + 1
            while end < len(raw) and raw[end] in _ASCII_DIGITS:
                end += 1
            if end > index + 1 and end < len(raw) and raw[end] == "]":
                index = end + 1
                continue
        result.append(raw[index])
        index += 1
    return "".join(result)


def words(text: str) -> list[str]:
    """Слова из букв и цифр любого алфавита (для офлайн-эмбеддингов)."""
    result: list[str] = []
    current: list[str] = []
    for char in text or "":
        if char.isalnum():
            current.append(char)
        elif current:
            result.append("".join(current))
            current = []
    if current:
        result.append("".join(current))
    return result


def paragraphs(text: str) -> list[str]:
    """Абзацы: группы непустых строк, разделённые пустой строкой."""
    result: list[str] = []
    current: list[str] = []
    for line in (text or "").splitlines():
        if line.strip():
            current.append(line)
        elif current:
            result.append("\n".join(current).strip())
            current = []
    if current:
        result.append("\n".join(current).strip())
    return [part for part in result if part]


def sentences(text: str) -> list[str]:
    """Предложения: разрез после `.`, `!`, `?`, если дальше пробел."""
    raw = text or ""
    result: list[str] = []
    current: list[str] = []
    for index, char in enumerate(raw):
        current.append(char)
        if (
            char in ".!?"
            and index + 1 < len(raw)
            and raw[index + 1].isspace()
        ):
            part = "".join(current).strip()
            if part:
                result.append(part)
            current = []
    tail = "".join(current).strip()
    if tail:
        result.append(tail)
    return result
