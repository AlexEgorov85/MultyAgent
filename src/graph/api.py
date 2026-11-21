"""Точка входа графа для LangGraph API server.

Сборка графа (включая запуск встроенного PostgreSQL через pgserver) —
синхронная и блокирующая. API-сервер вызывает фабрику внутри event loop,
где `langgraph dev` запрещает блокирующие вызовы, поэтому сборка выполняется
в отдельном потоке, а фабрика лишь дожидается результата.

Ноды графа — обычные синхронные функции, LangGraph сам исполняет их
в threadpool, поэтому их обращения к БД и LLM под это ограничение не попадают.
"""

from __future__ import annotations

import threading
from typing import Any

from src import db_runtime
from src.graph.main_graph import build_main_graph
from src.llm import OpenAILLM
from src.rag.embeddings import OpenAIEmbeddings

_ready = threading.Event()
_result: dict[str, Any] = {}
_error: dict[str, BaseException] = {}


def _start_db_server():
    try:
        return db_runtime.start_server(cleanup_mode=None)
    except Exception:
        # Предыдущий процесс могли завершить жёстко: postmaster остался
        # и держит каталог данных. Останавливаем его и пробуем ещё раз.
        if db_runtime.stop_server():
            return db_runtime.start_server(cleanup_mode=None)
        raise


def _build_worker() -> None:
    try:
        server = _start_db_server()
        llm = OpenAILLM()
        embeddings = OpenAIEmbeddings()
        _result["graph"] = build_main_graph(server, llm, embeddings=embeddings)
    except BaseException as exc:  # noqa: BLE001 - пробрасываем в фабрику
        _error["exc"] = exc
    finally:
        _ready.set()


threading.Thread(
    target=_build_worker,
    name="audit-graph-builder",
    daemon=True,
).start()


def graph(config=None):
    """Фабрика графа для langgraph.json."""
    _ready.wait()
    if "exc" in _error:
        raise _error["exc"]
    return _result["graph"]
