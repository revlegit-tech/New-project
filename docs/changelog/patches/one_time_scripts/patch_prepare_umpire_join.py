from pathlib import Path

path = Path("prepare_market_training.py")
text = path.read_text(encoding="utf-8")

if "umpire_stats = read_optional_csv" in text:
    print("prepare_market_training.py already has umpire join logic. No patch needed.")
    raise SystemExit(0)

marker = '''    def matchup(row: pd.Series) -> Any:
'''

umpire_join = r'''
    # Join real home-plate umpire assignments and umpire tendency stats.
    # game_umpires_YEAR.csv is joined by date/team/opponent. umpire_stats_YEAR.csv
    # is joined by homePlateUmpireId -> umpireId.
    umpire_games = read_optional_csv(ROOT / "data" / "cache" / "umpires" / f"game_umpires_{season}.csv")
    umpire_stats = read_optional_csv(ROOT / "data" / "cache" / "umpires" / f"umpire_stats_{season}.csv")

    if (
        not umpire_games.empty
        and {"date", "homeTeam", "awayTeam", "homePlateUmpireId", "homePlateUmpireName"}.issubset(umpire_games.columns)
        and {"date", "team", "opponent"}.issubset(df.columns)
    ):
        umpire_games = umpire_games.copy()
        umpire_games["date"] = pd.to_datetime(umpire_games["date"], errors="coerce").dt.date.astype(str)

        umpire_rows: list[dict[str, Any]] = []
        for _, row in umpire_games.iterrows():
            base = {
                "date": row.get("date"),
                "homePlateUmpireId": row.get("homePlateUmpireId"),
                "umpire": row.get("homePlateUmpireName"),
            }
            home = row.get("homeTeam")
            away = row.get("awayTeam")

            if pd.notna(home):
                umpire_rows.append({**base, "team": home, "opponent": away})
            if pd.notna(away):
                umpire_rows.append({**base, "team": away, "opponent": home})

        umpire_join = pd.DataFrame(umpire_rows)

        if not umpire_stats.empty and {"umpireId"}.issubset(umpire_stats.columns):
            umpire_stats = umpire_stats.copy()
            umpire_stats["homePlateUmpireId"] = umpire_stats["umpireId"].astype(str)

            stat_keep = ["homePlateUmpireId"]
            stat_rename: dict[str, str] = {}

            mappings = {
                "kRateFavorBatter": "ump_k_rate",
                "zoneSizeZscore": "ump_zone_size_zscore",
                "bbRateFavorBatter": "ump_favor_batter_score",
                "gamesUmped": "ump_games_umped",
            }

            for src_col, out_col in mappings.items():
                if src_col in umpire_stats.columns:
                    stat_keep.append(src_col)
                    stat_rename[src_col] = out_col

            if len(stat_keep) > 1:
                umpire_stats_small = (
                    umpire_stats[stat_keep]
                    .drop_duplicates(["homePlateUmpireId"])
                    .rename(columns=stat_rename)
                )
                umpire_join["homePlateUmpireId"] = umpire_join["homePlateUmpireId"].astype(str)
                umpire_join = umpire_join.merge(
                    umpire_stats_small,
                    on="homePlateUmpireId",
                    how="left",
                    suffixes=("", "_new"),
                )
                umpire_join = fill_from_new_columns(umpire_join)

        # If real IDs/names exist but tendency stats are neutral/fallback, keep explicit
        # zero values instead of all-null features so the ML pipeline can consume them.
        for col in ["ump_k_rate", "ump_zone_size_zscore", "ump_favor_batter_score"]:
            if col not in umpire_join.columns:
                umpire_join[col] = 0.0
            else:
                umpire_join[col] = pd.to_numeric(umpire_join[col], errors="coerce").fillna(0.0)

        keep_cols = [
            col for col in [
                "date",
                "team",
                "opponent",
                "umpire",
                "homePlateUmpireId",
                "ump_k_rate",
                "ump_zone_size_zscore",
                "ump_favor_batter_score",
                "ump_games_umped",
            ]
            if col in umpire_join.columns
        ]

        if len(keep_cols) > 3:
            umpire_join = umpire_join[keep_cols].drop_duplicates(["date", "team", "opponent"])
            df = df.merge(umpire_join, on=["date", "team", "opponent"], how="left", suffixes=("", "_new"))
            df = fill_from_new_columns(df)

'''

if marker not in text:
    raise SystemExit("Could not find matchup marker. Send me the enrich_training_file section.")

text = text.replace(marker, umpire_join + marker)
path.write_text(text, encoding="utf-8")

print("Patched prepare_market_training.py to join umpire assignments and stats.")
