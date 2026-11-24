"""Гибридный поиск по knowledge_chunks: pgvector + русский FTS."""

from __future__ import annotations

from typing import Any

from .. import telemetry

from .. import db_runtime

RRF_K = 60
MIN_VECTOR_SCORE = 0.2


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _fts(server, query: str, limit: int) -> list[dict[str, Any]]:
    with db_runtime.connect(server, role=db_runtime.READ_ONLY_ROLE) as conn:
        rows = conn.execute(
            "SELECT chunk_id, source_type, source_id, title, content, "
            "ts_rank(to_tsvector('russian', title || ' ' || content), "
            "        plainto_tsquery('russian', %s)) AS score "
            "FROM audit.knowledge_chunks "
            "WHERE to_tsvector('russian', title || ' ' || content) "
            "      @@ plainto_tsquery('russian', %s) "
            "ORDER BY score DESC LIMIT %s",
            (query, query, limit),
        ).fetchall()
        if not rows:
            # plainto_tsquery требует все слова сразу: длинный вопрос
            # («какие сроки устранения установлены...») не находит ничего,
            # хотя каждый термин в базе есть. Повторяем поиск по OR.
            lexemes_row = conn.execute(
                "SELECT array_to_string("
                "tsvector_to_array(to_tsvector('russian', %s)), ' | ')",
                (query,),
            ).fetchone()
            lexemes = str(lexemes_row[0] or "") if lexemes_row else ""
            if lexemes:
                # Лексемы уже нормализованы словарём. Приводим их к tsquery
                # напрямую (`::tsquery`), иначе повторное применение
                # to_tsquery('russian', …) стеммит их второй раз
                # («отклонен» → «отклон») и совпадений не остаётся.
                rows = conn.execute(
                    "SELECT chunk_id, source_type, source_id, title, content, "
                    "ts_rank(to_tsvector('russian', title || ' ' || content), "
                    "        %s::tsquery) AS score "
                    "FROM audit.knowledge_chunks "
                    "WHERE to_tsvector('russian', title || ' ' || content) "
                    "      @@ %s::tsquery "
                    "ORDER BY score DESC LIMIT %s",
                    (lexemes, lexemes, limit),
                ).fetchall()
    return [
        {
            "chunk_id": row[0],
            "source_type": row[1],
            "source_id": row[2],
            "title": row[3],
            "content": row[4],
            "score": float(row[5] or 0),
        }
        for row in rows
    ]


def _vector(server, query: str, embeddings, limit: int) -> list[dict[str, Any]]:
    vector = _vector_literal(embeddings.embed([query])[0])
    with db_runtime.connect(server, role=db_runtime.READ_ONLY_ROLE) as conn:
        rows = conn.execute(
            "SELECT chunk_id, source_type, source_id, title, content, "
            "1 - (embedding <=> %s::vector) AS score "
            "FROM audit.knowledge_chunks "
            "WHERE embedding IS NOT NULL "
            "  AND 1 - (embedding <=> %s::vector) >= %s "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (vector, vector, MIN_VECTOR_SCORE, vector, limit),
        ).fetchall()
    return [
        {
            "chunk_id": row[0],
            "source_type": row[1],
            "source_id": row[2],
            "title": row[3],
            "content": row[4],
            "score": float(row[5] or 0),
        }
        for row in rows
    ]


@telemetry.timed_tool("search_act_items")
def search(
    server,
    query: str,
    embeddings=None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Ищет чанки; при наличии embeddings объединяет векторный и FTS-поиск."""
    if not query.strip():
        return {"chunks": [], "mode": "empty"}

    candidates = max(top_k * 4, 20)
    lexical = _fts(server, query, candidates)
    mode = "fts"

    semantic: list[dict[str, Any]] = []
    if embeddings is not None:
        try:
            semantic = _vector(server, query, embeddings, candidates)
            if semantic:
                mode = "hybrid"
        except Exception:
            semantic = []

    if not semantic:
        return {"chunks": lexical[:top_k], "mode": mode}

    scores: dict[str, float] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for rank, item in enumerate(semantic, start=1):
        scores[item["chunk_id"]] = scores.get(item["chunk_id"], 0) + 1 / (RRF_K + rank)
        by_id[item["chunk_id"]] = item
    for rank, item in enumerate(lexical, start=1):
        scores[item["chunk_id"]] = scores.get(item["chunk_id"], 0) + 1 / (RRF_K + rank)
        by_id.setdefault(item["chunk_id"], item)

    ranked = sorted(scores, key=scores.get, reverse=True)[:top_k]
    return {
        "chunks": [{**by_id[chunk_id], "score": scores[chunk_id]} for chunk_id in ranked],
        "mode": mode,
    }
