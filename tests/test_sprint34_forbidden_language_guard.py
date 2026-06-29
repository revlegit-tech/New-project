from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = [
    ROOT / "frontend" / "src" / "outlier",
    ROOT / "mlb_app" / "services" / "edge_board_service.py",
    ROOT / "mlb_app" / "services" / "edge_report_service.py",
]

FORBIDDEN_PATTERNS = [
    re.compile(r"\block\b", re.IGNORECASE),
    re.compile(r"\bguaranteed\b", re.IGNORECASE),
    re.compile(r"\bmust\s+bet\b", re.IGNORECASE),
    re.compile(r"\bfree\s+money\b", re.IGNORECASE),
    re.compile(r"\bautomatic\s+profit\b", re.IGNORECASE),
    re.compile(r"\bcan(?:'|’)?t\s+lose\b", re.IGNORECASE),
    re.compile(r"\bsure\s+thing\b", re.IGNORECASE),
]


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for path in SOURCE_PATHS:
        if path.is_file():
            files.append(path)
        else:
            files.extend(
                item
                for item in path.rglob("*")
                if item.suffix in {".ts", ".tsx", ".js", ".css", ".py"} and item.is_file()
            )
    return files


def test_ui_and_report_sources_do_not_use_forbidden_certainty_language() -> None:
    offenders: list[str] = []
    for path in iter_source_files():
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(ROOT)} matched {pattern.pattern}")

    assert offenders == []
