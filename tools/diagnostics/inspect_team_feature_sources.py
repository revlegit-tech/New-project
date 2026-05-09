import pandas as pd
from pathlib import Path

paths = [
    Path("data/cache/incremental_stats/team_recent_2026.csv"),
    Path("data/cache/incremental_stats/team_totals_2026.csv"),
    Path("data/cache/incremental_stats/pitcher_recent_2026.csv"),
    Path("data/cache/incremental_stats/pitcher_totals_2026.csv"),
    Path("data/cloud/season_logs/team_game_logs_2026.csv"),
    Path("data/cloud/season_logs/pitcher_game_logs_2026.csv"),
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

    print("\nCoverage:")
    for col in df.columns:
        print(f"{col:35s} {df[col].notna().mean() * 100:6.2f}% non-null | unique={df[col].nunique(dropna=True)}")
