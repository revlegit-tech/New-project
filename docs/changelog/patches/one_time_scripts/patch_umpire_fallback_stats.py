from pathlib import Path

path = Path("umpire_collector.py")
text = path.read_text(encoding="utf-8")

insert_after = '''def collect_game_umpires(season: int = 2026, force: bool = False) -> list[dict[str, Any]]:
    games_path = INCREMENTAL_DIR / f"games_{season}.csv"
    existing_path = UMPIRE_DIR / f"game_umpires_{season}.csv"
    existing = {clean(row.get("gamePk")): row for row in read_csv_rows(existing_path)}
    rows: list[dict[str, Any]] = []

    for game in read_csv_rows(games_path):
        game_pk = clean(game.get("gamePk"))
        if not game_pk:
            continue
        if game_pk in existing and not force:
            rows.append(existing[game_pk])
            continue
        ump = fetch_game_umpire(game_pk)
        rows.append({
            "gamePk": game_pk,
            "date": clean(game.get("date")),
            "season": season,
            "homeTeam": clean(game.get("home")),
            "awayTeam": clean(game.get("away")),
            "homePlateUmpireId": ump.get("homePlateUmpireId", ""),
            "homePlateUmpireName": ump.get("homePlateUmpireName", ""),
            "updatedAt": now_iso(),
        })
    return rows
'''

fallback_func = '''def build_fallback_umpire_stats(game_rows: list[dict[str, Any]], season: int = 2026) -> list[dict[str, Any]]:
    """Create neutral umpire features from game assignments when tendency data is unavailable.

    These are intentionally conservative. They let downstream joins populate stable
    neutral umpire values instead of all-null features, while preserving gamesUmped
    as useful availability/context.
    """
    grouped: dict[str, dict[str, Any]] = {}

    for game in game_rows:
        umpire_id = clean(game.get("homePlateUmpireId"))
        umpire_name = clean(game.get("homePlateUmpireName"))

        # Some future/scheduled games may not have announced umpires yet.
        if not umpire_id and not umpire_name:
            continue

        key = umpire_id or umpire_name.lower()
        if key not in grouped:
            grouped[key] = {
                "umpireId": umpire_id,
                "umpireName": umpire_name,
                "season": season,
                "gamesUmped": 0,
                # Neutral fallback values until real umpire tendency stats exist.
                "kRateFavorBatter": 0.0,
                "bbRateFavorBatter": 0.0,
                "zoneSizeZscore": 0.0,
                "favorHomePct": 0.0,
                "runsScoredPerGame": 0.0,
                "hitsPerGame": 0.0,
                "updatedAt": now_iso(),
            }

        grouped[key]["gamesUmped"] = int(grouped[key]["gamesUmped"]) + 1

        # Preserve better values if one row has an ID/name and another does not.
        if umpire_id and not grouped[key].get("umpireId"):
            grouped[key]["umpireId"] = umpire_id
        if umpire_name and not grouped[key].get("umpireName"):
            grouped[key]["umpireName"] = umpire_name

    return sorted(
        grouped.values(),
        key=lambda row: (-int(row.get("gamesUmped") or 0), clean(row.get("umpireName"))),
    )


'''

if "def build_fallback_umpire_stats(" not in text:
    text = text.replace(insert_after, insert_after + "\n\n" + fallback_func)
else:
    print("Fallback function already exists; skipping insertion.")

old_sync = '''def sync_umpires(season: int = 2026, force: bool = False) -> dict[str, Any]:
    UMPIRE_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    try:
        stat_rows = fetch_umpire_stats(season)
    except Exception as error:
        stat_rows = read_csv_rows(UMPIRE_DIR / f"umpire_stats_{season}.csv")
        errors.append(f"umpire stats failed: {error}")
    try:
        game_rows = collect_game_umpires(season, force=force)
    except Exception as error:
        game_rows = read_csv_rows(UMPIRE_DIR / f"game_umpires_{season}.csv")
        errors.append(f"game umpire lookup failed: {error}")

    write_csv(UMPIRE_DIR / f"umpire_stats_{season}.csv", UMPIRE_STAT_FIELDS, stat_rows)
    write_csv(UMPIRE_DIR / f"game_umpires_{season}.csv", GAME_UMPIRE_FIELDS, game_rows)
    summary = {
        "season": season,
        "umpireStatsRows": len(stat_rows),
        "gameUmpireRows": len(game_rows),
        "errors": errors[:20],
        "errorCount": len(errors),
        "updatedAt": now_iso(),
    }
    write_json(UMPIRE_DIR / f"umpire_status_{season}.json", summary)
    return summary
'''

new_sync = '''def sync_umpires(season: int = 2026, force: bool = False) -> dict[str, Any]:
    UMPIRE_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    used_fallback_stats = False

    try:
        game_rows = collect_game_umpires(season, force=force)
    except Exception as error:
        game_rows = read_csv_rows(UMPIRE_DIR / f"game_umpires_{season}.csv")
        errors.append(f"game umpire lookup failed: {error}")

    try:
        stat_rows = fetch_umpire_stats(season)
    except Exception as error:
        stat_rows = read_csv_rows(UMPIRE_DIR / f"umpire_stats_{season}.csv")
        errors.append(f"umpire stats failed: {error}")

    if not stat_rows:
        stat_rows = build_fallback_umpire_stats(game_rows, season)
        used_fallback_stats = True

    write_csv(UMPIRE_DIR / f"umpire_stats_{season}.csv", UMPIRE_STAT_FIELDS, stat_rows)
    write_csv(UMPIRE_DIR / f"game_umpires_{season}.csv", GAME_UMPIRE_FIELDS, game_rows)

    summary = {
        "season": season,
        "umpireStatsRows": len(stat_rows),
        "gameUmpireRows": len(game_rows),
        "usedFallbackStats": used_fallback_stats,
        "errors": errors[:20],
        "errorCount": len(errors),
        "updatedAt": now_iso(),
    }
    write_json(UMPIRE_DIR / f"umpire_status_{season}.json", summary)
    return summary
'''

if old_sync not in text:
    raise SystemExit("Could not find sync_umpires block to patch.")

text = text.replace(old_sync, new_sync)
path.write_text(text, encoding="utf-8")

print("Patched umpire_collector.py with fallback neutral umpire stats.")
