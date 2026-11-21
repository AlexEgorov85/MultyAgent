"""Точка входа графа для LangGraph API server.

Граф создаётся лениво: сервер поднимается при первом запросе, а не при импорте.
Используются абсолютные импорты, потому что LangGraph загружает модуль как
отдельный файл, а не как часть пакета.
"""

from __future__ import annotations

from functools import lru_cache

from src import db_runtime
from src.graph.main_graph import build_main_graph
from src.llm import OpenAILLM
from src.rag.embeddings import OpenAIEmbeddings


@lru_cache(maxsize=1)
def _build():
    server = db_runtime.start_server(cleanup_mode=None)
    llm = OpenAILLM()
    embeddings = OpenAIEmbeddings()
    return build_main_graph(server, llm, embeddings=embeddings)


def graph(config=None):
    """Фабрика графа для langgraph.json."""
    return _build()
