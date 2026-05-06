import pandas as pd
from pathlib import Path

paths = [
    Path("data/cache/umpires/game_umpires_2026.csv"),
    Path("data/cache/umpires/umpire_stats_2026.csv"),
    Path("data/cache/umpires/umpire_status_2026.json"),
]

for path in paths:
    print("\n" + "=" * 80)
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

    for col in [
        "umpire",
        "homePlateUmpire",
        "games",
        "calledStrikes",
        "balls",
        "strikeRate",
        "kRate",
        "zoneSizeZScore",
        "favorBatterScore",
        "ump_k_rate",
        "ump_zone_size_zscore",
        "ump_favor_batter_score",
    ]:
        if col in df.columns:
            print(f"{col:28s} {df[col].notna().mean() * 100:6.2f}% non-null | unique={df[col].nunique(dropna=True)}")
