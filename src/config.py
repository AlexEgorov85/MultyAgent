"""Конфигурация проекта: пути, имена БД и лимиты."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:  # .env не обязателен для тестов и офлайн-проверок
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover - отсутствие пакета не критично
    pass

DB_NAME = os.getenv("DB_NAME", "audit")
PGDATA_DIR = Path(os.getenv("PGDATA_DIR", ROOT / "data" / "pg"))
SEED_DIR = Path(os.getenv("SEED_DIR", ROOT / "data" / "seed"))
KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", ROOT / "data" / "knowledge"))
MIGRATIONS_DIR = ROOT / "db" / "migrations"

DEFAULT_AS_OF_DATE = date(2026, 11, 21)

MAX_ROWS = int(os.getenv("MAX_ROWS", "200"))
SQL_TIMEOUT_SEC = int(os.getenv("SQL_TIMEOUT_SEC", "5"))

# Лимит инструментов, которые Analytics-агент выполняет за один шаг плана.
MAX_AGENT_ITERATIONS = int(os.getenv("MAX_AGENT_ITERATIONS", "5"))
