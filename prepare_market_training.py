from __future__ import annotations

"""Prepare clean ML training files for any supported player prop market.

Examples:
    python prepare_market_training.py --market batter_home_runs
    python prepare_market_training.py --market batter_hits
    python prepare_market_training.py --market batter_total_bases
    python prepare_market_training.py --market pitcher_strikeouts
    python prepare_market_training.py --market pitcher_hits_allowed
    python prepare_market_training.py --market pitcher_earned_runs

Input default:
    data/training/historical_props_with_game_odds.csv

Fallback:
    data/training/historical_props.csv

Output default:
    data/training/<market>_training.csv
"""

import argparse
import csv
import re
import unicodedata

import pandas as pd
from pathlib import Path
from typing import Any
from collections import Counter

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

SUPPORTED_MARKETS = {
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "batter_rbis",
    "batter_stolen_bases",
    "team_total_runs",
    "team_first_to_score",
    "pitcher_strikeouts",
    "pitcher_hits_allowed",
    "pitcher_earned_runs",
}

DEFAULT_INPUTS = [
    DATA_DIR / "training" / "historical_props_with_game_odds.csv",
    DATA_DIR / "training" / "historical_props.csv",
]

BASE_COLUMNS = [
    "date",
    "player",
    "market",
    "line",
    "american_odds",
    "actual",
    "over",
    "team",
    "opponent",
    "book",
    "side",
    "game",
    "event_id",
]

GAME_ODDS_COLUMNS = [
    "team_moneyline",
    "opponent_moneyline",
    "game_total",
    "open_team_moneyline",
    "close_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "close_game_total",
    "total_move",
    "moneyline_implied_probability",
    "favorite_status",
    "team_implied_runs",
    "opponent_implied_runs",
    "opponent_implied_runs_proxy",
]

MODEL_FEATURE_COLUMNS = [
    "line", "book_implied_probability", "line_move", "odds_move", "vig_pct",
    "recent_games", "recent_rate", "season_rate",
    "rolling_avg_5", "rolling_avg_10", "rolling_avg_15",
    "rolling_total_bases_10", "rolling_hr_rate_15", "rolling_k_rate_10",
    "batter_babip", "batter_k_rate", "batter_walk_rate", "batter_days_rest",
    "batter_avg_home", "batter_avg_away",
    "barrel_rate", "hard_hit_rate", "xwoba", "xba", "xslg",
    "batter_ld_rate", "batter_gb_rate", "batter_sprint_speed",
    "batter_avg_vs_hand", "batter_k_rate_vs_hand",
    "batter_recent_hits_vs_lhp", "batter_recent_hits_vs_rhp",
    "pitcher_k_rate", "pitcher_walk_rate", "pitcher_hr_rate",
    "pitcher_babip", "pitcher_days_rest", "pitcher_velo_delta",
    "pitcher_avg_allowed_vs_hand",
    "team_k_rate", "team_walk_rate", "opponent_rate", "opponent_bullpen_era_7d",
    "ump_k_rate", "ump_zone_size_zscore", "ump_favor_batter_score",
    "park_factor", "hit_factor", "hr_factor", "k_factor",
    "temperature", "wind_mph", "wind_out_score", "wind_out_flag",
    "turf_flag", "cold_game_flag",
    "pitcher", "team", "opponent", "throws", "bats", "venue", "roof", "platoon_matchup",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def to_float(value: Any) -> float | None:
    text = clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def first_existing_input() -> Path:
    for path in DEFAULT_INPUTS:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Could not find data/training/historical_props_with_game_odds.csv "
        "or data/training/historical_props.csv"
    )


def normalize_over(row: dict[str, Any]) -> str:
    text = clean(row.get("over")).lower()

    if text in {"1", "true", "yes", "y", "over", "hit", "won", "win"}:
        return "1"

    if text in {"0", "false", "no", "n", "under", "miss", "lost", "loss"}:
        return "0"

    actual = to_float(row.get("actual"))
    line = to_float(row.get("line"))

    if actual is not None and line is not None:
        return "1" if actual > line else "0"

    return ""


