import pandas as pd

df = pd.read_csv("data/training/batter_hits_training.csv")

for col in [
    "umpire",
    "ump_k_rate",
    "ump_zone_size_zscore",
    "ump_favor_batter_score",
]:
    if col in df.columns:
        print(f"{col:28s} {df[col].notna().mean() * 100:6.2f}% non-null | unique={df[col].nunique(dropna=True)}")
    else:
        print(f"{col:28s} MISSING")
