import json
import pandas as pd
from pathlib import Path
from joblib import load

model_path = Path("data/models/prop_model_batter_hits.joblib")
train_path = Path("data/training/batter_hits_training_enriched.csv")

df = pd.read_csv(train_path)
model = load(model_path)

print("Rows:", len(df))
print("Model:", type(model))

print("\nLabel counts:")
print(df["over"].value_counts(dropna=False))

print("\nFeature coverage:")
important = [
    "line",
    "book_implied_probability",
    "line_move",
    "odds_move",
    "batter_babip",
    "batter_days_rest",
    "barrel_rate",
    "hard_hit_rate",
    "xwoba",
    "xba",
    "xslg",
    "batter_ld_rate",
    "batter_gb_rate",
    "batter_sprint_speed",
    "pitcher_babip",
    "pitcher_days_rest",
    "pitcher_velo_delta",
    "pitcher_k_rate",
    "pitcher_walk_rate",
    "pitcher_hr_rate",
    "wind_out_flag",
    "turf_flag",
]
for col in important:
    if col in df.columns:
        print(f"{col:28s} {df[col].notna().mean()*100:6.2f}% non-null")
    else:
        print(f"{col:28s} MISSING")
