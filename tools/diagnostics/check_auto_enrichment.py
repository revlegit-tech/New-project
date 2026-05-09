import pandas as pd

df = pd.read_csv("data/training/batter_hits_training.csv")

features = [
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
    "line_move",
    "odds_move",
    "wind_out_flag",
    "turf_flag",
]

print("Rows:", len(df))
for col in features:
    if col not in df.columns:
        print(f"MISSING {col}")
    else:
        print(f"{col:28s} {df[col].notna().mean() * 100:6.2f}% non-null")
