from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class LockState:
    acquired: bool
    path: Path
    status: str
    warning: str = ""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def _age_seconds(path: Path, now: datetime | None = None) -> float:
    now = now or utc_now()
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return max(0.0, (now - modified).total_seconds())


@contextmanager
def runtime_lock(lock_path: Path, *, stale_after_seconds: int = 3600) -> Iterator[LockState]:
    """Acquire a small JSON lock file with stale-lock recovery."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    warning = ""
    if lock_path.exists():
        age = _age_seconds(lock_path)
        if age < stale_after_seconds:
            yield LockState(False, lock_path, "locked", f"Fresh lock exists ({int(age)}s old).")
            return
        warning = f"Recovered stale lock ({int(age)}s old)."
        lock_path.unlink(missing_ok=True)

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        yield LockState(False, lock_path, "locked", "Lock was acquired by another process.")
        return

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"created_at": iso_now(), "pid": os.getpid()}, handle)

    try:
        yield LockState(True, lock_path, "acquired", warning)
    finally:
        lock_path.unlink(missing_ok=True)
