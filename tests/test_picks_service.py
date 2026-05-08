from __future__ import annotations

from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.bankroll_service import BankrollService
from mlb_app.services.picks_service import PicksService


def test_my_picks_create_defaults_to_watchlist_for_research_only(tmp_path: Path) -> None:
    service = PicksService(Settings.from_env(tmp_path))
    payload = service.create(
        {
            "date": "2026-05-07",
            "player": "Aaron Judge",
            "team": "NYY",
            "opponent": "BAL",
            "market": "batter_total_bases",
            "marketDisplay": "Batter Total Bases",
            "line": "1.5",
            "americanOdds": "-110",
            "decisionLabel": "Watchlist",
            "readinessLabel": "Research only",
            "suggestedStake": "Research only",
            "stakeUnits": 1.0,
        }
    )
    assert payload["pick"]["status"] == "Watching"
    assert payload["pick"]["stakeUnits"] == 0.0
    assert payload["pick"]["stakeAmount"] == 0.0
    assert service.payload()["pickCount"] == 1


def test_bankroll_caps_stake_and_exposure_warnings(tmp_path: Path) -> None:
    settings = Settings.from_env(tmp_path)
    bankroll = BankrollService(settings)
    bankroll.update({"bankroll": 2000, "defaultUnitSize": 20, "maxUnitsPerBet": 0.25, "maxBetsPerSlate": 1, "maxExposurePerGameUnits": 0.25})
    service = PicksService(settings, bankroll_service=bankroll)
    created = service.create({"date": "2026-05-07", "player": "Juan Soto", "team": "NYM", "opponent": "PHI", "market": "batter_hits", "line": "0.5", "americanOdds": "-120", "decisionLabel": "Potential edge", "readinessLabel": "Production candidate", "suggestedStake": "0.25u capped", "stakeUnits": 2.0})
    assert created["pick"]["stakeUnits"] == 0.25
    assert created["pick"]["stakeAmount"] == 5.0
    service.create({"date": "2026-05-07", "player": "Pete Alonso", "team": "NYM", "opponent": "PHI", "market": "batter_hits", "line": "0.5", "americanOdds": "-110", "decisionLabel": "Potential edge", "readinessLabel": "Production candidate", "suggestedStake": "0.25u capped", "stakeUnits": 0.25})
    exposure = service.payload()["exposure"]
    assert exposure["activePickCount"] == 2
    assert any("max bets" in warning.lower() for warning in exposure["warnings"])
    assert any("Game exposure cap exceeded" in warning for warning in exposure["warnings"])


def test_update_pick_lifecycle_and_profit(tmp_path: Path) -> None:
    service = PicksService(Settings.from_env(tmp_path))
    created = service.create({"date": "2026-05-07", "player": "Tarik Skubal", "team": "DET", "opponent": "CLE", "market": "pitcher_strikeouts", "line": "6.5", "americanOdds": "+105", "decisionLabel": "Potential edge", "readinessLabel": "Production candidate", "suggestedStake": "0.25u capped", "stakeUnits": 0.25})
    updated = service.update({"id": created["pick"]["id"], "status": "Won", "profitUnits": 0.26})
    assert updated["pick"]["status"] == "Won"
    assert service.payload()["exposure"]["profitUnits"] == 0.26
