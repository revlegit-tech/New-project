from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable


Validator = Callable[[Path], None]


def atomic_write_text(path: Path, text: str, *, validator: Validator | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    try:
        if validator is not None:
            validator(temp_path)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return path


def atomic_write_json(path: Path, payload: dict[str, Any]) -> Path:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    def validate_json(candidate: Path) -> None:
        json.loads(candidate.read_text(encoding="utf-8"))

    return atomic_write_text(path, text, validator=validate_json)
