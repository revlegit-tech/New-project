#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PRODUCTION_FILES = (
    "Makefile",
    "Dockerfile",
    ".devcontainer/Dockerfile",
    ".github/workflows",
    "public",
    "mlb_app",
    "tools",
    "README.md",
    "docs/DEVELOPER_GUIDE.md",
)

BLOCKED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bpython\s+app\.py\b"),
    re.compile(r"\bpython3\s+app\.py\b"),
    re.compile(r"\bpy_compile\s+app\.py\b"),
    re.compile(r"\brun-legacy\b"),
    re.compile(r"\bapp\.py\b.*\bcompatibility bootstrap\b", re.IGNORECASE),
    re.compile(r"\bExisting app\.py server\b", re.IGNORECASE),
)

ALLOWED_FILES = {
    "docs/runtime/APP_PY_RETIREMENT.md",
    "PHASE10_README.md",
    "docs/endpoint-triage/ENDPOINT_TRIAGE_INVENTORY.md",
    "docs/endpoint-triage/endpoint_triage_inventory.csv",
    "docs/endpoint-triage/endpoint_triage_summary.json",
    "docs/endpoint-triage/port_queue.csv",
    "docs/endpoint-triage/replace_queue.csv",
    "docs/endpoint-triage/quarantine_queue.csv",
    "docs/endpoint-triage/retire_queue.csv",
    "docs/ENDPOINT_TRIAGE_TEMPLATE.md",
}

@dataclass(frozen=True)
class Finding:
    path: Path
    line_no: int
    line: str


def iter_files(root: Path):
    for entry in PRODUCTION_FILES:
        path = root / entry
        if not path.exists():
            continue
        if path.is_file():
            yield path
            continue
        for file_path in path.rglob("*"):
            if file_path.is_file() and file_path.suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pyc", ".pyo"}:
                if "__pycache__" not in file_path.parts:
                    yield file_path


def scan_file(root: Path, path: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    if rel in ALLOWED_FILES:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    findings: list[Finding] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(path=path.relative_to(root), line_no=idx, line=line.strip()))
                break
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate that app.py is retired from production/runtime surfaces.")
    parser.add_argument("--root", default=".", help="Project root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    failures: list[str] = []
    if (root / "app.py").exists():
        failures.append("root app.py still exists; delete it or move it outside the production tree before release")

    findings: list[Finding] = []
    for path in iter_files(root):
        findings.extend(scan_file(root, path))

    if findings:
        failures.append("production/runtime files still reference the retired legacy app.py path:")
        for finding in findings[:50]:
            failures.append(f"  {finding.path}:{finding.line_no}: {finding.line}")
        if len(findings) > 50:
            failures.append(f"  ... {len(findings) - 50} more findings")

    if failures:
        print("app.py retirement validation failed", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 2

    print("app.py retirement validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
