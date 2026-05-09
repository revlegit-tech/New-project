from pathlib import Path

path = Path("prepare_market_training.py")
text = path.read_text(encoding="utf-8")

if "park_factors = read_optional_csv" in text:
    print("prepare_market_training.py already has park-factor join logic. No patch needed.")
    raise SystemExit(0)

marker = '''    def matchup(row: pd.Series) -> Any:
'''

park_join = r'''
    # Join/derive venue-level park factor features.
    # Prefer a true park_factors_YEAR.csv if it exists. Otherwise derive a
    # venue-level fallback from weather_features_YEAR.csv adjustments.
    park_factors = read_optional_csv(ROOT / "data" / "cache" / "parks" / f"park_factors_{season}.csv")

    if park_factors.empty:
        park_factors = read_optional_csv(ROOT / "data" / "cache" / f"park_factors_{season}.csv")

    if park_factors.empty:
        weather_park = read_optional_csv(ROOT / "data" / "cache" / "weather" / f"weather_features_{season}.csv")

        if not weather_park.empty and "venue" in weather_park.columns:
            weather_park = weather_park.copy()

            for col in [
                "hitsWeatherAdjustment",
                "hrWeatherAdjustment",
                "pitcherStrikeoutsWeatherAdjustment",
            ]:
                if col not in weather_park.columns:
                    weather_park[col] = 0.0
                weather_park[col] = pd.to_numeric(weather_park[col], errors="coerce").fillna(0.0)

            park_factors = (
                weather_park
                .groupby("venue", as_index=False)
                .agg(
                    hit_adj=("hitsWeatherAdjustment", "mean"),
                    hr_adj=("hrWeatherAdjustment", "mean"),
                    k_adj=("pitcherStrikeoutsWeatherAdjustment", "mean"),
                )
            )

            park_factors["hit_factor"] = (1.0 + park_factors["hit_adj"] / 100.0).round(4)
            park_factors["hr_factor"] = (1.0 + park_factors["hr_adj"] / 100.0).round(4)
            park_factors["k_factor"] = (1.0 + park_factors["k_adj"] / 100.0).round(4)
            park_factors["park_factor"] = (
                park_factors[["hit_factor", "hr_factor", "k_factor"]]
                .mean(axis=1)
                .round(4)
            )

    if not park_factors.empty and "venue" in park_factors.columns and "venue" in df.columns:
        park_factors = park_factors.copy()

        keep_cols = ["venue"]
        for col in ["park_factor", "hit_factor", "hr_factor", "k_factor"]:
            if col in park_factors.columns:
                keep_cols.append(col)

        if len(keep_cols) > 1:
            park_small = park_factors[keep_cols].drop_duplicates(["venue"])
            df = df.merge(park_small, on="venue", how="left", suffixes=("", "_new"))
            df = fill_from_new_columns(df)

    # Final neutral fallback so park features are explicit instead of all-null.
    for col in ["park_factor", "hit_factor", "hr_factor", "k_factor"]:
        if col not in df.columns:
            df[col] = 1.0
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(1.0)

'''

if marker not in text:
    raise SystemExit("Could not find matchup marker. Send me the enrich_training_file section.")

text = text.replace(marker, park_join + marker)
path.write_text(text, encoding="utf-8")

print("Patched prepare_market_training.py to derive and join park-factor features.")
