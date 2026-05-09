import pandas as pd
from pathlib import Path

paths = [
    Path("data/cache/incremental_stats/batter_platoon_splits_2026.csv"),
    Path("data/cache/incremental_stats/pitcher_platoon_splits_2026.csv"),
    Path("data/cache/incremental_stats/platoon_splits_status_2026.json"),
]

for path in paths:
    print("\n" + "=" * 90)
    print(path)

    if not path.exists():
        print("MISSING")
        continue

    if path.suffix == ".json":
        print(path.read_text(encoding="utf-8")[:4000])
        continue

    df = pd.read_csv(path)
    print("rows:", len(df))
    print("columns:", list(df.columns))

    print("\nFirst 10 rows:")
    print(df.head(10).to_string(index=False))

    print("\nCoverage:")
    for col in df.columns:
        print(f"{col:35s} {df[col].notna().mean() * 100:6.2f}% non-null | unique={df[col].nunique(dropna=True)}")
