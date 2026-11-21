"""Unit-тесты чистых функций scripts/verify_clean_clone.py.

Не клонируют репозиторий, не ставят зависимости и не поднимают PostgreSQL.
"""

from __future__ import annotations

import pytest

from scripts.verify_clean_clone import (
    CheckError,
    assistant_graph_ids,
    build_parser,
    format_result,
    is_forbidden_tracked_path,
    is_sha_like,
    main,
    normalize_git_path,
    resolve_repo,
    scan_large_files,
)


def test_parser_defaults():
    args = build_parser().parse_args([])
    assert args.repo == "origin"
    assert args.ref == "main"
    assert args.no_env is False
    assert args.keep is False
    assert args.workdir is None
    assert args.index == "hash"
    assert args.api_port == 2024


def test_parser_accepts_new_flags():
    args = build_parser().parse_args(
        [
            "--repo",
            "../other-repo",
            "--ref",
            "v1.2.3",
            "--no-env",
            "--keep",
        ]
    )
    assert args.repo == "../other-repo"
    assert args.ref == "v1.2.3"
    assert args.no_env is True
    assert args.keep is True


def test_help_lists_new_flags(capsys):
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--help"])
    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    for flag in ("--repo", "--ref", "--no-env", "--keep", "--workdir", "--api-port"):
        assert flag in output


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("./a/b.txt", "a/b.txt"),
        (".\\a\\b.txt", "a/b.txt"),
        (".env", ".env"),
        ("data/pg/base", "data/pg/base"),
        ("src/main.py", "src/main.py"),
    ],
)
def test_normalize_git_path(raw, expected):
    assert normalize_git_path(raw) == expected


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "ui/.env.local",
        ".env.production",
        "data/pg/base",
        "data/seed/audits.csv",
        "node_modules/pkg/index.js",
        "ui/node_modules/pkg/index.js",
        ".next/server/page.js",
        "ui/.next/server/page.js",
        ".venv/Scripts/python.exe",
        "docs/report.pdf",
        "docs/report.PDF",
        "media/demo.mp4",
        "dist/archive.zip",
        "backup/dump.tar.gz",
    ],
)
def test_forbidden_tracked_paths(path):
    assert is_forbidden_tracked_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        ".env.example",
        ".env.local.example",
        "ui/.env.local.example",
        "src/main.py",
        "data/seed.py",
        "docs/readme.md",
        "scripts/archive_tool.py",
        "ui/app/page.tsx",
        "reports/example.csv",
    ],
)
def test_allowed_tracked_paths(path):
    assert is_forbidden_tracked_path(path) is False


def test_resolve_repo_local_path(tmp_path):
    target = tmp_path / "local-repo"
    target.mkdir()
    assert resolve_repo(str(target)) == str(target.resolve())


def test_resolve_repo_url_does_not_call_git(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("git не должен вызываться для URL")

    monkeypatch.setattr("scripts.verify_clean_clone.capture", boom)
    url = "https://example.invalid/repo.git"
    assert resolve_repo(url) == url


def test_resolve_repo_rejects_empty():
    with pytest.raises(CheckError):
        resolve_repo("   ")


def test_scan_large_files(tmp_path):
    (tmp_path / "small.txt").write_bytes(b"x" * 10)
    big = tmp_path / "data" / "big.csv"
    big.parent.mkdir()
    big.write_bytes(b"x" * 2048)

    offenders = scan_large_files(
        tmp_path,
        ["small.txt", "data/big.csv"],
        max_bytes=1024,
    )

    assert len(offenders) == 1
    assert "data/big.csv" in offenders[0]
    assert "small.txt" not in offenders[0]


def test_format_result_ok():
    assert format_result(True) == "RESULT: OK"


def test_format_result_fail_is_single_line():
    line = format_result(False, "клон упал\nвторая строка\tи третья")
    assert line == "RESULT: FAIL клон упал вторая строка и третья"
    assert "\n" not in line


def test_format_result_fail_without_reason():
    assert format_result(False) == "RESULT: FAIL"


@pytest.mark.parametrize(
    "ref",
    ["a1b2c3d", "A1B2C3D4E5F6", "0" * 40, "deadbeef"],
)
def test_is_sha_like_true(ref):
    assert is_sha_like(ref) is True


@pytest.mark.parametrize(
    "ref",
    ["main", "v1.2.3", "release/2026", "HEAD", "a1b2c3", "xyz1234"],
)
def test_is_sha_like_false(ref):
    assert is_sha_like(ref) is False


def test_assistant_graph_ids_ignores_order():
    body = [
        {"graph_id": "dialogue_admin"},
        {"graph_id": "audit_assistant"},
    ]
    assert assistant_graph_ids(body) == {"audit_assistant", "dialogue_admin"}


def test_assistant_graph_ids_requires_both_graphs():
    with pytest.raises(CheckError, match="dialogue_admin"):
        assistant_graph_ids([{"graph_id": "audit_assistant"}])


def test_assistant_graph_ids_rejects_empty_body():
    with pytest.raises(CheckError, match="ни одного ассистента"):
        assistant_graph_ids([])


def test_main_failure_returns_1_and_prints_result(monkeypatch, capsys):
    monkeypatch.setattr(
        "scripts.verify_clean_clone.resolve_repo",
        lambda repo: "https://example.invalid/repo.git",
    )

    def fail(*args, **kwargs):
        raise CheckError("нет сети")

    monkeypatch.setattr("scripts.verify_clean_clone.clone_repo", fail)

    code = main(["--repo", "https://example.invalid/repo.git"])

    assert code == 1
    captured = capsys.readouterr()
    assert "RESULT: FAIL нет сети" in captured.out
    assert "RESULT: OK" not in captured.out
