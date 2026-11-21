"""Одноразовая сборка графов, общая для всех фабрик LangGraph API.

`langgraph dev` импортирует файл с фабриками отдельно для каждого графа
из `langgraph.json`, поэтому один и тот же модуль может быть загружен под
разными именами (например, `src.graph.api` и `__src__graph__api`).
Сборка вынесена в отдельный модуль: он импортируется по абсолютному имени
и кэшируется в `sys.modules`, поэтому PostgreSQL и графы создаются ровно
один раз, сколько бы фабрик ни запросило API.

Сборка (включая запуск встроенного PostgreSQL через pgserver) —
синхронная и блокирующая. API-сервер вызывает фабрику внутри event loop,
где `langgraph dev` запрещает блокирующие вызовы, поэтому сборка выполняется
в отдельном потоке, а фабрики лишь дожидаются результата.

Ноды графа — обычные синхронные функции, LangGraph сам исполняет их
в threadpool, поэтому их обращения к БД и LLM под это ограничение не попадают.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from src import db_runtime
from src.graph.admin_graph import build_admin_graph
from src.graph.main_graph import build_main_graph
from src.llm import OpenAILLM
from src.rag.embeddings import OpenAIEmbeddings

logger = logging.getLogger(__name__)

_ready = threading.Event()
_result: dict[str, Any] = {}
_error: dict[str, BaseException] = {}
_start_lock = threading.Lock()
_started = False


def _start_db_server():
    try:
        return db_runtime.start_server(cleanup_mode=None)
    except Exception:
        # Предыдущий процесс могли завершить жёстко: postmaster остался
        # и держит каталог данных. Останавливаем его и пробуем ещё раз.
        if db_runtime.stop_server():
            return db_runtime.start_server(cleanup_mode=None)
        raise


def _prepare_database(server) -> None:
    """Применяет новые миграции и права при старте backend.

    Это делает обновление схемы (например, chat_history) бесшовным.
    Ошибка здесь не должна мешать запуску графа: история может быть
    недоступна, но остальные функции продолжат работать.
    """
    try:
        db_runtime.ensure_database(server)
        db_runtime.apply_migrations(server)
        db_runtime.ensure_roles(server)
    except Exception as exc:  # noqa: BLE001 - не ломаем старт графа
        logger.warning("Не удалось подготовить схему БД: %s", exc)


def _build_worker() -> None:
    try:
        logger.info("Сборка графа: запуск PostgreSQL")
        server = _start_db_server()
        logger.info("Сборка графа: PostgreSQL готов")
        _prepare_database(server)
        logger.info("Сборка графа: схема подготовлена")
        llm = OpenAILLM()
        embeddings = OpenAIEmbeddings()
        _result["graph"] = build_main_graph(server, llm, embeddings=embeddings)
        logger.info("Сборка графа: основной граф готов")
        _result["admin_graph"] = build_admin_graph(server)
        logger.info("Сборка графа: служебный граф готов")
    except BaseException as exc:  # noqa: BLE001 - пробрасываем в фабрику
        logger.exception("Сборка графа не удалась: %s", exc)
        _error["exc"] = exc
    finally:
        _ready.set()


def _start_build() -> None:
    """Запускает сборку один раз на процесс."""
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    threading.Thread(
        target=_build_worker,
        name="audit-graph-builder",
        daemon=True,
    ).start()


def _wait_result(key: str):
    _ready.wait()
    if "exc" in _error:
        raise _error["exc"]
    return _result[key]


def get_main_graph():
    """Основной граф ассистента аудитора."""
    _start_build()
    return _wait_result("graph")


def get_admin_graph():
    """Служебный граф управления чатами."""
    _start_build()
    return _wait_result("admin_graph")


# Прогреваем сборку сразу при импорте: сервер успевает поднять PostgreSQL
# и графы, пока LangGraph API завершает собственный старт.
_start_build()
