from __future__ import annotations

from datetime import date

from mlb_app.config import Settings, active_mlb_season


def test_active_mlb_season_defaults_to_calendar_year() -> None:
    assert active_mlb_season(date(2026, 5, 8)) == 2026


def test_current_season_defaults_from_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MLB_CURRENT_SEASON", "2027")
    settings = Settings.from_env(tmp_path)
    assert settings.current_season == 2027
    assert settings.season_from_query({}) == 2027


def test_explicit_query_season_overrides_setting(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MLB_CURRENT_SEASON", "2027")
    settings = Settings.from_env(tmp_path)
    assert settings.season_from_query({"season": ["2026"]}) == 2026
