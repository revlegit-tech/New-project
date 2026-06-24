from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.collector_verification_service import CollectorVerificationService
from mlb_app.services.data_source_capability_service import DataSourceCapabilityService


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    data_dir = tmp_path / "data"
    return replace(settings, data_dir=data_dir, db_path=data_dir / "mlb_app_state.sqlite3", current_season=2026)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_collector_check_includes_game_markets(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(settings.data_dir / "warehouse" / "normalized" / "game_markets" / "game_markets_2026-06-24.csv", [{"date": "2026-06-24", "market": "moneyline"}])

    payload = CollectorVerificationService(settings=settings).payload(date_label="2026-06-24", season=2026)

    assert payload["checks"]["gameMarkets"]["ok"] is True
    assert payload["counts"]["gameMarketRows"] == 1


def test_data_source_capabilities_detects_normalized_game_market_artifacts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(settings.data_dir / "warehouse" / "normalized" / "game_markets" / "game_markets_2026-06-24.csv", [{"date": "2026-06-24", "market": "moneyline"}])

    payload = DataSourceCapabilityService(settings).payload(date_label="2026-06-24", season=2026)

    assert payload["sources"]["gameMarkets"]["available"] is True
