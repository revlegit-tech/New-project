from pathlib import Path

# -----------------------------
# playerboard.py
# -----------------------------
path = Path("playerboard.py")
text = path.read_text(encoding="utf-8")

if '"team_total_runs",' not in text:
    text = text.replace(
'''    "batter_stolen_bases",
    "pitcher_strikeouts",
''',
'''    "batter_stolen_bases",
    "team_total_runs",
    "team_first_to_score",
    "pitcher_strikeouts",
'''
    )

text = text.replace(
'''    if text == "batter_stolen_bases":
        return "Batter Stolen Bases"
''',
'''    if text == "batter_stolen_bases":
        return "Batter Stolen Bases"
    if text == "team_total_runs":
        return "Team Total Runs"
    if text == "team_first_to_score":
        return "Team First To Score"
'''
)

text = text.replace(
'''        "batter stolen bases": "batter_stolen_bases",
''',
'''        "batter stolen bases": "batter_stolen_bases",
        "team total": "team_total_runs",
        "team totals": "team_total_runs",
        "team total runs": "team_total_runs",
        "team runs": "team_total_runs",
        "total runs team": "team_total_runs",
        "first to score": "team_first_to_score",
        "first team to score": "team_first_to_score",
        "team first to score": "team_first_to_score",
        "first score": "team_first_to_score",
'''
)

text = text.replace(
'''    if original in {"batter_rbis", "batter_stolen_bases"}:
        return original
''',
'''    if original in {"batter_rbis", "batter_stolen_bases"}:
        return original

    if original in {"team_total_runs", "team_first_to_score"}:
        return original
'''
)

text = text.replace(
'''        if not (market.startswith("batter_") or market.startswith("pitcher_")):
''',
'''        if not (market.startswith("batter_") or market.startswith("pitcher_") or market.startswith("team_")):
'''
)

text = text.replace(
'''    role = "pitcher" if clean(prop.get("market")).startswith("pitcher") else "batter"
''',
'''    role = "pitcher" if clean(prop.get("market")).startswith("pitcher") else "team" if clean(prop.get("market")).startswith("team") else "batter"
'''
)

path.write_text(text, encoding="utf-8")


# -----------------------------
# prepare_market_training.py
# -----------------------------
path = Path("prepare_market_training.py")
text = path.read_text(encoding="utf-8")

if '"team_total_runs",' not in text:
    text = text.replace(
'''    "batter_stolen_bases",
    "pitcher_strikeouts",
''',
'''    "batter_stolen_bases",
    "team_total_runs",
    "team_first_to_score",
    "pitcher_strikeouts",
'''
    )

path.write_text(text, encoding="utf-8")


# -----------------------------
# train_all_supported_markets.py
# -----------------------------
path = Path("train_all_supported_markets.py")
text = path.read_text(encoding="utf-8")

if '"team_total_runs",' not in text:
    text = text.replace(
'''    "batter_stolen_bases",
    "pitcher_strikeouts",
''',
'''    "batter_stolen_bases",
    "team_total_runs",
    "team_first_to_score",
    "pitcher_strikeouts",
'''
    )

path.write_text(text, encoding="utf-8")


# -----------------------------
# playerboard_backtest.py
# -----------------------------
path = Path("playerboard_backtest.py")
text = path.read_text(encoding="utf-8")

if 'market == "team_total_runs"' not in text:
    text = text.replace(
'''    if market.startswith("pitcher"):
''',
'''    if market.startswith("team"):
        # Team prop support is future-ready. It depends on team game logs
        # being populated with team-level runs and first-score fields.
        team = clean(row.get("team"))
        opponent = clean(row.get("opponent"))
        game_date = clean(row.get("date"))[:10]

        candidates = [
            r for r in batter_rows
            if clean(r.get("date"))[:10] == game_date
        ]

        # Prefer team rows if the caller starts passing a real team log here later.
        # For now, use any row shape that exposes team/runs fields.
        team_log = None
        for log in candidates:
            if clean(log.get("team")) == team:
                team_log = log
                break

        if market == "team_total_runs":
            if team_log:
                return to_float(get_any(team_log, ["runs", "teamRuns", "team_runs"])), "Team total runs from team/game log."
            return None, "Team total runs requires team game log rows."

        if market == "team_first_to_score":
            if team_log:
                value = get_any(team_log, ["firstToScore", "first_to_score", "teamFirstToScore"])
                if clean(value):
                    return to_float(value), "Team first-to-score flag from team/game log."
            return None, "Team first-to-score requires team first-score data."

        return None, f"Unsupported team market: {market}"

    if market.startswith("pitcher"):
'''
    )

path.write_text(text, encoding="utf-8")

print("Patched future-ready team prop market support.")
