from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.game_market_context_service import GameMarketContextService, NORMALIZED_GAME_MARKET_FIELDS


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    return replace(settings, data_dir=tmp_path / "data", current_season=2026)


def test_game_market_context_service_returns_context_by_team_opponent(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = GameMarketContextService(settings)
    path = service.normalized_path("2026-06-24")
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"date": "2026-06-24", "season": 2026, "event_id": "evt1", "game_id": "evt1", "team": "LAD", "opponent": "SDP", "market": "moneyline", "american_odds": "-140", "snapshot_at": "2026-06-24T12:00:00Z"},
        {"date": "2026-06-24", "season": 2026, "event_id": "evt1", "game_id": "evt1", "team": "", "opponent": "", "market": "game_total", "side": "Over", "line": "8.5", "american_odds": "-110", "snapshot_at": "2026-06-24T12:00:00Z"},
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(NORMALIZED_GAME_MARKET_FIELDS), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    context = service.context_by_team(date_label="2026-06-24", team="LAD", opponent="SDP")

    assert context["date"] == "2026-06-24"
    assert context["moneyline"]["market"] == "moneyline"
    assert context["sourceStatus"] == "partial"
