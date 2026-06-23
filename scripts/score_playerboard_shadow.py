from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from mlb_app.config import Settings
from mlb_app.services.shadow_prediction_service import ShadowPredictionService


def main() -> int:
    parser = argparse.ArgumentParser(description="Score playerboard rows with registered models in shadow mode.")
    parser.add_argument("--input", required=True, help="Playerboard CSV or JSON input.")
    parser.add_argument("--output", default="", help="Optional JSON report path.")
    parser.add_argument("--stage", default="shadow", choices=["candidate", "shadow", "production"])
    parser.add_argument("--model-key", default="")
    parser.add_argument("--no-persist", action="store_true", help="Do not write shadow predictions to storage.")
    args = parser.parse_args()

    settings = Settings.from_env(Path.cwd())
    service = ShadowPredictionService(settings=settings)
    report = service.score_rows(
        _read_rows(Path(args.input)),
        model_stage=args.stage,
        model_key=args.model_key or None,
        persist=not args.no_persist,
    )
    text = json.dumps(_safe_report(report), indent=2, sort_keys=True, default=str)
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


def _safe_report(report: dict[str, Any]) -> dict[str, Any]:
    payload = dict(report)
    payload["rows"] = payload.get("rows", [])[:10]
    payload["previewRowCount"] = len(payload["rows"])
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
