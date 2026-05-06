import pandas as pd
from pathlib import Path

raw = Path("data/cache/weather/game_weather_2026.csv")
features = Path("data/cache/weather/weather_features_2026.csv")

for path in [raw, features]:
    print("\n" + "="*80)
    print(path)

    if not path.exists():
        print("MISSING")
        continue

    df = pd.read_csv(path)
    print("rows:", len(df))
    print("columns:", list(df.columns))

    for col in [
        "temperatureF",
        "feelsLikeF",
        "windMph",
        "windDirection",
        "windOutScore",
        "windOutFlag",
        "turfFlag",
        "coldGameFlag",
    ]:
        if col in df.columns:
            non_null = df[col].notna().mean() * 100
            unique = df[col].nunique(dropna=True)
            print(f"{col:20s} {non_null:6.2f}% non-null | unique={unique}")
