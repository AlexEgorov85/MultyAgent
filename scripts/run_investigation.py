"""CLI-запуск расследования (A7)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db_runtime  # noqa: E402
from src.acl import make_acl_message  # noqa: E402
from src.graph.investigation_graph import build_investigation_graph  # noqa: E402
from src.llm import LLMError, OpenAILLM  # noqa: E402
from src.rag.embeddings import HashEmbeddings, OpenAIEmbeddings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Запуск расследования")
    parser.add_argument("--question", required=True)
    parser.add_argument("--auditor-id", default="AUD-001")
    parser.add_argument("--conversation-id", default="conv-inv-cli-001")
    parser.add_argument("--hash", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    try:
        llm = OpenAILLM()
    except LLMError as exc:
        print(f"[error] {exc}. Задайте OPENAI_API_KEY.", file=sys.stderr)
        return 2
    embeddings = HashEmbeddings() if args.hash else OpenAIEmbeddings()

    request = make_acl_message(
        performative="request",
        sender="orchestrator",
        receiver="investigation_coordinator",
        content={"question": args.question, "auditor_id": args.auditor_id},
        conversation_id=args.conversation_id,
    )

    server = db_runtime.start_server()
    try:
        graph = build_investigation_graph(
            server, llm, embeddings=embeddings
        )
        result = graph.invoke({"acl_request": request.model_dump()})
    finally:
        server.cleanup()

    response = result.get("acl_response", {})
    content = response.get("content", {})
    print(f"\nperformative: {response.get('performative')}")
    print(content.get("answer", result.get("error", "")))
    print("acl_rounds:", content.get("metrics", {}).get("acl_rounds"))
    print("causal_claim:", content.get("causal_claim"))
    if content.get("missing"):
        print("missing:", ", ".join(content["missing"]))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"JSON: {args.json}")
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
