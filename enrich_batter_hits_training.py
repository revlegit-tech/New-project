# -*- coding: utf-8 -*-
import re
import unicodedata
from pathlib import Path
import pandas as pd

SEASON = 2026
TRAINING_PATH = Path("data/training/batter_hits_training.csv")
OUT_PATH = Path("data/training/batter_hits_training_enriched.csv")

def clean_name(value):
    value = "" if pd.isna(value) else str(value)
    value = re.sub(r"\s*\([^)]*\)\s*$", "", value)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9 ]+", "", value)
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value

def load_csv(path):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)

def fill_from_new_columns(df):
    for col in list(df.columns):
        if col.endswith("_new"):
            base = col[:-4]
            if base in df.columns:
                df[base] = df[base].combine_first(df[col])
                df = df.drop(columns=[col])
            else:
                df = df.rename(columns={col: base})
    return df

def merge_by_clean_player(df, src, src_player_col, mappings, left_col="player"):
    if src.empty or src_player_col not in src.columns:
        return df

    src = src.copy()
    src["_join_player"] = src[src_player_col].map(clean_name)

    keep = ["_join_player"]
    rename = {}
    for src_col, out_col in mappings.items():
        if src_col in src.columns:
            keep.append(src_col)
            rename[src_col] = out_col

    if len(keep) == 1:
        return df

    src = src[keep].drop_duplicates("_join_player").rename(columns=rename)

    df = df.copy()
    df["_join_player"] = df[left_col].map(clean_name)
    df = df.merge(src, on="_join_player", how="left", suffixes=("", "_new"))
    df = fill_from_new_columns(df)
    return df.drop(columns=["_join_player"])

def merge_by_clean_pitcher(df, src, src_player_col, mappings):
    if src.empty or src_player_col not in src.columns or "pitcher" not in df.columns:
        return df

    src = src.copy()
    src["_join_pitcher"] = src[src_player_col].map(clean_name)

    keep = ["_join_pitcher"]
    rename = {}
    for src_col, out_col in mappings.items():
        if src_col in src.columns:
            keep.append(src_col)
            rename[src_col] = out_col

    if len(keep) == 1:
        return df

    src = src[keep].drop_duplicates("_join_pitcher").rename(columns=rename)

    df = df.copy()
    df["_join_pitcher"] = df["pitcher"].map(clean_name)
    df = df.merge(src, on="_join_pitcher", how="left", suffixes=("", "_new"))
    df = fill_from_new_columns(df)
    return df.drop(columns=["_join_pitcher"])

df = pd.read_csv(TRAINING_PATH)
df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date.astype(str)

batter_totals = load_csv(f"data/cache/incremental_stats/batter_totals_{SEASON}.csv")
batter_recent = load_csv(f"data/cache/incremental_stats/batter_recent_{SEASON}.csv")
pitcher_totals = load_csv(f"data/cache/incremental_stats/pitcher_totals_{SEASON}.csv")
pitcher_recent = load_csv(f"data/cache/incremental_stats/pitcher_recent_{SEASON}.csv")
savant_batter = load_csv(f"data/cache/savant/savant_batter_quality_{SEASON}.csv")
savant_pitcher = load_csv(f"data/cache/savant/savant_pitcher_quality_{SEASON}.csv")
weather = load_csv(f"data/cache/weather/weather_features_{SEASON}.csv")
movement = load_csv(f"data/cache/odds_movement/prop_movement_{SEASON}.csv")

df = merge_by_clean_player(df, batter_totals, "player", {
    "babip": "batter_babip",
    "kRate": "batter_k_rate",
    "bbRate": "batter_walk_rate",
    "avgHome": "batter_avg_home",
    "avgAway": "batter_avg_away",
    "hitsPerGame": "season_rate",
})

df = merge_by_clean_player(df, batter_recent, "player", {
    "games": "recent_games",
    "last5HitsPerGame": "rolling_avg_5",
    "last10HitsPerGame": "rolling_avg_10",
    "last15HitsPerGame": "rolling_avg_15",
    "last10TotalBasesPerGame": "rolling_total_bases_10",
    "last15HomeRunsPerGame": "rolling_hr_rate_15",
    "last10StrikeoutsPerGame": "rolling_k_rate_10",
    "last10HitsPerGame": "recent_rate",
    "daysRest": "batter_days_rest",
})

