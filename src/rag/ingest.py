"""Чанкинг источников и построение индекса knowledge_chunks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .. import db_runtime
from ..textscan import paragraphs, sentences

MAX_CHARS = 1200
ITEM_FIELDS = (
    "title",
    "test_description",
    "criterion",
    "condition",
    "cause",
    "effect",
    "recommendation",
)


def _split_long(text: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for sentence in sentences(text):
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                parts.append(current)
            while len(sentence) > max_chars:
                parts.append(sentence[:max_chars])
                sentence = sentence[max_chars:]
            current = sentence
    if current:
        parts.append(current)
    return parts


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Делит документ на смысловые чанки по абзацам и предложениям."""
    paragraphs_list = paragraphs(text)
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs_list:
        pieces = (
            [paragraph]
            if len(paragraph) <= max_chars
            else _split_long(paragraph, max_chars)
        )
        for piece in pieces:
            if not current:
                current = piece
            elif len(current) + len(piece) + 2 <= max_chars:
                current = f"{current}\n\n{piece}"
            else:
                chunks.append(current)
                current = piece
    if current:
        chunks.append(current)
    return chunks


def collect_chunks(server, knowledge_dir: Path | str) -> list[dict[str, Any]]:
    """Собирает чанки методичек, пунктов и актов."""
    chunks: list[dict[str, Any]] = []

    directory = Path(knowledge_dir)
    if directory.exists():
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            for index, part in enumerate(chunk_text(text)):
                chunks.append(
                    {
                        "chunk_id": f"kn:{path.stem}:{index}",
                        "source_type": "методика",
                        "source_id": path.name,
                        "title": path.stem.replace("_", " "),
                        "content": part,
                    }
                )

    with db_runtime.connect(server, role=db_runtime.READ_ONLY_ROLE) as conn:
        items = conn.execute(
            "SELECT i.item_id, i.item_number, i.title, i.test_description, "
            "i.criterion, i.condition, i.cause, i.effect, i.recommendation, "
            "a.audit_code "
            "FROM audit.act_items i "
            "JOIN audit.acts ac ON ac.act_id = i.act_id "
            "JOIN audit.audits a ON a.audit_id = ac.audit_id "
            "ORDER BY i.item_id"
        ).fetchall()
        acts = conn.execute(
            "SELECT ac.act_id, ac.act_number, ac.summary, ac.full_text, "
            "a.audit_code "
            "FROM audit.acts ac "
            "JOIN audit.audits a ON a.audit_id = ac.audit_id "
            "ORDER BY ac.act_id"
        ).fetchall()

    for row in items:
        (
            item_id,
            number,
            title,
            test,
            criterion,
            condition,
            cause,
            effect,
            recommendation,
            audit_code,
        ) = row
        content = "\n".join(
            [
                f"Пункт {number}: {title}",
                f"Проверка {audit_code}.",
                f"Тест: {test}",
                f"Критерий: {criterion or ''}",
                f"Условие: {condition or ''}",
                f"Причина: {cause or ''}",
                f"Следствие: {effect or ''}",
                f"Рекомендация: {recommendation or ''}",
            ]
        )
        chunks.append(
            {
                "chunk_id": f"itm:{item_id}",
                "source_type": "пункт",
                "source_id": item_id,
                "title": title,
                "content": content,
            }
        )

    for act_id, act_number, summary, full_text, audit_code in acts:
        text = (full_text or "").strip() or (summary or "").strip()
        if not text:
            continue
        for index, part in enumerate(chunk_text(text)):
            chunks.append(
                {
                    "chunk_id": f"act:{act_id}:{index}",
                    "source_type": "акт",
                    "source_id": act_id,
                    "title": f"Акт {act_number} ({audit_code})",
                    "content": part,
                }
            )

    return chunks


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def build_index(
    server,
    embeddings,
    knowledge_dir: Path | str,
    batch_size: int = 32,
    rebuild: bool = True,
) -> dict[str, int]:
    """Строит индекс заново; при rebuild=False обновляет существующие чанки."""
    chunks = collect_chunks(server, knowledge_dir)
    if not chunks:
        return {}

    with db_runtime.connect(server) as conn:
        if rebuild:
            conn.execute("TRUNCATE audit.knowledge_chunks")
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = embeddings.embed([item["content"] for item in batch])
            if len(vectors) != len(batch):
                raise RuntimeError("Число эмбеддингов не совпало с числом чанков")
            for item, vector in zip(batch, vectors):
                conn.execute(
                    "INSERT INTO audit.knowledge_chunks "
                    "(chunk_id, source_type, source_id, title, content, embedding) "
                    "VALUES (%s, %s, %s, %s, %s, %s::vector) "
                    "ON CONFLICT (chunk_id) DO UPDATE "
                    "SET source_type = EXCLUDED.source_type, "
                    "    source_id = EXCLUDED.source_id, "
                    "    title = EXCLUDED.title, "
                    "    content = EXCLUDED.content, "
                    "    embedding = EXCLUDED.embedding",
                    (
                        item["chunk_id"],
                        item["source_type"],
                        item["source_id"],
                        item["title"],
                        item["content"],
                        _vector_literal(vector),
                    ),
                )

    counts: dict[str, int] = {}
    for item in chunks:
        counts[item["source_type"]] = counts.get(item["source_type"], 0) + 1
    return counts


def clear_index(server) -> None:
    """Очищает таблицу чанков перед полной перестройкой индекса."""
    with db_runtime.connect(server) as conn:
        conn.execute("TRUNCATE audit.knowledge_chunks")


def iter_chunks(server) -> Iterable[dict[str, Any]]:
    """Потоково отдаёт чанки индекса для эмбеддингов и проверок."""
    with db_runtime.connect(server, role=db_runtime.READ_ONLY_ROLE) as conn:
        rows = conn.execute(
            "SELECT chunk_id, source_type, source_id, title, content "
            "FROM audit.knowledge_chunks ORDER BY chunk_id"
        ).fetchall()
    for chunk_id, source_type, source_id, title, content in rows:
        yield {
            "chunk_id": chunk_id,
            "source_type": source_type,
            "source_id": source_id,
            "title": title,
            "content": content,
        }
