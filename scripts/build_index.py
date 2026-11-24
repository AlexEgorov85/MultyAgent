"""Построение RAG-индекса knowledge_chunks.

Запуск:
    .venv\\Scripts\\python.exe scripts\\build_index.py
    .venv\\Scripts\\python.exe scripts\\build_index.py --hash

--hash использует детерминированные офлайн-эмбеддинги (демо и тесты).
Модель записывается в audit.dataset_metadata, чтобы runtime использовал
для запросов ту же модель, что и при построении индекса.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config, db_runtime  # noqa: E402
from src.rag.embeddings import HashEmbeddings, OpenAIEmbeddings  # noqa: E402
from src.rag.ingest import build_index  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Построение RAG-индекса")
    parser.add_argument(
        "--hash",
        action="store_true",
        help="использовать офлайн-эмбеддинги вместо OpenAI",
    )
    parser.add_argument(
        "--knowledge-dir",
        type=Path,
        default=config.KNOWLEDGE_DIR,
    )
    args = parser.parse_args()

    embeddings = HashEmbeddings() if args.hash else OpenAIEmbeddings()
    model_name = "hash" if args.hash else str(
        getattr(embeddings, "model", "") or "openai"
    )
    server = db_runtime.start_server()
    try:
        # Индекс строится поверх актуальной схемы, даже если init_db.py
        # запускали до появления новых миграций.
        db_runtime.ensure_database(server)
        db_runtime.apply_migrations(server)
        db_runtime.ensure_roles(server)
        counts = build_index(server, embeddings, args.knowledge_dir)
        if counts:
            # Runtime выберет такую же модель для запросов.
            db_runtime.set_index_embedding_model(server, model_name)
    finally:
        server.cleanup()

    if not counts:
        print("[rag] нет чанков для индексации")
        return 1
    print(f"[rag] индекс построен (эмбеддинги: {model_name}):")
    for source_type, count in sorted(counts.items()):
        print(f"  {source_type}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
