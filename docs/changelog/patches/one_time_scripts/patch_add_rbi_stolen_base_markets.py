from pathlib import Path

# -----------------------------
# playerboard.py
# -----------------------------
path = Path("playerboard.py")
text = path.read_text(encoding="utf-8")

if '"batter_rbis",' not in text:
    text = text.replace(
'''    "batter_home_runs",
    "batter_home_runs_alt",
''',
'''    "batter_home_runs",
    "batter_home_runs_alt",
    "batter_rbis",
    "batter_stolen_bases",
'''
    )

text = text.replace(
'''    if text == "batter_home_runs_alt":
        return f"Batter Home Runs Alt - {label}" if label else "Batter Home Runs Alt"
''',
'''    if text == "batter_home_runs_alt":
        return f"Batter Home Runs Alt - {label}" if label else "Batter Home Runs Alt"
    if text == "batter_rbis":
        return "Batter RBIs"
    if text == "batter_stolen_bases":
        return "Batter Stolen Bases"
'''
)

text = text.replace(
'''        "batter home runs": "batter_home_runs",
''',
'''        "batter home runs": "batter_home_runs",
        "rbi": "batter_rbis",
        "rbis": "batter_rbis",
        "runs batted in": "batter_rbis",
        "batter rbi": "batter_rbis",
        "batter rbis": "batter_rbis",
        "stolen base": "batter_stolen_bases",
        "stolen bases": "batter_stolen_bases",
        "steals": "batter_stolen_bases",
        "batter stolen bases": "batter_stolen_bases",
'''
)

text = text.replace(
'''    if original == "batter_home_runs":
        if is_alt:
            return "batter_home_runs_alt"
''',
'''    if original == "batter_home_runs":
        if is_alt:
            return "batter_home_runs_alt"

    if original in {"batter_rbis", "batter_stolen_bases"}:
        return original
'''
)

path.write_text(text, encoding="utf-8")


# -----------------------------
# prepare_market_training.py
# -----------------------------
path = Path("prepare_market_training.py")
text = path.read_text(encoding="utf-8")

if '"batter_rbis",' not in text:
    text = text.replace(
'''    "batter_home_runs",
    "pitcher_strikeouts",
''',
'''    "batter_home_runs",
    "batter_rbis",
    "batter_stolen_bases",
    "pitcher_strikeouts",
'''
    )

path.write_text(text, encoding="utf-8")


# -----------------------------
# train_all_supported_markets.py
# -----------------------------
path = Path("train_all_supported_markets.py")
text = path.read_text(encoding="utf-8")

if '"batter_rbis",' not in text:
    text = text.replace(
'''    "batter_total_bases",
    "pitcher_strikeouts",
''',
'''    "batter_total_bases",
    "batter_rbis",
    "batter_stolen_bases",
    "pitcher_strikeouts",
'''
    )

path.write_text(text, encoding="utf-8")


# -----------------------------
# playerboard_backtest.py
# -----------------------------
path = Path("playerboard_backtest.py")
text = path.read_text(encoding="utf-8")

if 'market == "batter_rbis"' not in text:
    text = text.replace(
'''        if market == "batter_home_runs":
            return to_float(get_any(log, ["homeRuns", "home_runs", "hr"])), "Batter home runs from game log."

        return None, f"Unsupported batter market: {market}"
''',
'''        if market == "batter_home_runs":
            return to_float(get_any(log, ["homeRuns", "home_runs", "hr"])), "Batter home runs from game log."
        if market == "batter_rbis":
            return to_float(get_any(log, ["rbi", "rbiS", "runsBattedIn", "runs_batted_in"])), "Batter RBIs from game log."
        if market == "batter_stolen_bases":
            return to_float(get_any(log, ["stolenBases", "stolen_bases", "sb"])), "Batter stolen bases from game log."

        return None, f"Unsupported batter market: {market}"
'''
    )

path.write_text(text, encoding="utf-8")

print("Patched RBI and stolen-base market support.")
