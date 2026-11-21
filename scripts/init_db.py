"""Инициализация встроенного PostgreSQL и применение миграций.

Запуск:
    .venv\\Scripts\\python.exe scripts\\init_db.py [--seed] [--reset-db --yes]

Скрипт применяет только новые миграции (реестр public.schema_migrations),
создаёт роли audit_ro/audit_app и по флагу --seed идемпотентно загружает CSV.
Разрушающий сброс каталога данных возможен только через --reset-db --yes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config, db_runtime  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Инициализация БД проекта")
    parser.add_argument("--seed", action="store_true", help="загрузить CSV из data/seed")
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="удалить каталог data/pg (требует --yes)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="подтвердить разрушающий сброс",
    )
    args = parser.parse_args()

    if args.reset_db and not args.yes:
        print("[error] --reset-db удаляет все данные; добавьте --yes", file=sys.stderr)
        return 2

    if args.reset_db:
        db_runtime.reset_data_dir()
        print("[pg] каталог данных удалён")

    server = db_runtime.start_server()
    try:
        created = db_runtime.ensure_database(server)
        if created:
            print(f"[db] создана база {config.DB_NAME}")

        result = db_runtime.apply_migrations(server)
        for name in result.applied:
            print(f"[db] применена миграция {name}")
        if not result.applied:
            print(f"[db] новых миграций нет (пропущено {len(result.skipped)})")

        db_runtime.ensure_roles(server)
        print("[db] роли audit_ro и audit_app готовы")

        if args.seed:
            counts = db_runtime.seed_from_csv(server)
            for table, count in counts.items():
                print(f"[seed] {table}: {count} строк")
            meta = db_runtime.upsert_dataset_metadata(server)
            print(f"[seed] срез {meta['as_of_date']}, seed {meta['seed']}")

        print("[ok] база готова")
    finally:
        server.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
