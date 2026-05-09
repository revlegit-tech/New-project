import pandas as pd
from pathlib import Path

paths = [
    Path("data/playerboard/playerboard_2026.csv"),
    Path("data/backtests/playerboard_backtest_2026.csv"),
    Path("data/cache/odds_movement/prop_snapshots_2026.csv"),
]

for path in paths:
    print("\n" + "="*100)
    print(path)

    if not path.exists():
        print("MISSING")
        continue

    df = pd.read_csv(path)
    print("rows:", len(df))
    print("columns:", list(df.columns))

    market_cols = [c for c in ["market", "baseMarket", "originalMarket", "rawLabel", "marketDisplay"] if c in df.columns]

    for col in market_cols:
        print(f"\nTop {col}:")
        print(df[col].astype(str).value_counts(dropna=False).head(50).to_string())

    if market_cols:
        mask = False
        for col in market_cols:
            s = df[col].astype(str).str.lower()
            mask = mask | s.str.contains("rbi|runs batted|stolen|steal|sb", regex=True, na=False)

        hits = df[mask].copy()
        print("\nPossible RBI/SB rows:", len(hits))
        if len(hits):
            show_cols = [c for c in ["date","market","baseMarket","originalMarket","marketDisplay","rawLabel","player","team","opponent","pitcher","line","americanOdds"] if c in hits.columns]
            print(hits[show_cols].head(50).to_string(index=False))
