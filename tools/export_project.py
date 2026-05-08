#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_MAX_ARCHIVE_BYTES = 25 * 1024 * 1024

DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git/**",
    ".secrets.baseline",
    ".venv/**",
    "venv/**",
    "env/**",
    "__pycache__/**",
    ".pytest_cache/**",
    ".mypy_cache/**",
    ".ruff_cache/**",
    "node_modules/**",
    "playwright-report/**",
    "test-results/**",
    "htmlcov/**",
    ".coverage",
    "coverage.xml",
    "*.pyc",
    "*.pyo",
    ".env",
    ".env.*",
    "*.env",
    ".en",
    "*.key",
    "*.pem",
    "secrets.*",
    "*.secret",
    "*.zip",
    "*.tar",
    "*.tgz",
    "*.tar.gz",
    "*.7z",
    "*.rar",
    "data/audit/**",
    "data/backtests/**",
    "data/cache/**",
    "data/cloud/**",
    "data/health/**",
    "data/ml/**",
    "data/odds/**",
    "data/playerboard/**",
    "data/predictions/**",
    "data/training/**",
    "data/user/**",
    "data/warehouse/**",
    "data/models/**",
    "logs/**",
    "*.log",
    "*.err.log",
    "screenshots/**",
    "tmp/**",
    "tmp*/**",
    "tmpl*/**",
    "dist/**",
)

DATA_EXCLUDES: tuple[str, ...] = (
    "data/audit/**",
    "data/backtests/**",
    "data/cache/**",
    "data/cloud/**",
    "data/health/**",
    "data/ml/**",
    "data/odds/**",
    "data/playerboard/**",
    "data/predictions/**",
    "data/training/**",
    "data/user/**",
    "data/warehouse/**",
)

MODEL_ARTIFACT_EXCLUDES: tuple[str, ...] = ("data/models/**",)

SECRET_FILENAME_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.env",
    ".en",
    "*.key",
    "*.pem",
    "secrets.*",
    "*.secret",
)

ARCHIVE_FILENAME_PATTERNS: tuple[str, ...] = (
    "*.zip",
    "*.tar",
    "*.tgz",
    "*.tar.gz",
    "*.7z",
    "*.rar",
)

SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*=\s*['\"]?([A-Za-z0-9_\-]{16,})"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}"),
)


@dataclass(frozen=True)
class ExportItem:
    path: Path
    arcname: str


def norm(path: str | Path) -> str:
    return str(path).replace(os.sep, "/")


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def should_exclude(path: str, excludes: tuple[str, ...]) -> bool:
    path = path.strip("/")
    if path == ".env.example":
        return False
    return matches_any(path, excludes) or any(path.startswith(pattern.removesuffix("/**") + "/") for pattern in excludes if pattern.endswith("/**"))


def iter_export_items(root: Path, excludes: tuple[str, ...], *, output: Path | None = None) -> list[ExportItem]:
    items: list[ExportItem] = []
    resolved_output = output.resolve() if output is not None else None
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if resolved_output is not None and path.resolve() == resolved_output:
            continue
        rel = norm(path.relative_to(root))
        if should_exclude(rel, excludes):
            continue
        items.append(ExportItem(path=path, arcname=rel))
    return items


def assert_safe_filename(arcname: str) -> None:
    if arcname == ".env.example":
        return
    basename = Path(arcname).name
    if matches_any(basename, SECRET_FILENAME_PATTERNS) or matches_any(arcname, SECRET_FILENAME_PATTERNS):
        raise ValueError(f"Refusing to export secret-bearing filename: {arcname}")
    if matches_any(basename, ARCHIVE_FILENAME_PATTERNS) or matches_any(arcname, ARCHIVE_FILENAME_PATTERNS):
        raise ValueError(f"Refusing to export nested generated archive: {arcname}")


def assert_safe_content(path: Path, arcname: str) -> None:
    if path.stat().st_size > 2_000_000:
        return
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for pattern in SECRET_VALUE_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"Refusing to export file with secret-like content: {arcname}")


def build_excludes(include_data: bool, include_model_artifacts: bool) -> tuple[str, ...]:
    excludes = list(DEFAULT_EXCLUDES)
    if include_data:
        excludes = [pattern for pattern in excludes if pattern not in DATA_EXCLUDES]
    if include_model_artifacts:
        excludes = [pattern for pattern in excludes if pattern not in MODEL_ARTIFACT_EXCLUDES]
    return tuple(excludes)


def export_project(
    root: Path,
    output: Path,
    *,
    include_data: bool = False,
    include_model_artifacts: bool = False,
    dry_run: bool = False,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
) -> list[ExportItem]:
    root = root.resolve()
    output = output.resolve()
    excludes = build_excludes(include_data=include_data, include_model_artifacts=include_model_artifacts)
    items = iter_export_items(root, excludes, output=output)
    for item in items:
        assert_safe_filename(item.arcname)
        assert_safe_content(item.path, item.arcname)
    if dry_run:
        return items
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item in items:
            archive.write(item.path, item.arcname)
    size = output.stat().st_size
    if size > max_archive_bytes:
        output.unlink(missing_ok=True)
        raise ValueError(
            f"Refusing oversized export: {size} bytes exceeds threshold {max_archive_bytes} bytes"
        )
    return items


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a safe, source-only MLB app export")
    parser.add_argument("--root", default=".", help="Project root directory")
    parser.add_argument("--output", required=True, help="Output zip path, e.g. dist/mlb-app-source.zip")
    parser.add_argument("--include-data", action="store_true", help="Include generated data folders. Off by default.")
    parser.add_argument("--include-model-artifacts", action="store_true", help="Include data/models artifacts. Off by default.")
    parser.add_argument("--dry-run", action="store_true", help="List files that would be exported without writing zip")
    parser.add_argument("--max-size-mb", type=float, default=25.0, help="Fail if the produced archive exceeds this size")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        items = export_project(
            Path(args.root),
            Path(args.output),
            include_data=args.include_data,
            include_model_artifacts=args.include_model_artifacts,
            dry_run=args.dry_run,
            max_archive_bytes=int(args.max_size_mb * 1024 * 1024),
        )
    except ValueError as error:
        print(f"safe export failed: {error}", file=sys.stderr)
        return 2
    if args.dry_run:
        for item in items:
            print(item.arcname)
    else:
        print(f"exported {len(items)} files to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
