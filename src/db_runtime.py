"""Жизненный цикл PostgreSQL, миграции, роли и загрузка seed.

Модуль реализует спецификацию `data-platform`:
- встроенный PostgreSQL через pgserver;
- реестр миграций с checksum в public.schema_migrations;
- разделение ролей audit_ro / audit_app;
- идемпотентная загрузка CSV;
- обход ошибки initdb при кириллическом пути.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from . import config

READ_ONLY_ROLE = "audit_ro"
APP_ROLE = "audit_app"
ADMIN_ROLE = "postgres"


class MigrationError(RuntimeError):
    """Миграция не может быть применена или изменена."""


class SeedChecksumError(RuntimeError):
    """CSV-файлы не соответствуют checksum из manifest.json."""


@dataclass(frozen=True)
class MigrationResult:
    applied: list[str]
    skipped: list[str]


# Порядок важен для загрузки из-за внешних ключей.
SEED_TABLES: tuple[str, ...] = (
    "audit.auditors",
    "audit.audit_pockets",
    "audit.audits",
    "audit.acts",
    "audit.act_items",
    "audit.scripts",
    "audit.script_runs",
    "audit.deviations",
    "audit.script_templates",
    "audit.auditor_memory",
)


def ensure_ascii_pg_install() -> Path | None:
    """Копирует pginstall в ASCII-путь, если текущий путь содержит не-ASCII.

    Возвращает путь к bin, если было выполнено перенаправление, иначе None.
    """
    import pgserver
    import pgserver._commands as commands
    import pgserver.postgres_server as server_module

    src = Path(pgserver.__file__).parent / "pginstall"
    if str(src).isascii():
        return None

    public = os.environ.get("PUBLIC") or r"C:\Users\Public"
    dst = Path(public) / "audit-assistant-pg" / "pginstall-16.2"
    marker = dst / "bin" / "initdb.exe"

    if not marker.exists():
        base = dst.parent
        base.mkdir(parents=True, exist_ok=True)
        tmp = base / f"pginstall-{os.getpid()}"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(src, tmp)
        if dst.exists():
            shutil.rmtree(dst)
        tmp.rename(dst)

    commands.POSTGRES_BIN_PATH = dst / "bin"
    server_module.POSTGRES_BIN_PATH = dst / "bin"
    return dst / "bin"


def start_server(pgdata: Path | str | None = None, cleanup_mode: str | None = "stop"):
    """Запускает (или подключается к) PostgreSQL и возвращает handle."""
    import pgserver
    import pgserver.postgres_server as server_module

    ensure_ascii_pg_install()
    path = Path(pgdata or config.PGDATA_DIR)
    path.mkdir(parents=True, exist_ok=True)
    try:
        return pgserver.get_server(path, cleanup_mode=cleanup_mode)
    except Exception:
        # pgserver кладёт экземпляр в кэш ДО успешного старта. Если старт
        # упал (например, таймаут восстановления после жёсткого завершения),
        # в кэше остаётся handle с _postmaster_info=None, и все последующие
        # вызовы падают с AssertionError. Убираем его, чтобы retry создал новый.
        server_module.PostgresServer._instances.pop(path.resolve(), None)
        raise


def stop_server(
    pgdata: Path | str | None = None,
    *,
    mode: str = "fast",
    timeout: int = 30,
) -> bool:
    """Останавливает postmaster, оставшийся от аварийно завершённого процесса.

    Нужен после `taskkill /F`: `atexit`-очистка pgserver не выполняется,
    сервер продолжает держать каталог данных, и следующий запуск падает
    по таймауту `pg_ctl start`. Возвращает True, если сервер остановлен.
    """
    import pgserver._commands as commands

    ensure_ascii_pg_install()
    path = Path(pgdata or config.PGDATA_DIR)
    if not path.exists():
        return False
    for stop_mode in (mode, "immediate"):
        try:
            commands.pg_ctl(["-w", "-m", stop_mode, "stop"], pgdata=path, timeout=timeout)
            return True
        except Exception:  # noqa: BLE001 - сервер мог уже остановиться
            continue
    return False


def data_uri(server, role: str = ADMIN_ROLE, database: str | None = None) -> str:
    """Возвращает актуальный DSN для роли на текущем порту сервера."""
    # pgserver кэширует handle. После неудачного старта/перезапуска в кэше
    # может остаться объект с _postmaster_info=None. Тогда get_uri() падает
    # с AssertionError. Перечитываем postmaster.pid и восстанавливаем handle.
    if getattr(server, "_postmaster_info", None) is None:
        ensure = getattr(server, "ensure_postgres_running", None)
        if ensure is not None:
            ensure()
    uri = server.get_uri(database=database or config.DB_NAME)
    if role == ADMIN_ROLE:
        return uri
    prefix = f"{ADMIN_ROLE}:@"
    if prefix not in uri:
        raise RuntimeError(f"Неожиданный формат DSN: {uri}")
    return uri.replace(prefix, f"{role}:@", 1)


def connect(
    server,
    *,
    role: str = ADMIN_ROLE,
    database: str | None = None,
    autocommit: bool = True,
    client_side: bool = False,
):
    """Открывает соединение psycopg с указанной ролью.

    Если pgserver-объект хранит устаревший порт (после перезапуска
    PostgreSQL), первое подключение падает. Тогда перечитываем
    postmaster.pid и повторяем один раз.
    """
    import psycopg

    kwargs: dict = {"autocommit": autocommit}
    if client_side:
        from psycopg import ClientCursor

        kwargs["cursor_factory"] = ClientCursor

    def _open():
        return psycopg.connect(data_uri(server, role, database), **kwargs)

    try:
        return _open()
    except psycopg.OperationalError:
        ensure = getattr(server, "ensure_postgres_running", None)
        if ensure is None:
            raise
        ensure()
        return _open()


def ensure_database(server) -> bool:
    """Создаёт базу audit, если её нет. Возвращает True, если создана."""
    with connect(server, database="postgres") as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (config.DB_NAME,)
        ).fetchone()
        if exists:
            return False
        conn.execute(f'CREATE DATABASE "{config.DB_NAME}"')
        return True


def _registry_ddl() -> str:
    return """
        CREATE TABLE IF NOT EXISTS public.schema_migrations (
            filename   text PRIMARY KEY,
            checksum   text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
    """


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_checksum(seed_dir: Path | None = None) -> str:
    """SHA-256 набора CSV по тем же правилам, что scripts/generate_data.py.

    В хеш входят имена файлов и их байты в лексикографическом порядке.
    """
    directory = Path(seed_dir or config.SEED_DIR)
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.csv")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _verify_seed_checksum(directory: Path, *, allow_mismatch: bool) -> None:
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SeedChecksumError(
            f"Не удалось прочитать {manifest_path}: {exc}"
        ) from exc

    expected = str(manifest.get("sha256") or "")
    if not expected:
        return
    actual = seed_checksum(directory)
    if actual == expected:
        return
    if allow_mismatch:
        return
    raise SeedChecksumError(
        f"Checksum seed не совпадает с manifest.json: "
        f"ожидалось {expected[:12]}..., получено {actual[:12]}.... "
        f"Перегенерируйте данные: .venv\\Scripts\\python.exe "
        f"scripts\\generate_data.py --deviations. "
        f"Проверку можно пропустить флагом --allow-checksum-mismatch."
    )


def apply_migrations(
    server,
    migrations_dir: Path | None = None,
) -> MigrationResult:
    """Применяет только новые миграции; проверяет checksum уже применённых."""
    directory = Path(migrations_dir or config.MIGRATIONS_DIR)
    files = sorted(directory.glob("*.sql"))
    if not files:
        raise MigrationError(f"В каталоге {directory} нет миграций")

    applied: list[str] = []
    skipped: list[str] = []

    with connect(server, autocommit=False, client_side=True) as conn:
        conn.execute(_registry_ddl())
        conn.commit()

        for path in files:
            checksum = _checksum(path)
            row = conn.execute(
                "SELECT checksum FROM public.schema_migrations WHERE filename = %s",
                (path.name,),
            ).fetchone()

            if row is not None:
                if row[0] != checksum:
                    raise MigrationError(
                        f"Миграция {path.name} изменена после применения: "
                        f"checksum {row[0][:12]} != {checksum[:12]}"
                    )
                skipped.append(path.name)
                continue

            try:
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO public.schema_migrations (filename, checksum) "
                    "VALUES (%s, %s)",
                    (path.name, checksum),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            applied.append(path.name)

    return MigrationResult(applied=applied, skipped=skipped)


def ensure_roles(server) -> None:
    """Создаёт read-only и прикладную роли с минимальными правами."""
    with connect(server) as conn:
        for role in (READ_ONLY_ROLE, APP_ROLE):
            exists = conn.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE ROLE "{role}" LOGIN')

        conn.execute(f'GRANT CONNECT ON DATABASE "{config.DB_NAME}" TO {READ_ONLY_ROLE}, {APP_ROLE}')
        conn.execute(f"GRANT USAGE ON SCHEMA audit TO {READ_ONLY_ROLE}, {APP_ROLE}")
        conn.execute(f"REVOKE CREATE ON SCHEMA audit FROM PUBLIC")

        conn.execute(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA audit "
            f"TO {READ_ONLY_ROLE}, {APP_ROLE}"
        )
        conn.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA audit "
            f"GRANT SELECT ON TABLES TO {READ_ONLY_ROLE}, {APP_ROLE}"
        )
        # audit.as_of_date() вызывается из представлений и QA под обеими ролями.
        conn.execute(
            f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA audit "
            f"TO {READ_ONLY_ROLE}, {APP_ROLE}"
        )
        conn.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA audit "
            f"GRANT EXECUTE ON FUNCTIONS TO {READ_ONLY_ROLE}, {APP_ROLE}"
        )

        conn.execute(
            f"GRANT INSERT, UPDATE, DELETE ON audit.auditor_memory TO {APP_ROLE}"
        )
        chat_tables = conn.execute(
            "SELECT to_regclass('audit.chat_threads')"
        ).fetchone()
        if chat_tables and chat_tables[0]:
            conn.execute(
                f"GRANT INSERT, UPDATE, DELETE ON "
                f"audit.chat_threads, audit.chat_messages TO {APP_ROLE}"
            )
        conn.execute(
            f"REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA audit "
            f"FROM {READ_ONLY_ROLE}"
        )

        conn.execute(
            f"ALTER ROLE {READ_ONLY_ROLE} SET default_transaction_read_only = on"
        )
        conn.execute(
            f"ALTER ROLE {READ_ONLY_ROLE} SET statement_timeout = "
            f"'{config.SQL_TIMEOUT_SEC}s'"
        )
        conn.execute(f"ALTER ROLE {READ_ONLY_ROLE} SET search_path = audit, public")
        conn.execute(
            f"ALTER ROLE {APP_ROLE} SET statement_timeout = "
            f"'{config.SQL_TIMEOUT_SEC}s'"
        )
        conn.execute(f"ALTER ROLE {APP_ROLE} SET search_path = audit, public")


def _copy_csv(conn, table: str, csv_path: Path) -> None:
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        header = fh.readline().strip()
        fh.seek(0)
        sql = (
            f"COPY {table} ({header}) FROM STDIN "
            "WITH (FORMAT csv, HEADER true)"
        )
        with conn.cursor().copy(sql) as copy:
            copy.write(fh.read())


def seed_from_csv(
    server,
    seed_dir: Path | None = None,
    tables: Sequence[str] | None = None,
    *,
    allow_checksum_mismatch: bool = False,
) -> dict[str, int]:
    """Идемпотентно заменяет синтетический набор данных.

    Все таблицы очищаются и загружаются в одной транзакции: повторный запуск
    даёт тот же результат и не создаёт дубликатов. Перед загрузкой CSV
    сверяются с sha256 из manifest.json.
    """
    directory = Path(seed_dir or config.SEED_DIR)
    if not directory.exists():
        raise FileNotFoundError(f"Каталог seed не найден: {directory}")

    _verify_seed_checksum(directory, allow_mismatch=allow_checksum_mismatch)

    selected = tuple(tables or SEED_TABLES)
    available = [
        table for table in selected
        if (directory / f"{table.split('.')[1]}.csv").exists()
    ]
    if not available:
        raise FileNotFoundError(f"В {directory} нет CSV для таблиц {selected}")

    counts: dict[str, int] = {}
    with connect(server, autocommit=False) as conn:
        try:
            conn.execute(
                "TRUNCATE " + ", ".join(available) + " RESTART IDENTITY CASCADE"
            )
            for table in available:
                _copy_csv(conn, table, directory / f"{table.split('.')[1]}.csv")
                counts[table] = conn.execute(
                    f"SELECT count(*) FROM {table}"
                ).fetchone()[0]
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return counts


def upsert_dataset_metadata(server, seed_dir: Path | None = None) -> dict:
    """Загружает manifest набора в audit.dataset_metadata."""
    directory = Path(seed_dir or config.SEED_DIR)
    manifest_path = directory / "manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    as_of = manifest.get("as_of_date") or config.DEFAULT_AS_OF_DATE.isoformat()
    seed = int(manifest.get("seed", 42))
    checksum = str(manifest.get("sha256", ""))

    with connect(server) as conn:
        conn.execute(
            """
            INSERT INTO audit.dataset_metadata (metadata_id, as_of_date, seed, checksum)
            VALUES (1, %s, %s, %s)
            ON CONFLICT (metadata_id) DO UPDATE
            SET as_of_date = EXCLUDED.as_of_date,
                seed = EXCLUDED.seed,
                checksum = EXCLUDED.checksum
            """,
            (as_of, seed, checksum),
        )
    return {"as_of_date": as_of, "seed": seed, "checksum": checksum}


def reset_data_dir(pgdata: Path | str | None = None) -> None:
    """Удаляет каталог данных PostgreSQL. Требует явного согласия вызывающего."""
    path = Path(pgdata or config.PGDATA_DIR)
    if path.exists():
        shutil.rmtree(path)


def migration_files(migrations_dir: Path | None = None) -> Iterable[Path]:
    return sorted(Path(migrations_dir or config.MIGRATIONS_DIR).glob("*.sql"))
