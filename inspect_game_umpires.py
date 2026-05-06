import pandas as pd

df = pd.read_csv("data/cache/umpires/game_umpires_2026.csv")

for col in ["homePlateUmpireId", "homePlateUmpireName"]:
    print(f"{col:24s} {df[col].notna().mean()*100:6.2f}% non-null | unique={df[col].nunique(dropna=True)}")

print("\nSample rows:")
print(df.head(20).to_string(index=False))
