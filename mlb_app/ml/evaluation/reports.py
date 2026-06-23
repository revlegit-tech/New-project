from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from mlb_app.ml.evaluation.walk_forward import evaluate_walk_forward


def evaluate_csv(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    target = Path(path)
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return evaluate_walk_forward(rows, **kwargs)


def write_report(path: str | Path, report: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
