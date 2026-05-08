from __future__ import annotations

import csv
from pathlib import Path

from mlb_app.services import propline_props_service as svc


def test_save_props_csv_writes_odds_and_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(svc, "ODDS_DIR", tmp_path / "data" / "odds")
    monkeypatch.setattr(svc, "WAREHOUSE_SNAPSHOT_DIR", tmp_path / "data" / "warehouse" / "odds_snapshots")
    result = svc.save_props_csv([
        {"eventDateLocal": "2026-05-07", "market": "batter_hits", "player": "Test Player", "americanOdds": -110}
    ], "2026-05-07", snapshot=True)
    odds_path = Path(result["savedPath"])
    snapshot_path = Path(result["snapshotPath"])
    assert odds_path.exists()
    assert snapshot_path.exists()
    with odds_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["player"] == "Test Player"
    assert rows[0]["market"] == "batter_hits"


def test_normalize_prop_splits_player_team():
    event = {"id": "1", "away_team": "NYY", "home_team": "BOS", "commence_time": "2026-05-07T23:00:00Z"}
    book = {"title": "DraftKings", "key": "draftkings"}
    market = {"key": "batter_hits"}
    outcome = {"description": "Aaron Judge (NYY)", "name": "Over", "point": 0.5, "price": -120}
    row = svc.normalize_prop(event, book, market, outcome)
    assert row["player"] == "Aaron Judge"
    assert row["team"] == "NYY"
    assert row["game"] == "NYY @ BOS"
