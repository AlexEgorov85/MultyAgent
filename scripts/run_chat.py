"""Интерактивный чат с основным графом (CLI)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db_runtime  # noqa: E402
from src.graph.main_graph import build_main_graph  # noqa: E402
from src.llm import LLMError, OpenAILLM  # noqa: E402
from src.rag.embeddings import OpenAIEmbeddings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Чат с ассистентом аудитора")
    parser.add_argument("--auditor-id", default="AUD-001")
    parser.add_argument("--thread-id", default="thread-cli-001")
    args = parser.parse_args()

    try:
        llm = OpenAILLM()
        embeddings = OpenAIEmbeddings()
    except Exception as exc:
        print(f"[error] LLM недоступна: {exc}. Задайте OPENAI_API_KEY.", file=sys.stderr)
        return 2

    server = db_runtime.start_server()
    try:
        graph = build_main_graph(server, llm, embeddings=embeddings)
        config = {"configurable": {"thread_id": args.thread_id}}
        print(
            f"Аудитор: {args.auditor_id}, нить: {args.thread_id}. "
            "Введите вопрос или /exit."
        )
        while True:
            try:
                text = input("\nВы: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            if text in ("/exit", "/quit"):
                break
            result = graph.invoke(
                {
                    "messages": [{"role": "user", "content": text}],
                    "auditor_id": args.auditor_id,
                    "conversation_id": args.thread_id,
                },
                config=config,
            )
            print(f"\nАссистент: {result.get('final_answer', '')}")
    finally:
        server.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