def prepare_market(input_path: Path, output_path: Path, market: str) -> dict[str, Any]:
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {market}. Supported: {sorted(SUPPORTED_MARKETS)}")

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    fieldnames = []
    for column in BASE_COLUMNS + GAME_ODDS_COLUMNS + MODEL_FEATURE_COLUMNS:
        if column not in fieldnames:
            fieldnames.append(column)

    clean_rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str, str, str]] = set()

    for row in rows:
        if clean(row.get("market")) != market:
            continue

        line = clean(row.get("line"))
        actual = clean(row.get("actual"))
        over = normalize_over(row)

        if not line or not over:
            continue

        out: dict[str, str] = {}
        for column in fieldnames:
            out[column] = clean(row.get(column))

        out["market"] = market
        out["line"] = line
        out["actual"] = actual
        out["over"] = over

        if not out.get("park_factor"):
            out["park_factor"] = "1.0"

        if not out.get("opponent_rate") and out.get("opponent_implied_runs_proxy"):
            out["opponent_rate"] = out["opponent_implied_runs_proxy"]

        key = (
            out.get("date", ""),
            out.get("player", ""),
            out.get("market", ""),
            out.get("line", ""),
            out.get("actual", ""),
            out.get("book", ""),
            out.get("side", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        clean_rows.append(out)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in clean_rows:
            writer.writerow({column: row.get(column, "") for column in fieldnames})

    class_counts = Counter(row["over"] for row in clean_rows)

    return {
        "market": market,
        "input": str(input_path),
        "output": str(output_path),
        "inputRows": len(rows),
        "trainingRows": len(clean_rows),
        "classCounts": dict(class_counts),
        "canTrain": len(class_counts) >= 2,
    }



def clean_join_name(value: Any) -> str:
    value = "" if value is None else str(value)
    value = re.sub(r"\s*\([^)]*\)\s*$", "", value)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9 ]+", "", value)
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def read_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def fill_from_new_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in list(df.columns):
        if col.endswith("_new"):
            base = col[:-4]
            if base in df.columns:
                df[base] = df[base].combine_first(df[col])
                df = df.drop(columns=[col])
            else:
                df = df.rename(columns={col: base})
    return df


def merge_by_clean_key(
    df: pd.DataFrame,
    src: pd.DataFrame,
    left_col: str,
    src_col: str,
    mappings: dict[str, str],
    join_name: str,
) -> pd.DataFrame:
    if src.empty or src_col not in src.columns or left_col not in df.columns:
        return df

    src = src.copy()
    src[join_name] = src[src_col].map(clean_join_name)

    keep = [join_name]
    rename: dict[str, str] = {}
    for src_feature, out_feature in mappings.items():
        if src_feature in src.columns:
            keep.append(src_feature)
            rename[src_feature] = out_feature

    if len(keep) == 1:
        return df

    src = src[keep].drop_duplicates(join_name).rename(columns=rename)

    df = df.copy()
    df[join_name] = df[left_col].map(clean_join_name)
    df = df.merge(src, on=join_name, how="left", suffixes=("", "_new"))
    df = fill_from_new_columns(df)
    return df.drop(columns=[join_name])


def enrich_training_file(output_path: Path, market: str, season: int | None = None) -> Path:
    """Populate generated feature columns from cache CSVs before ML training."""
    if not output_path.exists():
        return output_path

    try:
        df = pd.read_csv(output_path)
    except Exception:
        return output_path

    if df.empty or "date" not in df.columns:
        return output_path

    if season is None:
        if "date" in df.columns:
            dates = pd.to_datetime(df["date"], errors="coerce")
            years = dates.dropna().dt.year
            season = int(years.mode().iloc[0]) if not years.empty else 2026
        else:
            season = 2026

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date.astype(str)

    cache = DATA_DIR / "cache"
    inc = cache / "incremental_stats"

    batter_totals = read_optional_csv(inc / f"batter_totals_{season}.csv")
    batter_recent = read_optional_csv(inc / f"batter_recent_{season}.csv")
    batter_recent_vs_hand = read_optional_csv(inc / f"batter_recent_vs_hand_{season}.csv")
    pitcher_totals = read_optional_csv(inc / f"pitcher_totals_{season}.csv")
    pitcher_recent = read_optional_csv(inc / f"pitcher_recent_{season}.csv")
    savant_batter = read_optional_csv(cache / "savant" / f"savant_batter_quality_{season}.csv")
    savant_pitcher = read_optional_csv(cache / "savant" / f"savant_pitcher_quality_{season}.csv")
    weather = read_optional_csv(cache / "weather" / f"weather_features_{season}.csv")
    movement = read_optional_csv(cache / "odds_movement" / f"prop_movement_{season}.csv")

    df = merge_by_clean_key(df, batter_totals, "player", "player", {
        "babip": "batter_babip",
        "kRate": "batter_k_rate",
        "bbRate": "batter_walk_rate",
        "avgHome": "batter_avg_home",
        "avgAway": "batter_avg_away",
        "hitsPerGame": "season_rate",
    }, "_join_player")

    df = merge_by_clean_key(df, batter_recent, "player", "player", {
        "games": "recent_games",
        "last5HitsPerGame": "rolling_avg_5",
        "last10HitsPerGame": "rolling_avg_10",
        "last15HitsPerGame": "rolling_avg_15",
        "last10TotalBasesPerGame": "rolling_total_bases_10",
        "last15HomeRunsPerGame": "rolling_hr_rate_15",
        "last10StrikeoutsPerGame": "rolling_k_rate_10",
        "last10HitsPerGame": "recent_rate",
        "daysRest": "batter_days_rest",
    }, "_join_player")

    if (
        not batter_recent_vs_hand.empty
        and {"date", "player"}.issubset(batter_recent_vs_hand.columns)
        and {"date", "player"}.issubset(df.columns)
    ):
        recent_hand = batter_recent_vs_hand.copy()
        recent_hand["date"] = pd.to_datetime(recent_hand["date"], errors="coerce").dt.date.astype(str)
        recent_hand["_join_player"] = recent_hand["player"].map(clean_join_name)

        df["_join_player"] = df["player"].map(clean_join_name)

        keep = ["date", "_join_player"]
        if "team" in recent_hand.columns and "team" in df.columns:
            keep.append("team")
            join_cols = ["date", "_join_player", "team"]
        else:
            join_cols = ["date", "_join_player"]

        for col in [
            "batter_recent_hits_vs_lhp",
            "batter_recent_hits_vs_rhp",
            "batter_recent_pa_vs_lhp",
            "batter_recent_pa_vs_rhp",
            "batter_recent_games_vs_lhp",
            "batter_recent_games_vs_rhp",
        ]:
            if col in recent_hand.columns and col not in keep:
                keep.append(col)

        if len(keep) > len(join_cols):
            recent_hand_small = recent_hand[keep].drop_duplicates(join_cols)
            df = df.merge(recent_hand_small, on=join_cols, how="left", suffixes=("", "_new"))
            df = fill_from_new_columns(df)

        if "_join_player" in df.columns:
            df = df.drop(columns=["_join_player"])

    df = merge_by_clean_key(df, savant_batter, "player", "player", {
        "barrelRate": "barrel_rate",
        "hardHitRate": "hard_hit_rate",
        "avgXWOBA": "xwoba",
        "avgXBA": "xba",
        "avgXSLG": "xslg",
        "ldRate": "batter_ld_rate",
        "gbRate": "batter_gb_rate",
        "sprintSpeed": "batter_sprint_speed",
        "babip": "batter_babip",
    }, "_join_player")

    df = merge_by_clean_key(df, pitcher_totals, "pitcher", "player", {
        "kRate": "pitcher_k_rate",
        "bbRate": "pitcher_walk_rate",
        "hrPer9": "pitcher_hr_rate",
        "babip": "pitcher_babip",
    }, "_join_pitcher")

    df = merge_by_clean_key(df, pitcher_recent, "pitcher", "player", {
        "daysRest": "pitcher_days_rest",
    }, "_join_pitcher")

    df = merge_by_clean_key(df, savant_pitcher, "pitcher", "player", {
        "veloDelta": "pitcher_velo_delta",
    }, "_join_pitcher")

    if not movement.empty and {"date", "market", "player"}.issubset(movement.columns):
        movement = movement.copy()
        movement["date"] = pd.to_datetime(movement["date"], errors="coerce").dt.date.astype(str)
        movement["_join_player"] = movement["player"].map(clean_join_name)
        df["_join_player"] = df["player"].map(clean_join_name)

        keep = ["date", "market", "_join_player"]
        rename: dict[str, str] = {}
        for src_col, out_col in {"lineMove": "line_move", "oddsMove": "odds_move"}.items():
            if src_col in movement.columns:
                keep.append(src_col)
                rename[src_col] = out_col

        if len(keep) > 3:
            movement_small = (
                movement[keep]
                .drop_duplicates(["date", "market", "_join_player"])
                .rename(columns=rename)
            )
            df = df.merge(movement_small, on=["date", "market", "_join_player"], how="left", suffixes=("", "_new"))
            df = fill_from_new_columns(df)

        if "_join_player" in df.columns:
            df = df.drop(columns=["_join_player"])

    if not weather.empty and {"date", "home", "away"}.issubset(weather.columns):
        weather = weather.copy()
        weather["date"] = pd.to_datetime(weather["date"], errors="coerce").dt.date.astype(str)

        weather_rows: list[dict[str, Any]] = []
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
        if not weather_join.empty and {"date", "team", "opponent"}.issubset(df.columns):
            df = df.merge(weather_join, on=["date", "team", "opponent"], how="left", suffixes=("", "_new"))
            df = fill_from_new_columns(df)


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

    # True recent-vs-hand features are joined from batter_recent_vs_hand_YEAR.csv above.
    # Only keep the old season-split AVG proxy as an emergency fallback when the
    # true file has not been built yet.
    if "batter_recent_hits_vs_lhp" not in df.columns and "batter_avg_vs_lhp" in df.columns:
        df["batter_recent_hits_vs_lhp"] = df["batter_avg_vs_lhp"]
    if "batter_recent_hits_vs_rhp" not in df.columns and "batter_avg_vs_rhp" in df.columns:
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

    # Join true rolling 7-day bullpen ERA by opponent/date when available.
    bullpen_recent = read_optional_csv(inc / f"bullpen_recent_{season}.csv")

    if not bullpen_recent.empty and {"date", "team", "bullpen_era_7d"}.issubset(bullpen_recent.columns) and {"date", "opponent"}.issubset(df.columns):
        bullpen_recent = bullpen_recent.copy()
        bullpen_recent["date"] = pd.to_datetime(bullpen_recent["date"], errors="coerce").dt.date.astype(str)

        bullpen_keep = ["date", "team", "bullpen_era_7d"]
        if "bullpen_ip_7d" in bullpen_recent.columns:
            bullpen_keep.append("bullpen_ip_7d")
        if "bullpen_appearances_7d" in bullpen_recent.columns:
            bullpen_keep.append("bullpen_appearances_7d")

        bullpen_small = (
            bullpen_recent[bullpen_keep]
            .drop_duplicates(["date", "team"])
            .rename(columns={
                "team": "opponent",
                "bullpen_era_7d": "opponent_bullpen_era_7d",
                "bullpen_ip_7d": "opponent_bullpen_ip_7d",
                "bullpen_appearances_7d": "opponent_bullpen_appearances_7d",
            })
        )
        df = df.merge(bullpen_small, on=["date", "opponent"], how="left", suffixes=("", "_new"))
        df = fill_from_new_columns(df)

    # Fallback only when true bullpen history is unavailable for a row.
    if "opponent_bullpen_era_7d" not in df.columns and "opponent_rate" in df.columns:
        df["opponent_bullpen_era_7d"] = df["opponent_rate"]
    elif "opponent_bullpen_era_7d" in df.columns and "opponent_rate" in df.columns:
        df["opponent_bullpen_era_7d"] = df["opponent_bullpen_era_7d"].fillna(df["opponent_rate"])


    # Join/derive venue-level park factor features.
    # Prefer a true park_factors_YEAR.csv if it exists. Otherwise derive a
    # venue-level fallback from weather_features_YEAR.csv adjustments.
    park_factors = read_optional_csv(ROOT / "data" / "cache" / "parks" / f"park_factors_{season}.csv")

    if park_factors.empty:
        park_factors = read_optional_csv(ROOT / "data" / "cache" / f"park_factors_{season}.csv")

    if park_factors.empty:
        weather_park = read_optional_csv(ROOT / "data" / "cache" / "weather" / f"weather_features_{season}.csv")

        if not weather_park.empty and "venue" in weather_park.columns:
            weather_park = weather_park.copy()

            for col in [
                "hitsWeatherAdjustment",
                "hrWeatherAdjustment",
                "pitcherStrikeoutsWeatherAdjustment",
            ]:
                if col not in weather_park.columns:
                    weather_park[col] = 0.0
                weather_park[col] = pd.to_numeric(weather_park[col], errors="coerce").fillna(0.0)

            park_factors = (
                weather_park
                .groupby("venue", as_index=False)
                .agg(
                    hit_adj=("hitsWeatherAdjustment", "mean"),
                    hr_adj=("hrWeatherAdjustment", "mean"),
                    k_adj=("pitcherStrikeoutsWeatherAdjustment", "mean"),
                )
            )

            park_factors["hit_factor"] = (1.0 + park_factors["hit_adj"] / 100.0).round(4)
            park_factors["hr_factor"] = (1.0 + park_factors["hr_adj"] / 100.0).round(4)
            park_factors["k_factor"] = (1.0 + park_factors["k_adj"] / 100.0).round(4)
            park_factors["park_factor"] = (
                park_factors[["hit_factor", "hr_factor", "k_factor"]]
                .mean(axis=1)
                .round(4)
            )

    if not park_factors.empty and "venue" in park_factors.columns and "venue" in df.columns:
        park_factors = park_factors.copy()

        keep_cols = ["venue"]
        for col in ["park_factor", "hit_factor", "hr_factor", "k_factor"]:
            if col in park_factors.columns:
                keep_cols.append(col)

        if len(keep_cols) > 1:
            park_small = park_factors[keep_cols].drop_duplicates(["venue"])
            df = df.merge(park_small, on="venue", how="left", suffixes=("", "_new"))
            df = fill_from_new_columns(df)

    # Final neutral fallback so park features are explicit instead of all-null.
    for col in ["park_factor", "hit_factor", "hr_factor", "k_factor"]:
        if col not in df.columns:
            df[col] = 1.0
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(1.0)

    def matchup(row: pd.Series) -> Any:
        t = str(row.get("throws") or "").strip().upper()[:1]
        b = str(row.get("bats") or "").strip().upper()[:1]
        if b == "S":
            return "switch_hitter"
        if t in {"L", "R"} and b in {"L", "R"}:
            return "same_side" if t == b else "opposite_side"
        return row.get("platoon_matchup")

    if "platoon_matchup" in df.columns:
        df["platoon_matchup"] = df.apply(matchup, axis=1)

    df.to_csv(output_path, index=False)
    return output_path

def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare clean ML training data for a player prop market.")
    parser.add_argument("--market", required=True, choices=sorted(SUPPORTED_MARKETS))
    parser.add_argument("--input", default="", help="Input CSV. Defaults to enriched historical props if present.")
    parser.add_argument("--out", default="", help="Output CSV. Defaults to data/training/<market>_training.csv")
    parser.add_argument("--train", action="store_true", help="Train ml_prop_model.py after preparing if both classes exist.")
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else first_existing_input()
    output_path = Path(args.out) if args.out else DATA_DIR / "training" / f"{args.market}_training.csv"

    summary = prepare_market(input_path, output_path, args.market)
    enrich_training_file(output_path, args.market)

    for key, value in summary.items():
        print(f"{key}: {value}")

    if not summary["canTrain"]:
        print("")
        print("Cannot train yet because this market has only one outcome class.")
        print("You need at least one row with over=0 and at least one row with over=1.")
        return

    if args.train:
        import subprocess
        import sys

        print("")
        print("Training model...")
        subprocess.run(
            [sys.executable, str(ROOT / "ml_prop_model.py"), "train", str(output_path), "--market", args.market],
            check=True,
        )


if __name__ == "__main__":
    main()
