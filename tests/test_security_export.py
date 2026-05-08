from __future__ import annotations

import zipfile
from pathlib import Path

from tools.export_project import export_project


def test_safe_export_excludes_secret_and_generated_data(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (root / ".env").write_text("ODDS_" + "API_" + "KEY=should-not-export\n", encoding="utf-8")
    (root / ".env.example").write_text("ODDS_API_KEY=\n", encoding="utf-8")
    (root / ".en").write_text("SEC" + "RET=should-not-export\n", encoding="utf-8")
    (root / "data" / "cache").mkdir(parents=True)
    (root / "data" / "cache" / "odds.csv").write_text("x\n", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"cache")
    (root / ".pytest_cache").mkdir()
    (root / ".pytest_cache" / "README.md").write_text("cache\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "package.txt").write_text("cache\n", encoding="utf-8")
    output = tmp_path / "source.zip"

    export_project(root, output)

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert "app.py" in names
    assert ".env" not in names
    assert ".env.example" in names
    assert ".en" not in names
    assert "data/cache/odds.csv" not in names
    assert "__pycache__/app.cpython-312.pyc" not in names
    assert ".pytest_cache/README.md" not in names
    assert "node_modules/package.txt" not in names


def test_safe_export_blocks_secret_like_content(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "config.py").write_text("API" + "_" + "KEY='abcdefghijklmnopqrstuvwxyz'\n", encoding="utf-8")

    try:
        export_project(root, tmp_path / "source.zip")
    except ValueError as error:
        assert "secret-like content" in str(error)
    else:
        raise AssertionError("export_project should reject secret-like content")


def test_safe_export_excludes_nested_archives(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "old-export.zip").write_bytes(b"zip data")
    output = tmp_path / "source.zip"

    export_project(root, output)

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert "app.py" in names
    assert "old-export.zip" not in names


def test_safe_export_fails_when_archive_is_too_large(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "big.txt").write_text("x" * 1000, encoding="utf-8")
    output = tmp_path / "source.zip"

    try:
        export_project(root, output, max_archive_bytes=10)
    except ValueError as error:
        assert "oversized export" in str(error)
        assert not output.exists()
    else:
        raise AssertionError("export_project should reject oversized artifacts")
