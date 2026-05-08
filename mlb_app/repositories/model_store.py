from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ModelStore:
    """Repository for model artifacts, feature metadata, and registry files."""

    def __init__(self, model_dir: str | Path) -> None:
        self.model_dir = Path(model_dir)

    def model_path_for_market(self, market: str) -> Path:
        key = normalize_market_key(market)
        return self.model_dir / f"prop_model_{key}.joblib"

    def metadata_path_for_model(self, model_path: str | Path) -> Path:
        path = Path(model_path)
        return path.with_name(f"{path.stem}_features.json")

    def load_registry(self, path: str | Path) -> dict[str, Any]:
        target = Path(path)
        if not target.exists():
            return {}
        with target.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Model registry must be a JSON object keyed by market")
        return payload


def normalize_market_key(value: object) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")
