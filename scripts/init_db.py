"""Инициализация встроенного PostgreSQL и применение миграций.

Запуск:
    .venv\\Scripts\\python.exe scripts\\init_db.py [--reset] [--seed]

Скрипт поднимает PostgreSQL 16 через pgserver, создаёт базу `audit`,
применяет миграции из db/migrations и (опционально) загружает CSV из data/seed.

Особенность Windows: если путь к site-packages содержит не-ASCII символы
(например, C:\\Users\\Алексей\\...), initdb падает с
"invalid byte sequence for encoding UTF8". Поэтому установка PostgreSQL
копируется в ASCII-путь (%PUBLIC%\\audit-assistant-pg) и модули pgserver
перенаправляются на неё.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PGDATA = ROOT / "data" / "pg"
MIGRATIONS = ROOT / "db" / "migrations"
SEED = ROOT / "data" / "seed"

DB_NAME = "audit"
RO_DSN_FILE = ROOT / "data" / "pg" / "dsn_ro.txt"


def ensure_ascii_pg_install() -> None:
    """Копирует pginstall в ASCII-путь, если текущий путь содержит не-ASCII."""
    import pgserver
    import pgserver._commands as commands
    import pgserver.postgres_server as server_module

    src = Path(pgserver.__file__).parent / "pginstall"
    if str(src).isascii():
        return

    public = os.environ.get("PUBLIC") or r"C:\Users\Public"
    base = Path(public) / "audit-assistant-pg"
    dst = base / "pginstall-16.2"

    if not (dst / "bin" / "initdb.exe").exists():
        base.mkdir(parents=True, exist_ok=True)
        tmp = base / f"pginstall-{os.getpid()}"
        if tmp.exists():
            shutil.rmtree(tmp)
        print(f"[pg] копирую PostgreSQL в ASCII-путь: {dst}")
        shutil.copytree(src, tmp)
        if dst.exists():
            shutil.rmtree(dst)
        tmp.rename(dst)

    commands.POSTGRES_BIN_PATH = dst / "bin"
    server_module.POSTGRES_BIN_PATH = dst / "bin"


def start_server(reset: bool = False):
    import pgserver

    if reset and PGDATA.exists():
        for name in ("postmaster.pid",):
            pid_file = PGDATA / name
            if pid_file.exists():
                pid_file.unlink()
        shutil.rmtree(PGDATA)
        print("[pg] каталог данных удалён")

    PGDATA.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(PGDATA)
    print(f"[pg] сервер запущен: {server.get_uri()}")
    return server


def _admin_conn(server, dbname: str = "postgres", client_side: bool = False):
    import psycopg

    uri = server.get_uri(database=dbname)
    kwargs = {}
    if client_side:
        from psycopg import ClientCursor

        kwargs["cursor_factory"] = ClientCursor
    return psycopg.connect(uri, autocommit=True, **kwargs)


def ensure_database(server) -> None:
    with _admin_conn(server) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{DB_NAME}"')
            print(f"[db] создана база {DB_NAME}")


def apply_migrations(server) -> None:
    with _admin_conn(server, DB_NAME, client_side=True) as conn:
        for path in sorted(MIGRATIONS.glob("*.sql")):
            print(f"[db] применяю {path.name}")
            conn.execute(path.read_text(encoding="utf-8"))


def ensure_readonly_role(server) -> str:
    with _admin_conn(server, DB_NAME) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = 'audit_ro'"
        ).fetchone()
        if not exists:
            conn.execute("CREATE ROLE audit_ro LOGIN")
        conn.execute(f'GRANT CONNECT ON DATABASE "{DB_NAME}" TO audit_ro')
        conn.execute("GRANT USAGE ON SCHEMA audit TO audit_ro")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA audit TO audit_ro")
        conn.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA audit "
            "GRANT SELECT ON TABLES TO audit_ro"
        )
        conn.execute("ALTER ROLE audit_ro SET default_transaction_read_only = on")
        conn.execute("ALTER ROLE audit_ro SET statement_timeout = '5s'")
        conn.execute("ALTER ROLE audit_ro SET search_path = audit, public")

    dsn = server.get_uri(database=DB_NAME).replace("postgres:@", "audit_ro:@", 1)
    RO_DSN_FILE.parent.mkdir(parents=True, exist_ok=True)
    RO_DSN_FILE.write_text(dsn, encoding="utf-8")
    return dsn


TABLES = [
    ("audit.auditors", "auditor_id"),
    ("audit.audit_pockets", "pocket_id"),
    ("audit.audits", "audit_id"),
    ("audit.acts", "act_id"),
    ("audit.act_items", "item_id"),
    ("audit.scripts", "script_id"),
    ("audit.script_runs", "run_id"),
    ("audit.deviations", "deviation_id"),
    ("audit.script_templates", "template_id"),
    ("audit.auditor_memory", "auditor_id, memory_key"),
]


def load_seed(server) -> None:
    if not SEED.exists():
        print("[seed] каталог data/seed не найден — пропускаю")
        return

    with _admin_conn(server, DB_NAME) as conn:
        for table, _order_by in TABLES:
            csv_path = SEED / f"{table.split('.')[1]}.csv"
            if not csv_path.exists():
                continue
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                header = fh.readline().strip()
                fh.seek(0)
                sql = (
                    f"COPY {table} ({header}) FROM STDIN "
                    "WITH (FORMAT csv, HEADER true)"
                )
                with conn.cursor().copy(sql) as copy:
                    copy.write(fh.read())
            count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"[seed] {table}: {count} строк")


def main() -> int:
    parser = argparse.ArgumentParser(description="Инициализация БД проекта")
    parser.add_argument("--reset", action="store_true", help="удалить каталог data/pg")
    parser.add_argument("--seed", action="store_true", help="загрузить CSV из data/seed")
    args = parser.parse_args()

    ensure_ascii_pg_install()
    server = start_server(reset=args.reset)
    try:
        ensure_database(server)
        apply_migrations(server)
        dsn = ensure_readonly_role(server)
        if args.seed:
            load_seed(server)
        print("[ok] база готова")
        print(f"[ok] read-only DSN записан в {RO_DSN_FILE}")
        print(f"[ok] DSN: {dsn}")
    finally:
        server.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
