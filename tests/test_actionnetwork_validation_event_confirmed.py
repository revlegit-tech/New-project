from __future__ import annotations

from scripts.validate_actionnetwork_odds import (
    index_logs,
    index_logs_by_game,
    index_team_logs,
    validate_row,
)


def base_odds_row(**overrides: str) -> dict[str, str]:
    row = {
        "source": "actionnetwork",
        "game_date": "2026-06-23",
        "event_id": "event-1",
        "player_id": "99",
        "player_name": "Aaron Judge",
        "market_group": "alt_hits",
        "market": "Hits",
        "market_type": "hits",
        "line": "1.5",
        "bet_side": "over_yes",
        "american_odds": "-110",
        "collection_mode": "live_forward",
        "exclude_from_ml": "0",
    }
    row.update(overrides)
    return row


def validate_fixture(row: dict[str, str], bridge: dict[tuple[str, str], dict[str, str]]) -> dict[str, str]:
    batter_rows = [{"date": "2026-06-23", "gamePk": "game-1", "player": "Aaron Judge", "hits": "2"}]
    pitcher_rows = [{"date": "2026-06-23", "gamePk": "game-1", "player": "Pitcher One", "strikeOuts": "5"}]
    team_rows = [{"date": "2026-06-23", "gamePk": "game-1", "team": "NYY", "teamName": "Yankees", "runs": "5"}]
    batter_by_date, known_batters = index_logs(batter_rows)
    pitcher_by_date, known_pitchers = index_logs(pitcher_rows)
    team_by_date, known_teams = index_team_logs(team_rows)
    return validate_row(
        row,
        batter_by_date=batter_by_date,
        pitcher_by_date=pitcher_by_date,
        team_by_date=team_by_date,
        batter_by_game=index_logs_by_game(batter_rows),
        pitcher_by_game=index_logs_by_game(pitcher_rows),
        known_batters=known_batters,
        known_pitchers=known_pitchers,
        known_teams=known_teams,
        suspect_dates=set(),
        apply_integrity_gate=True,
        bridge_by_event=bridge,
        truth_logs_available=True,
        requested_date_covered=True,
    )


def test_confirmed_live_forward_validation_row_is_trainable() -> None:
    out = validate_fixture(
        base_odds_row(),
        {("2026-06-23", "event-1"): {"bridge_status": "confirmed", "gamePk": "game-1", "confidence": "0.9"}},
    )

    assert out["validation_status"] == "valid_labeled_event_confirmed"
    assert out["label_result"] == "win"
    assert out["exclude_from_ml"] == "0"
    assert out["gamePk"] == "game-1"


def test_missing_bridge_blocks_date_only_trainable_label() -> None:
    out = validate_fixture(base_odds_row(), {})

    assert out["validation_status"] == "event_bridge_missing"
    assert out["exclude_from_ml"] == "1"
