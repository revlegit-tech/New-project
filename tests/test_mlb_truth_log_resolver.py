from __future__ import annotations

from pathlib import Path

from mlb_app.services.mlb_truth_log_resolver import load_truth_logs


def write_csv(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_empty_cloud_truth_logs_fall_back_to_cache(tmp_path: Path) -> None:
    cloud = tmp_path / "cloud"
    cache = tmp_path / "cache"
    for name in ["batter", "pitcher", "team"]:
        write_csv(cloud / f"{name}_game_logs_2026.csv", "date,gamePk,player\n")
    write_csv(cache / "batter_game_logs_2026.csv", "date,gamePk,player\n2026-06-23,1,Aaron Judge\n")
    write_csv(cache / "pitcher_game_logs_2026.csv", "date,gamePk,player\n2026-06-23,1,Carlos Rodon\n")
    write_csv(cache / "team_game_logs_2026.csv", "date,gamePk,team\n2026-06-23,1,NYY\n")

    truth = load_truth_logs("2026", truth_dir=cache)

    assert truth.source_dir == cache
    assert truth.covers("2026-06-23") is True
    assert truth.covers("2026-06-24") is False
    assert truth.summary("2026-06-23")["requested_date_covered"] is True
