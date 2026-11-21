"""Построение RAG-индекса knowledge_chunks.

Запуск:
    .venv\\Scripts\\python.exe scripts\\build_index.py
    .venv\\Scripts\\python.exe scripts\\build_index.py --hash

--hash использует детерминированные офлайн-эмбеддинги (демо и тесты).
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
    server = db_runtime.start_server()
    try:
        counts = build_index(server, embeddings, args.knowledge_dir)
    finally:
        server.cleanup()

    if not counts:
        print("[rag] нет чанков для индексации")
        return 1
    print("[rag] индекс построен:")
    for source_type, count in sorted(counts.items()):
        print(f"  {source_type}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
