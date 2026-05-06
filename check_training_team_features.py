import pandas as pd

df = pd.read_csv("data/training/batter_hits_training.csv")

for col in [
    "team_k_rate",
    "team_walk_rate",
    "opponent_rate",
    "opponent_bullpen_era_7d",
    "hit_factor",
    "hr_factor",
    "k_factor",
]:
    if col in df.columns:
        print(f"{col:30s} {df[col].notna().mean() * 100:6.2f}% non-null | unique={df[col].nunique(dropna=True)}")
    else:
        print(f"{col:30s} MISSING")
