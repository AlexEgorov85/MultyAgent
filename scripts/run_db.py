"""Запуск PostgreSQL для ручного исследования базы.

Запуск:
    .venv\\Scripts\\python.exe scripts\\run_db.py
    .venv\\Scripts\\python.exe scripts\\run_db.py --seconds 5

Скрипт поднимает сервер, применяет миграции и роли, печатает DSN и держит
процесс живым до Ctrl+C (или до истечения --seconds). Данные сохраняются
в data/pg после остановки.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config, db_runtime  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Живой PostgreSQL для разработки")
    parser.add_argument(
        "--seconds",
        type=int,
        default=0,
        help="остановиться через N секунд (0 — ждать Ctrl+C)",
    )
    args = parser.parse_args()

    server = db_runtime.start_server()
    try:
        db_runtime.ensure_database(server)
        result = db_runtime.apply_migrations(server)
        if result.applied:
            print(f"[db] применено миграций: {len(result.applied)}")
        db_runtime.ensure_roles(server)

        print("\nPostgreSQL запущен. DSN:")
        print(f"  admin: {db_runtime.data_uri(server)}")
        print(f"  ro:    {db_runtime.data_uri(server, db_runtime.READ_ONLY_ROLE)}")
        print(f"  app:   {db_runtime.data_uri(server, db_runtime.APP_ROLE)}")
        print(f"\nБаза: {config.DB_NAME}. Ctrl+C — остановить.\n")

        if args.seconds:
            time.sleep(args.seconds)
        else:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        print("\n[pg] остановка по Ctrl+C")
    finally:
        server.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
