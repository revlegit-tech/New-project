from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.umpire_context_service import UmpireContextService


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings.from_env(tmp_path)
    return replace(settings, data_dir=tmp_path / "data", current_season=2026)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_umpire_missing_returns_neutral_fallback_and_quality_flag(tmp_path: Path) -> None:
    payload = UmpireContextService(make_settings(tmp_path)).context_for_game(
        date_label="2026-06-24",
        season=2026,
        game_pk="123",
        home_team="NYY",
        away_team="BAL",
    )

    assert payload["assignment_status"] == "neutral_fallback"
    assert payload["umpire_name"] == "Unknown"
    assert payload["k_boost"] == "0"
    assert payload["run_environment"] == "1"
    assert "neutral_fallback" in payload["quality_flags"]


def test_umpire_context_uses_existing_artifact_without_faking_assignment(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    write_csv(
        settings.data_dir / "warehouse" / "umpires" / "umpires_2026-06-24.csv",
        [
            {
                "date": "2026-06-24",
                "season": "2026",
                "game_pk": "123",
                "home_team": "NYY",
                "away_team": "BAL",
                "umpire_name": "Test Umpire",
                "assignment_status": "confirmed",
                "k_boost": "0.03",
                "run_environment": "0.98",
                "zone_tendency": "wide",
            }
        ],
    )

    payload = UmpireContextService(settings).context_for_game(date_label="2026-06-24", season=2026, game_pk="123")

    assert payload["assignment_status"] == "confirmed"
    assert payload["umpire_name"] == "Test Umpire"
    assert "neutral_fallback" not in payload["quality_flags"]
