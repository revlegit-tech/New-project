from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.shadow_prediction_service import ShadowPredictionService


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach post-grade targets to stored shadow predictions.")
    parser.add_argument("--grades", required=True, help="CSV or JSON rows with prediction_id and target_* fields.")
    parser.add_argument("--output", default="", help="Optional JSON report path.")
    args = parser.parse_args()

    settings = Settings.from_env(Path.cwd())
    service = ShadowPredictionService(settings=settings)
    report = service.evaluate_after_grading(_read_rows(Path(args.grades)))
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        return [dict(row) for row in rows] if isinstance(rows, list) else []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


if __name__ == "__main__":
    raise SystemExit(main())
