"""CLI-запуск Analytics-агента.

Нужен OPENAI_API_KEY (и при необходимости OPENAI_BASE_URL).

Пример:
    .venv\\Scripts\\python.exe scripts\\run_analytics.py ^
        --question "Сколько завершённых проверок по ипотеке в 2026 году?"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db_runtime  # noqa: E402
from src.acl import make_acl_message  # noqa: E402
from src.graph.analytics_graph import build_analytics_graph  # noqa: E402
from src.llm import LLMError, OpenAILLM  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Запуск Analytics-агента")
    parser.add_argument("--question", required=True, help="вопрос аудитора")
    parser.add_argument("--auditor-id", default="AUD-001")
    parser.add_argument("--conversation-id", default="conv-cli-001")
    parser.add_argument("--json", type=Path, help="сохранить результат в JSON")
    args = parser.parse_args()

    try:
        llm = OpenAILLM()
    except LLMError as exc:
        print(f"[error] {exc}. Задайте OPENAI_API_KEY в .env или окружении.", file=sys.stderr)
        return 2

    request = make_acl_message(
        performative="request",
        sender="orchestrator",
        receiver="analytics_agent",
        content={"question": args.question, "auditor_id": args.auditor_id},
        conversation_id=args.conversation_id,
    )

    server = db_runtime.start_server()
    try:
        graph = build_analytics_graph(server, llm)
        result = graph.invoke({"acl_request": request.model_dump()})
    finally:
        server.cleanup()

    response = result.get("acl_response", {})
    content = response.get("content", {})
    print(f"\nperformative: {response.get('performative')}")
    print(f"answer: {content.get('answer', result.get('error', ''))}")
    if content.get("sql"):
        print(f"\nSQL:\n{content['sql']}")
    if content.get("rows"):
        print(f"\nстрок: {len(content['rows'])}")
        for row in content["rows"][:10]:
            print("  ", row)
    if content.get("evidence"):
        print("\nevidence:", json.dumps(content["evidence"], ensure_ascii=False))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\nJSON: {args.json}")
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
