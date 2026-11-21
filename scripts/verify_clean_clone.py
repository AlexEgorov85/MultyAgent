"""Автоматическая проверка чистого клона.

Запуск из корня проекта:
    python scripts/verify_clean_clone.py
    python scripts/verify_clean_clone.py --ref main --no-env
    python scripts/verify_clean_clone.py --repo . --ref main --keep
    python scripts/verify_clean_clone.py --repo https://github.com/user/repo.git --ref v1.0.0
    python scripts/verify_clean_clone.py --ref 1a2b3c4d --no-env
    python scripts/verify_clean_clone.py --with-ui
    python scripts/verify_clean_clone.py --with-live --index openai

Флаги:
    --repo PATH_OR_URL  откуда клонировать: URL, локальный путь или имя remote
                        (по умолчанию origin);
    --ref NAME          ветка, тег или SHA (по умолчанию main). Для SHA клон
                        создаётся без --branch, а checkout делается внутри клона;
    --no-env            не создавать .env в клоне: проверка, что офлайн-этапы
                        не требуют секретов;
    --keep              не удалять клон после проверки (путь печатается);
    --workdir PATH      каталог клона;
    --index MODE        hash | openai | skip;
    --with-ui           собрать Next.js UI;
    --with-live         выполнить живой LLM-запрос.

Скрипт:
1. клонирует указанную ревизию в отдельный каталог;
2. создаёт venv на Python 3.12 через uv;
3. ставит requirements.txt;
4. генерирует данные, поднимает БД, применяет миграции, грузит seed;
5. проверяет идемпотентность повторной загрузки;
6. строит RAG-индекс;
7. запускает QA и pytest;
8. проверяет read-only SQL;
9. поднимает LangGraph API и проверяет /ok и /assistants/search;
10. опционально собирает UI и запускает живой Analytics-запрос;
11. проверяет, что в git нет секретов и тяжёлых артефактов: .env и его
    локальные варианты, data/pg/, data/seed/, node_modules/, .next/, *.pdf,
    видео и архивы, а также файлы больше 5 МБ. Содержимое .env не печатается.

В конце выводится машинно-проверяемая строка `RESULT: OK` или
`RESULT: FAIL <причина>`; код возврата 0 или 1 соответственно.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"

DEFAULT_REPO = "origin"
DEFAULT_REF = "main"
# Файлы больше этого размера в git считаются тяжёлыми артефактами.
MAX_TRACKED_FILE_BYTES = 5 * 1024 * 1024

# Каталоги (на любом уровне вложенности), которые не должны попадать в git.
FORBIDDEN_DIRS = (
    "data/pg",
    "data/seed",
    "node_modules",
    ".next",
    ".venv",
)
FORBIDDEN_EXTENSIONS = (
    ".pdf",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".iso",
)

_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


class CheckError(RuntimeError):
    pass


def run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 1800,
    env: dict[str, str] | None = None,
) -> None:
    printable = " ".join(command)
    print(f"\n$ {printable}")
    result = subprocess.run(
        command,
        cwd=str(cwd),
        timeout=timeout,
        env={**os.environ, **(env or {})},
    )
    if result.returncode != 0:
        raise CheckError(f"Команда завершилась с кодом {result.returncode}: {printable}")


def capture(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def venv_python(clone: Path) -> Path:
    return clone / (".venv/Scripts/python.exe" if IS_WINDOWS else ".venv/bin/python")


def venv_tool(clone: Path, name: str) -> Path:
    folder = ".venv/Scripts" if IS_WINDOWS else ".venv/bin"
    suffix = ".exe" if IS_WINDOWS else ""
    return clone / folder / f"{name}{suffix}"


def remove_tree(path: Path) -> None:
    """Удаляет каталог, снимая read-only с файлов git на Windows."""
    import stat

    def onexc(func, target, exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except Exception:
            pass

    shutil.rmtree(path, onexc=onexc)


def make_workdir(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
    else:
        base = Path(r"C:\Temp") if IS_WINDOWS else Path(tempfile.gettempdir())
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = base / f"audit-clean-{stamp}"
    if path.exists():
        if "audit-clean" not in path.name:
            raise CheckError(
                f"Отказываюсь удалять {path}: имя не содержит 'audit-clean'"
            )
        remove_tree(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def is_sha_like(ref: str) -> bool:
    """Похожа ли ревизия на SHA коммита (7-40 hex-символов)."""
    return bool(_SHA_RE.fullmatch(ref.strip()))


def resolve_repo(repo: str) -> str:
    """Превращает аргумент --repo в то, что понимает git clone.

    Локальный путь становится абсолютным, имя remote (например, origin)
    заменяется на его URL, остальное (URL, ssh-адрес) передаётся как есть.
    """
    value = (repo or "").strip()
    if not value:
        raise CheckError("--repo не может быть пустым")

    if "://" in value or value.startswith("git@"):
        return value

    candidate = Path(value).expanduser()
    if candidate.exists():
        return str(candidate.resolve())

    try:
        remotes = capture(["git", "remote"], cwd=ROOT).splitlines()
    except (OSError, subprocess.CalledProcessError):
        remotes = []

    if value in remotes:
        try:
            return capture(["git", "remote", "get-url", value], cwd=ROOT)
        except subprocess.CalledProcessError as exc:
            raise CheckError(f"Не удалось получить URL remote {value}") from exc

    if value == DEFAULT_REPO:
        raise CheckError(
            "Не удалось определить origin: это не remote и не существующий путь; "
            "укажите --repo"
        )
    return value


def verify_checkout(clone: Path, ref: str) -> str:
    """Проверяет, что клон действительно находится на запрошенной ревизии."""
    head = capture(["git", "rev-parse", "HEAD"], cwd=clone)
    branch = capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=clone)

    if is_sha_like(ref):
        if not head.lower().startswith(ref.lower()):
            raise CheckError(
                f"HEAD {head[:12]} не совпадает с запрошенным SHA {ref}"
            )
    elif branch == ref:
        pass
    else:
        try:
            tag_commit = capture(
                ["git", "rev-parse", "--verify", f"refs/tags/{ref}^{{commit}}"],
                cwd=clone,
            )
        except subprocess.CalledProcessError as exc:
            raise CheckError(
                f"Клон не находится на ветке или теге {ref} (HEAD: {branch})"
            ) from exc
        if tag_commit != head:
            raise CheckError(
                f"HEAD {head[:12]} не совпадает с тегом {ref} ({tag_commit[:12]})"
            )

    print(f"[git] HEAD: {head[:12]} ({branch})")
    return head


def clone_repo(repo: str, workdir: Path, ref: str = DEFAULT_REF) -> Path:
    print(f"\n=== 1. Клон {repo} ({ref}) -> {workdir} ===")
    if is_sha_like(ref):
        print("[git] ревизия похожа на SHA: клонирую и переключаюсь внутри клона")
        run(["git", "clone", repo, str(workdir)], cwd=ROOT)
        run(["git", "checkout", ref], cwd=workdir)
    else:
        run(["git", "clone", "--branch", ref, repo, str(workdir)], cwd=ROOT)

    verify_checkout(workdir, ref)
    if capture(["git", "status", "--porcelain"], cwd=workdir):
        raise CheckError("Рабочее дерево чистого клона не пустое")
    return workdir


def find_uv() -> list[str]:
    candidates: list[list[str]] = [[sys.executable, "-m", "uv"]]
    system_python = shutil.which("python")
    if system_python:
        candidates.append([system_python, "-m", "uv"])
    candidates.extend(
        [
            ["uv"],
            ["py", "-3.14", "-m", "uv"],
            ["py", "-3.12", "-m", "uv"],
        ]
    )
    for candidate in candidates:
        try:
            subprocess.run(
                [*candidate, "--version"],
                check=True,
                capture_output=True,
            )
            return candidate
        except (OSError, subprocess.CalledProcessError):
            continue
    raise CheckError(
        "uv не найден. Установите: python -m pip install --user uv"
    )


def prepare_python(clone: Path) -> Path:
    print("\n=== 2. Python 3.12, venv и зависимости ===")
    uv = find_uv()
    run([*uv, "python", "install", "3.12"], cwd=clone, timeout=600)
    run(
        [*uv, "venv", "--python", "3.12", ".venv"],
        cwd=clone,
        timeout=600,
    )
    python = venv_python(clone)
    run(
        [
            *uv,
            "pip",
            "install",
            "--python",
            str(python),
            "-r",
            "requirements.txt",
        ],
        cwd=clone,
        timeout=1800,
    )
    return python


def prepare_env(clone: Path, no_env: bool = False) -> None:
    target = clone / ".env"
    if no_env:
        target.unlink(missing_ok=True)
        print(
            "[env] --no-env: .env не создаётся, "
            "офлайн-этапы должны работать без секретов"
        )
        return

    source = ROOT / ".env"
    if source.exists():
        shutil.copyfile(source, target)
        print("[env] .env скопирован из рабочей копии (секрет не печатается)")
    elif (clone / ".env.example").exists():
        shutil.copyfile(clone / ".env.example", target)
        print("[env] создан .env из .env.example")
    else:
        raise CheckError("Нет .env.example")


def prepare_data(python: Path, clone: Path, index_mode: str) -> None:
    print("\n=== 3. Данные и БД ===")
    run([str(python), "scripts/generate_data.py", "--deviations"], cwd=clone)
    run(
        [str(python), "scripts/init_db.py", "--reset-db", "--yes", "--seed"],
        cwd=clone,
    )

    print("\n=== 4. Идемпотентность seed ===")
    run([str(python), "scripts/init_db.py", "--seed"], cwd=clone)

    if index_mode == "skip":
        print("[rag] индекс пропущен по флагу --index skip")
        return

    print("\n=== 5. RAG-индекс ===")
    args = [str(python), "scripts/build_index.py"]
    if index_mode == "hash":
        args.append("--hash")
    run(args, cwd=clone, timeout=1200)


def run_checks(python: Path, clone: Path) -> None:
    print("\n=== 6. QA и тесты ===")
    run([str(python), "scripts/qa_checks.py"], cwd=clone)
    run([str(python), "-m", "pytest", "-q"], cwd=clone, timeout=1200)

    print("\n=== 7. Read-only SQL ===")
    run([str(python), "scripts/demo_queries.py"], cwd=clone)


def wait_for_api(url: str, timeout: int = 240) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/ok", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise CheckError(f"LangGraph API не поднялся за {timeout} секунд")


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()


def check_api(clone: Path) -> None:
    print("\n=== 8. LangGraph API ===")
    url = "http://127.0.0.1:2024"
    executable = venv_tool(clone, "langgraph")
    log_path = clone / "data" / "pg" / "langgraph-dev.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(executable), "dev", "--port", "2024", "--no-browser"],
        cwd=str(clone),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    try:
        try:
            wait_for_api(url)
        except CheckError:
            log_file.flush()
            tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
            raise CheckError(
                "LangGraph API не поднялся. Последние строки лога:\n"
                + "\n".join(tail)
            )
        print("[api] /ok: 200")
        request = urllib.request.Request(
            f"{url}/assistants/search",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, list) or not body:
            raise CheckError("API не вернул ни одного ассистента")
        graph_id = body[0].get("graph_id")
        if graph_id != "audit_assistant":
            raise CheckError(f"Неожиданный graph_id: {graph_id}")
        print(f"[api] assistant: {graph_id}")
    finally:
        stop_process(process)
        log_file.close()
        log_path.unlink(missing_ok=True)


def check_ui(clone: Path) -> None:
    print("\n=== 9. UI build ===")
    npm = shutil.which("npm")
    if not npm:
        raise CheckError("npm не найден в PATH")
    run([npm, "ci", "--no-audit", "--no-fund"], cwd=clone / "ui", timeout=1800)
    run([npm, "run", "build"], cwd=clone / "ui", timeout=1800)


def check_live(python: Path, clone: Path) -> None:
    print("\n=== 10. Живой Analytics-запрос ===")
    run(
        [
            str(python),
            "scripts/run_analytics.py",
            "--question",
            "Сколько завершённых проверок по ипотеке в 2026 году?",
        ],
        cwd=clone,
        timeout=600,
    )


def normalize_git_path(path: str) -> str:
    """Приводит путь из git к виду с прямыми слэшами без префикса ./."""
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_forbidden_tracked_path(path: str) -> bool:
    """Запрещён ли путь в git: секреты, данные БД, сборки, PDF, видео, архивы."""
    normalized = normalize_git_path(path)
    lower = normalized.lower()
    name = lower.rsplit("/", 1)[-1]

    # .env и его локальные варианты; шаблоны *.example безопасны.
    if name.startswith(".env") and not name.endswith(".example"):
        return True

    for folder in FORBIDDEN_DIRS:
        if (
            lower == folder
            or lower.startswith(f"{folder}/")
            or f"/{folder}/" in lower
        ):
            return True

    return lower.endswith(FORBIDDEN_EXTENSIONS)


def format_size(size: int) -> str:
    if size >= 1024**3:
        return f"{size / 1024**3:.1f} ГБ"
    if size >= 1024**2:
        return f"{size / 1024**2:.1f} МБ"
    if size >= 1024:
        return f"{size / 1024:.1f} КБ"
    return f"{size} Б"


def scan_large_files(
    clone: Path,
    tracked: list[str],
    max_bytes: int = MAX_TRACKED_FILE_BYTES,
) -> list[str]:
    """Возвращает описания файлов из git, превышающих лимит размера."""
    offenders: list[str] = []
    for path in tracked:
        normalized = normalize_git_path(path)
        if not normalized:
            continue
        try:
            size = (clone / normalized).stat().st_size
        except OSError:
            continue
        if size > max_bytes:
            offenders.append(
                f"{normalized} ({format_size(size)} > {format_size(max_bytes)})"
            )
    return offenders


def check_repo_clean(clone: Path) -> None:
    print("\n=== 11. Чистота репозитория ===")
    status = capture(["git", "status", "--porcelain"], cwd=clone)
    if status:
        raise CheckError(f"В клоне появились незакоммиченные файлы:\n{status}")

    tracked = [
        line
        for line in capture(["git", "ls-files"], cwd=clone).splitlines()
        if line.strip()
    ]

    forbidden = [
        normalize_git_path(path)
        for path in tracked
        if is_forbidden_tracked_path(path)
    ]
    large = scan_large_files(clone, tracked)

    problems: list[str] = []
    for item in [*forbidden, *large]:
        if item not in problems:
            problems.append(item)

    if problems:
        raise CheckError(
            "В git попали секреты или тяжёлые артефакты "
            f"({len(problems)}):\n" + "\n".join(f" - {item}" for item in problems)
        )

    print(
        f"[git] рабочее дерево чистое; файлов в git: {len(tracked)}; "
        "секретов и тяжёлых артефактов нет"
    )


def format_result(ok: bool, reason: str = "") -> str:
    """Единая машинно-проверяемая итоговая строка (всегда в одну строку)."""
    if ok:
        return "RESULT: OK"
    detail = " ".join(str(reason).split())
    return f"RESULT: FAIL {detail}" if detail else "RESULT: FAIL"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Проверка чистого клона",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  python scripts/verify_clean_clone.py\n"
            "  python scripts/verify_clean_clone.py --ref main --no-env\n"
            "  python scripts/verify_clean_clone.py --repo . --ref main --keep\n"
            "  python scripts/verify_clean_clone.py --repo https://github.com/user/repo.git --ref v1.0.0\n"
            "  python scripts/verify_clean_clone.py --ref 1a2b3c4d --no-env\n"
        ),
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        metavar="PATH_OR_URL",
        help=(
            "откуда клонировать: URL, локальный путь или имя remote "
            f"(по умолчанию {DEFAULT_REPO})"
        ),
    )
    parser.add_argument(
        "--ref",
        default=DEFAULT_REF,
        metavar="NAME",
        help=(
            "ветка, тег или SHA для проверки "
            f"(по умолчанию {DEFAULT_REF})"
        ),
    )
    parser.add_argument("--workdir", help="каталог клона")
    parser.add_argument(
        "--index",
        choices=("hash", "openai", "skip"),
        default="hash",
        help="режим индекса: офлайн hash, реальные эмбеддинги openai или пропуск",
    )
    parser.add_argument(
        "--no-env",
        action="store_true",
        help="не создавать .env в клоне (проверка работы без секретов)",
    )
    parser.add_argument("--with-ui", action="store_true", help="собрать Next.js UI")
    parser.add_argument("--with-live", action="store_true", help="живой LLM-запрос")
    parser.add_argument("--keep", action="store_true", help="не удалять клон")
    return parser


def run_verification(args: argparse.Namespace) -> None:
    repo = resolve_repo(args.repo)
    workdir = make_workdir(args.workdir)
    started = time.time()
    print(f"Репозиторий: {repo}")
    print(f"Ревизия:    {args.ref}")
    print(f"Каталог:    {workdir}")

    try:
        clone = clone_repo(repo, workdir, args.ref)
        python = prepare_python(clone)
        prepare_env(clone, no_env=args.no_env)
        prepare_data(python, clone, args.index)
        run_checks(python, clone)
        check_api(clone)
        if args.with_ui:
            check_ui(clone)
        if args.with_live:
            check_live(python, clone)
        check_repo_clean(clone)
    except CheckError:
        if args.keep and workdir.exists():
            print(f"Клон оставлен для разбора: {workdir}", file=sys.stderr)
        raise
    finally:
        if not args.keep and workdir.exists():
            remove_tree(workdir)

    elapsed = time.time() - started
    print(f"\n[OK] Чистый клон прошёл все проверки за {elapsed:.1f} секунд")
    print("Проверено: клон, зависимости, БД, seed, индекс, QA, тесты, API.")
    if args.no_env:
        print("Env: .env не создавался, офлайн-этапы прошли без секретов.")
    if args.with_ui:
        print("UI: production build пройден.")
    if args.with_live:
        print("Live: Analytics-запрос выполнен.")
    if args.keep:
        print(f"Клон оставлен: {workdir}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run_verification(args)
    except CheckError as exc:
        print(f"\n[FAIL] {exc}", file=sys.stderr)
        print(format_result(False, str(exc)))
        return 1
    except KeyboardInterrupt:
        print("\n[FAIL] Прервано пользователем", file=sys.stderr)
        print(format_result(False, "прервано пользователем"))
        return 1
    except Exception as exc:  # непредвиденная ошибка — всё равно даём RESULT
        traceback.print_exc()
        print(format_result(False, f"неожиданная ошибка: {type(exc).__name__}: {exc}"))
        return 1

    print(format_result(True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