df = merge_by_clean_player(df, savant_batter, "player", {
    "barrelRate": "barrel_rate",
    "hardHitRate": "hard_hit_rate",
    "avgXWOBA": "xwoba",
    "avgXBA": "xba",
    "avgXSLG": "xslg",
    "ldRate": "batter_ld_rate",
    "gbRate": "batter_gb_rate",
    "sprintSpeed": "batter_sprint_speed",
    "babip": "batter_babip",
})

df = merge_by_clean_pitcher(df, pitcher_totals, "player", {
    "kRate": "pitcher_k_rate",
    "bbRate": "pitcher_walk_rate",
    "hrPer9": "pitcher_hr_rate",
    "babip": "pitcher_babip",
})

df = merge_by_clean_pitcher(df, pitcher_recent, "player", {
    "daysRest": "pitcher_days_rest",
})

df = merge_by_clean_pitcher(df, savant_pitcher, "player", {
    "veloDelta": "pitcher_velo_delta",
})

if not movement.empty:
    movement = movement.copy()
    movement["date"] = pd.to_datetime(movement["date"], errors="coerce").dt.date.astype(str)
    movement["_join_player"] = movement["player"].map(clean_name)
    df["_join_player"] = df["player"].map(clean_name)

    keep = ["date", "market", "_join_player"]
    rename = {}
    for src_col, out_col in {"lineMove": "line_move", "oddsMove": "odds_move"}.items():
        if src_col in movement.columns:
            keep.append(src_col)
            rename[src_col] = out_col

    move_small = movement[keep].drop_duplicates(["date", "market", "_join_player"]).rename(columns=rename)
    df = df.merge(move_small, on=["date", "market", "_join_player"], how="left", suffixes=("", "_new"))
    df = fill_from_new_columns(df)
    df = df.drop(columns=["_join_player"])

if not weather.empty:
    weather = weather.copy()
    weather["date"] = pd.to_datetime(weather["date"], errors="coerce").dt.date.astype(str)

    weather_rows = []
    for _, row in weather.iterrows():
        base = {
            "date": row.get("date"),
            "venue": row.get("venue"),
            "roof": row.get("roof"),
            "temperature": row.get("temperatureF"),
            "wind_mph": row.get("windMph"),
            "wind_out_score": row.get("windOutScore"),
            "wind_out_flag": row.get("windOutFlag"),
            "turf_flag": row.get("turfFlag"),
            "cold_game_flag": row.get("coldGameFlag"),
        }
        home = row.get("home")
        away = row.get("away")
        if pd.notna(home):
            weather_rows.append({**base, "team": home, "opponent": away})
        if pd.notna(away):
            weather_rows.append({**base, "team": away, "opponent": home})

    weather_join = pd.DataFrame(weather_rows)
    if not weather_join.empty:
        df = df.merge(weather_join, on=["date", "team", "opponent"], how="left", suffixes=("", "_new"))
        df = fill_from_new_columns(df)

def platoon_matchup(row):
    t = str(row.get("throws") or "").strip().upper()[:1]
    b = str(row.get("bats") or "").strip().upper()[:1]
    if b == "S":
        return "switch_hitter"
    if t in {"L", "R"} and b in {"L", "R"}:
        return "same_side" if t == b else "opposite_side"
    return row.get("platoon_matchup")

if "platoon_matchup" in df.columns:
    df["platoon_matchup"] = df.apply(platoon_matchup, axis=1)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT_PATH, index=False)

print(f"Wrote {OUT_PATH}")
print("rows:", len(df), "cols:", len(df.columns))

features = [
    "line_move", "odds_move",
    "batter_babip", "batter_days_rest", "batter_k_rate", "batter_walk_rate",
    "barrel_rate", "hard_hit_rate", "xwoba", "xba", "xslg",
    "batter_ld_rate", "batter_gb_rate", "batter_sprint_speed",
    "pitcher_babip", "pitcher_days_rest", "pitcher_velo_delta",
    "pitcher_k_rate", "pitcher_walk_rate", "pitcher_hr_rate",
    "wind_out_score", "wind_out_flag", "turf_flag", "cold_game_flag",
]

print("\nCoverage:")
for col in features:
    if col not in df.columns:
        print(f"missing {col}")
    else:
        print(f"{col:28s} {df[col].notna().mean()*100:6.2f}% non-null | unique={df[col].nunique(dropna=True)}")
