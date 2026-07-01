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


def test_sync_propline_props_respects_adaptive_pull_budget(monkeypatch):
    from mlb_app.integrations.propline import client as propline_client

    events = [
        {"id": "event-1", "away_team": "NYY", "home_team": "BOS", "commence_time": "2026-06-24T23:00:00Z"},
        {"id": "event-2", "away_team": "LAD", "home_team": "SD", "commence_time": "2026-06-24T23:00:00Z"},
        {"id": "event-3", "away_team": "CHC", "home_team": "STL", "commence_time": "2026-06-24T23:00:00Z"},
    ]
    calls: list[str] = []

    def fake_props(event_id, markets=None, sport="baseball_mlb"):
        calls.append(event_id)
        return {"bookmakers": []}

    monkeypatch.setenv("MLB_PROPLINE_MAX_DAILY_PULL_REQUESTS", "1")
    monkeypatch.setenv("MLB_PROPLINE_DAILY_RESERVE", "150")
    monkeypatch.setattr(propline_client, "get_events", lambda sport="baseball_mlb": events)
    monkeypatch.setattr(propline_client, "get_event_player_props", fake_props)
    monkeypatch.setattr(
        propline_client,
        "value_client_status",
        lambda: {"tokenGuard": {"estimatedUsed": 849, "dailyLimit": 1000, "reservedTokens": 150, "remainingUsable": 1}},
    )

    payload = svc.sync_propline_props(svc.PropLineSyncRequest(date="2026-06-24", save=False, snapshot=False))

    assert calls == ["event-1"]
    assert payload["attemptedEventCount"] == 1
    assert payload["diagnostics"]["eventsSkipped"] == 2
    assert payload["diagnostics"]["proplineMaxDailyPullRequests"] == 1
