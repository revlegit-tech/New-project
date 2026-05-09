from pathlib import Path

path = Path("prepare_market_training.py")
text = path.read_text(encoding="utf-8")

if "def enrich_training_file(" in text:
    print("prepare_market_training.py already has enrichment logic. No patch needed.")
    raise SystemExit(0)

# Add imports.
text = text.replace(
    "import argparse\nimport csv\n",
    "import argparse\nimport csv\nimport re\nimport unicodedata\n\nimport pandas as pd\n",
)

enrichment_code = r'''

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
'''

marker = "\ndef main() -> None:"
if marker not in text:
    raise SystemExit("Could not find def main() marker in prepare_market_training.py")

text = text.replace(marker, enrichment_code + marker)

old = '    summary = prepare_market(input_path, output_path, args.market)\n'
new = '    summary = prepare_market(input_path, output_path, args.market)\n    enrich_training_file(output_path, args.market)\n'
if old not in text:
    raise SystemExit("Could not find summary = prepare_market(...) line")

text = text.replace(old, new)

path.write_text(text, encoding="utf-8")
print("Patched prepare_market_training.py with automatic feature enrichment.")
