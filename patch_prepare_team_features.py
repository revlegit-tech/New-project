from pathlib import Path

path = Path("prepare_market_training.py")
text = path.read_text(encoding="utf-8")

if "team_totals = read_optional_csv" in text:
    print("prepare_market_training.py already has team feature join logic. No patch needed.")
    raise SystemExit(0)

marker = '''    def matchup(row: pd.Series) -> Any:
'''

team_join = r'''
    # Join team/opponent season context features.
    team_totals = read_optional_csv(ROOT / "data" / "cache" / "incremental_stats" / f"team_totals_{season}.csv")

    if not team_totals.empty and "team" in team_totals.columns and "team" in df.columns:
        team_totals = team_totals.copy()

        team_keep = ["team"]
        team_rename: dict[str, str] = {}

        for src_col, out_col in {
            "strikeoutsPerGame": "team_k_rate",
            "walksPerGame": "team_walk_rate",
            "runsPerGame": "team_runs_per_game",
            "hitsPerGame": "team_hits_per_game",
            "homeRunsPerGame": "team_hr_per_game",
        }.items():
            if src_col in team_totals.columns:
                team_keep.append(src_col)
                team_rename[src_col] = out_col

        if len(team_keep) > 1:
            team_small = (
                team_totals[team_keep]
                .drop_duplicates(["team"])
                .rename(columns=team_rename)
            )
            df = df.merge(team_small, on="team", how="left", suffixes=("", "_new"))
            df = fill_from_new_columns(df)

    if not team_totals.empty and "team" in team_totals.columns and "opponent" in df.columns:
        opp_keep = ["team"]
        opp_rename: dict[str, str] = {"team": "opponent"}

        for src_col, out_col in {
            "runsAllowedPerGame": "opponent_rate",
            "hitsAllowedPerGame": "opponent_hits_allowed_per_game",
            "pitchingStrikeoutsPerGame": "opponent_pitching_k_per_game",
            "pitchingWalksPerGame": "opponent_pitching_walks_per_game",
            "pitchingHomeRunsPerGame": "opponent_pitching_hr_per_game",
        }.items():
            if src_col in team_totals.columns:
                opp_keep.append(src_col)
                opp_rename[src_col] = out_col

        if len(opp_keep) > 1:
            opp_small = (
                team_totals[opp_keep]
                .drop_duplicates(["team"])
                .rename(columns=opp_rename)
            )
            df = df.merge(opp_small, on="opponent", how="left", suffixes=("", "_new"))
            df = fill_from_new_columns(df)

    # Temporary real-data fallback until a true bullpen-only recent ERA file exists.
    if "opponent_bullpen_era_7d" not in df.columns and "opponent_rate" in df.columns:
        df["opponent_bullpen_era_7d"] = df["opponent_rate"]
    elif "opponent_bullpen_era_7d" in df.columns and "opponent_rate" in df.columns:
        df["opponent_bullpen_era_7d"] = df["opponent_bullpen_era_7d"].fillna(df["opponent_rate"])

'''

if marker not in text:
    raise SystemExit("Could not find matchup marker. Send me the enrich_training_file section.")

text = text.replace(marker, team_join + marker)
path.write_text(text, encoding="utf-8")

print("Patched prepare_market_training.py to join team/opponent features.")
