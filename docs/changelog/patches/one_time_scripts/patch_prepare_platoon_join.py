from pathlib import Path

path = Path("prepare_market_training.py")
text = path.read_text(encoding="utf-8")

if "batter_platoon = read_optional_csv" in text:
    print("prepare_market_training.py already has platoon join logic. No patch needed.")
    raise SystemExit(0)

marker = '''    def matchup(row: pd.Series) -> Any:
'''

platoon_join = r'''
    # Join batter/pitcher platoon split features.
    batter_platoon = read_optional_csv(ROOT / "data" / "cache" / "incremental_stats" / f"batter_platoon_splits_{season}.csv")
    pitcher_platoon = read_optional_csv(ROOT / "data" / "cache" / "incremental_stats" / f"pitcher_platoon_splits_{season}.csv")

    if not batter_platoon.empty and {"player", "team"}.issubset(batter_platoon.columns) and {"player", "team"}.issubset(df.columns):
        batter_platoon = batter_platoon.copy()

        batter_keep = ["player", "team"]
        batter_rename: dict[str, str] = {}

        for src_col, out_col in {
            "avgVsLHP": "batter_avg_vs_lhp",
            "avgVsRHP": "batter_avg_vs_rhp",
            "kRateVsLHP": "batter_k_rate_vs_lhp",
            "kRateVsRHP": "batter_k_rate_vs_rhp",
            "paVsLHP": "batter_pa_vs_lhp",
            "paVsRHP": "batter_pa_vs_rhp",
            "platoonAvgGap": "batter_platoon_avg_gap",
        }.items():
            if src_col in batter_platoon.columns:
                batter_keep.append(src_col)
                batter_rename[src_col] = out_col

        if len(batter_keep) > 2:
            batter_small = (
                batter_platoon[batter_keep]
                .drop_duplicates(["player", "team"])
                .rename(columns=batter_rename)
            )
            df = df.merge(batter_small, on=["player", "team"], how="left", suffixes=("", "_new"))
            df = fill_from_new_columns(df)

    if not pitcher_platoon.empty and {"player"}.issubset(pitcher_platoon.columns) and "pitcher" in df.columns:
        pitcher_platoon = pitcher_platoon.copy()

        pitcher_keep = ["player"]
        pitcher_rename: dict[str, str] = {"player": "pitcher"}

        for src_col, out_col in {
            "avgAllowedVsLHB": "pitcher_avg_allowed_vs_lhb",
            "avgAllowedVsRHB": "pitcher_avg_allowed_vs_rhb",
            "kRateVsLHB": "pitcher_k_rate_vs_lhb",
            "kRateVsRHB": "pitcher_k_rate_vs_rhb",
            "paVsLHB": "pitcher_pa_vs_lhb",
            "paVsRHB": "pitcher_pa_vs_rhb",
            "platoonAvgGapAllowed": "pitcher_platoon_avg_gap_allowed",
        }.items():
            if src_col in pitcher_platoon.columns:
                pitcher_keep.append(src_col)
                pitcher_rename[src_col] = out_col

        if len(pitcher_keep) > 1:
            pitcher_small = (
                pitcher_platoon[pitcher_keep]
                .drop_duplicates(["player"])
                .rename(columns=pitcher_rename)
            )
            df = df.merge(pitcher_small, on="pitcher", how="left", suffixes=("", "_new"))
            df = fill_from_new_columns(df)

    # Derived matchup-specific platoon fields.
    # If pitcher handedness / batter side are unavailable, use both splits as
    # generic context but leave text matchup labels blank.
    if "throws" not in df.columns:
        df["throws"] = ""
    if "bats" not in df.columns:
        df["bats"] = ""

    throws_norm = df["throws"].astype(str).str.upper().str[0]
    bats_norm = df["bats"].astype(str).str.upper().str[0]

    if {"batter_avg_vs_lhp", "batter_avg_vs_rhp"}.issubset(df.columns):
        df["batter_avg_vs_hand"] = df["batter_avg_vs_rhp"]
        df.loc[throws_norm == "L", "batter_avg_vs_hand"] = df.loc[throws_norm == "L", "batter_avg_vs_lhp"]

        # If throw hand is missing, use average of both sides when possible.
        both_avg = df[["batter_avg_vs_lhp", "batter_avg_vs_rhp"]].apply(pd.to_numeric, errors="coerce").mean(axis=1)
        df.loc[~throws_norm.isin(["L", "R"]), "batter_avg_vs_hand"] = both_avg

    if {"batter_k_rate_vs_lhp", "batter_k_rate_vs_rhp"}.issubset(df.columns):
        df["batter_k_rate_vs_hand"] = df["batter_k_rate_vs_rhp"]
        df.loc[throws_norm == "L", "batter_k_rate_vs_hand"] = df.loc[throws_norm == "L", "batter_k_rate_vs_lhp"]

        both_k = df[["batter_k_rate_vs_lhp", "batter_k_rate_vs_rhp"]].apply(pd.to_numeric, errors="coerce").mean(axis=1)
        df.loc[~throws_norm.isin(["L", "R"]), "batter_k_rate_vs_hand"] = both_k

    if "batter_avg_vs_lhp" in df.columns:
        df["batter_recent_hits_vs_lhp"] = df["batter_avg_vs_lhp"]
    if "batter_avg_vs_rhp" in df.columns:
        df["batter_recent_hits_vs_rhp"] = df["batter_avg_vs_rhp"]

    if {"pitcher_avg_allowed_vs_lhb", "pitcher_avg_allowed_vs_rhb"}.issubset(df.columns):
        df["pitcher_avg_allowed_vs_hand"] = df["pitcher_avg_allowed_vs_rhb"]
        df.loc[bats_norm == "L", "pitcher_avg_allowed_vs_hand"] = df.loc[bats_norm == "L", "pitcher_avg_allowed_vs_lhb"]

        both_allowed = df[["pitcher_avg_allowed_vs_lhb", "pitcher_avg_allowed_vs_rhb"]].apply(pd.to_numeric, errors="coerce").mean(axis=1)
        df.loc[~bats_norm.isin(["L", "R"]), "pitcher_avg_allowed_vs_hand"] = both_allowed

    if "platoon_matchup" not in df.columns:
        df["platoon_matchup"] = ""
    df.loc[bats_norm.isin(["L", "R"]) & throws_norm.isin(["L", "R"]), "platoon_matchup"] = (
        bats_norm + "v" + throws_norm
    )

'''

if marker not in text:
    raise SystemExit("Could not find matchup marker. Send me the enrich_training_file section.")

text = text.replace(marker, platoon_join + marker)
path.write_text(text, encoding="utf-8")

print("Patched prepare_market_training.py to join platoon split features.")
