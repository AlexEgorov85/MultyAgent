"""Точка входа графов для LangGraph API server.

Сборка графов живёт в `src/graph/runtime.py`: `langgraph dev` импортирует
этот файл отдельно для каждого графа из `langgraph.json`, а тяжёлая
инициализация (PostgreSQL, LLM, эмбеддинги) должна произойти ровно один раз.
"""

from __future__ import annotations

from src.graph.runtime import get_admin_graph, get_main_graph


def graph(config=None):
    """Фабрика основного графа для langgraph.json."""
    return get_main_graph()


def admin_graph(config=None):
    """Фабрика служебного графа управления чатами."""
    return get_admin_graph()
