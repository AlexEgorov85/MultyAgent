"""Конфигурация проекта: пути, имена БД и лимиты."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DB_NAME = os.getenv("DB_NAME", "audit")
PGDATA_DIR = Path(os.getenv("PGDATA_DIR", ROOT / "data" / "pg"))
SEED_DIR = Path(os.getenv("SEED_DIR", ROOT / "data" / "seed"))
KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", ROOT / "data" / "knowledge"))
MIGRATIONS_DIR = ROOT / "db" / "migrations"

DEFAULT_AS_OF_DATE = date(2026, 11, 21)

MAX_ROWS = int(os.getenv("MAX_ROWS", "200"))
SQL_TIMEOUT_SEC = int(os.getenv("SQL_TIMEOUT_SEC", "5"))
