import pandas as pd
from pathlib import Path

src = Path("data/ml/playerboard_training_2026.csv")
out_dir = Path("data/training")
out_dir.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(src)

# Normalize column names expected by older training scripts
rename_map = {
    "americanOdds": "american_odds",
    "actualStat": "actual",
    "overHit": "over",
    "sportsbookImpliedPercent": "book_implied_percent",
    "finalProbabilityPercent": "model_probability_percent",
}

for old, new in rename_map.items():
    if old in df.columns and new not in df.columns:
        df[new] = df[old]

# Convert percentages to probabilities where useful
if "book_implied_probability" not in df.columns and "sportsbookImpliedPercent" in df.columns:
    df["book_implied_probability"] = pd.to_numeric(df["sportsbookImpliedPercent"], errors="coerce") / 100.0

# Remove pushes and rows without labels
if "push" in df.columns:
    df = df[pd.to_numeric(df["push"], errors="coerce").fillna(0) == 0]

df = df[df["over"].notna()]
df = df[df["actual"].notna()]

out = out_dir / "historical_props.csv"
df.to_csv(out, index=False)

print(f"Wrote {out}")
print("rows:", len(df))
print("markets:")
print(df["market"].value_counts(dropna=False))
print("\nover counts:")
print(df["over"].value_counts(dropna=False))
