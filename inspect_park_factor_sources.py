import pandas as pd
from pathlib import Path

paths = [
    Path("data/cache/parks/park_factors_2026.csv"),
    Path("data/cache/park_factors_2026.csv"),
    Path("data/cache/weather/weather_features_2026.csv"),
    Path("data/cache/incremental_stats/games_2026.csv"),
    Path("data/playerboard/playerboard_2026.csv"),
    Path("data/training/batter_hits_training.csv"),
]

for path in paths:
    print("\n" + "=" * 90)
    print(path)

    if not path.exists():
        print("MISSING")
        continue

    df = pd.read_csv(path)
    print("rows:", len(df))
    print("columns:", list(df.columns))

    print("\nFirst 5 rows:")
    print(df.head(5).to_string(index=False))

    print("\nVenue/park-related coverage:")
    for col in [
        "venue",
        "park",
        "ballpark",
        "stadium",
        "home",
        "away",
        "team",
        "opponent",
        "park_factor",
        "hit_factor",
        "hr_factor",
        "k_factor",
        "venueName",
        "gamePk",
        "date",
    ]:
        if col in df.columns:
            print(f"{col:25s} {df[col].notna().mean() * 100:6.2f}% non-null | unique={df[col].nunique(dropna=True)}")
