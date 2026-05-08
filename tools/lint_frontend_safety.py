#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TARGETS = ("public/outlier-*.js", "public/trust-surface.js")

PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("unsafe_markup_assignment", re.compile(r"\.innerHTML\s*[+]?="), "Do not assign markup strings in trust-critical UI; construct nodes and use textContent."),
    ("unsafe_markup_insertion", re.compile(r"\.insertAdjacentHTML\s*\("), "Do not insert markup strings with API-sourced content."),
    ("silent_catch", re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}"), "Do not silently swallow rendering or contract failures."),
    ("dangerous_eval", re.compile(r"\b(eval|Function)\s*\("), "Do not evaluate dynamic strings in frontend modules."),
)

ALLOW_MARKER = "frontend-safety-allow"

@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    kind: str
    message: str
    source: str


def iter_files(root: Path, patterns: list[str]) -> list[Path]:
    files: set[Path] = set()
    for pattern in patterns:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(files)


def scan_file(path: Path, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    rel = path.relative_to(root)
    for line_number, line in enumerate(lines, start=1):
        if ALLOW_MARKER in line:
            continue
        for kind, pattern, message in PATTERNS:
            if pattern.search(line):
                findings.append(Finding(rel, line_number, kind, message, line.strip()))
    return findings


def scan(root: Path, patterns: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_files(root, patterns):
        findings.extend(scan_file(path, root))
    return findings


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan trust-critical frontend modules for unsafe rendering patterns.")
    parser.add_argument("--root", default=".", help="Project root")
    parser.add_argument("--target", action="append", help="Glob to scan. May be repeated. Defaults to Outlier modules and trust surface.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = Path(args.root).resolve()
    targets = args.target or list(DEFAULT_TARGETS)
    findings = scan(root, targets)
    for finding in findings:
      print(f"{finding.path}:{finding.line}: {finding.kind}: {finding.message}\n  {finding.source}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
