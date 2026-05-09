import pandas as pd

df = pd.read_csv("data/training/batter_hits_training.csv")

for col in [
    "bats",
    "throws",
    "platoon_matchup",
    "batter_avg_vs_hand",
    "batter_k_rate_vs_hand",
    "batter_recent_hits_vs_lhp",
    "batter_recent_hits_vs_rhp",
    "pitcher_avg_allowed_vs_hand",
]:
    if col in df.columns:
        print(f"{col:32s} {df[col].notna().mean() * 100:6.2f}% non-null | unique={df[col].nunique(dropna=True)}")
    else:
        print(f"{col:32s} MISSING")
