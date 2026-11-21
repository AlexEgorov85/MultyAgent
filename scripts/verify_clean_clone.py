"""Автоматическая проверка чистого клона.

Запуск из корня проекта:
    python scripts/verify_clean_clone.py
    python scripts/verify_clean_clone.py --with-ui
    python scripts/verify_clean_clone.py --with-live --index openai

Скрипт:
1. клонирует origin/main в отдельный каталог;
2. создаёт venv на Python 3.12 через uv;
3. ставит requirements.txt;
4. генерирует данные, поднимает БД, применяет миграции, грузит seed;
5. проверяет идемпотентность повторной загрузки;
6. строит RAG-индекс;
7. запускает QA и pytest;
8. проверяет read-only SQL;
9. поднимает LangGraph API и проверяет /ok и /assistants/search;
10. опционально собирает UI и запускает живой Analytics-запрос;
11. проверяет, что в git нет секретов и тяжёлых артефактов.

Секреты не печатаются. Для offline-проверки ключ не нужен.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"


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


def clone_repo(repo: str, workdir: Path) -> Path:
    print(f"\n=== 1. Клон {repo} -> {workdir} ===")
    run(["git", "clone", "--branch", "main", repo, str(workdir)], cwd=ROOT)
    branch = capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=workdir)
    if branch != "main":
        raise CheckError(f"Ожидалась ветка main, получена {branch}")
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


def prepare_env(clone: Path) -> None:
    target = clone / ".env"
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


def check_repo_clean(clone: Path) -> None:
    print("\n=== 11. Чистота репозитория ===")
    status = capture(["git", "status", "--porcelain"], cwd=clone)
    if status:
        raise CheckError(f"В клоне появились незакоммиченные файлы:\n{status}")

    tracked = capture(["git", "ls-files"], cwd=clone).splitlines()
    forbidden = []
    for path in tracked:
        normalized = path.replace("\\", "/")
        if (
            normalized == ".env"
            or normalized.startswith("data/pg/")
            or normalized.startswith("data/seed/")
            or "/node_modules/" in normalized
            or normalized.startswith("node_modules/")
            or "/.next/" in normalized
            or normalized.startswith(".next/")
            or normalized.lower().endswith(".pdf")
        ):
            forbidden.append(normalized)
    if forbidden:
        raise CheckError("В git попали запрещённые файлы:\n" + "\n".join(forbidden))
    print("[git] рабочее дерево чистое, секретов и тяжёлых артефактов нет")


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка чистого клона")
    parser.add_argument("--repo", help="URL репозитория (по умолчанию origin)")
    parser.add_argument("--workdir", help="каталог клона")
    parser.add_argument(
        "--index",
        choices=("hash", "openai", "skip"),
        default="hash",
        help="режим индекса: офлайн hash, реальные эмбеддинги openai или пропуск",
    )
    parser.add_argument("--with-ui", action="store_true", help="собрать Next.js UI")
    parser.add_argument("--with-live", action="store_true", help="живой LLM-запрос")
    parser.add_argument("--keep", action="store_true", help="не удалять клон")
    args = parser.parse_args()

    repo = args.repo
    if not repo:
        try:
            repo = capture(["git", "remote", "get-url", "origin"], cwd=ROOT)
        except subprocess.CalledProcessError as exc:
            raise CheckError("Не удалось определить origin; укажите --repo") from exc

    workdir = make_workdir(args.workdir)
    started = time.time()
    print(f"Репозиторий: {repo}")
    print(f"Каталог:    {workdir}")

    try:
        clone = clone_repo(repo, workdir)
        python = prepare_python(clone)
        prepare_env(clone)
        prepare_data(python, clone, args.index)
        run_checks(python, clone)
        check_api(clone)
        if args.with_ui:
            check_ui(clone)
        if args.with_live:
            check_live(python, clone)
        check_repo_clean(clone)
    except CheckError as exc:
        print(f"\n[FAIL] {exc}", file=sys.stderr)
        if args.keep:
            print(f"Клон оставлен для разбора: {workdir}", file=sys.stderr)
        return 1
    finally:
        if not args.keep and workdir.exists():
            remove_tree(workdir)

    elapsed = time.time() - started
    print(f"\n[OK] Чистый клон прошёл все проверки за {elapsed:.1f} секунд")
    print("Проверено: клон, зависимости, БД, seed, индекс, QA, тесты, API.")
    if args.with_ui:
        print("UI: production build пройден.")
    if args.with_live:
        print("Live: Analytics-запрос выполнен.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
