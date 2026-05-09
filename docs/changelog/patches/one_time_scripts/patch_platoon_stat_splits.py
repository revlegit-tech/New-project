from pathlib import Path

path = Path("platoon_splits_collector.py")
text = path.read_text(encoding="utf-8")

old_batter = '''def fetch_batter_platoon(player: dict[str, str], season: int) -> dict[str, Any]:
    player_id = clean(player.get("playerId"))
    result: dict[str, Any] = {
        "season": season,
        "playerId": player_id,
        "player": clean(player.get("player")),
        "team": clean(player.get("team")),
        "updatedAt": now_iso(),
    }
    data = mlb_get(f"people/{player_id}/stats", {
        "stats": "season",
        "group": "hitting",
        "sitCodes": "vl,vr",
        "season": season,
    })
    for split in data.get("stats", [{}])[0].get("splits", []):
        code = clean(split.get("split", {}).get("code")).lower()
        stat = split.get("stat", {})
        suffix = "VsLHP" if code == "vl" else "VsRHP" if code == "vr" else ""
        if not suffix:
            continue
        result[f"avg{suffix}"] = stat.get("avg", "")
        result[f"obp{suffix}"] = stat.get("obp", "")
        result[f"slg{suffix}"] = stat.get("slg", "")
        result[f"ops{suffix}"] = stat.get("ops", "")
        result[f"kRate{suffix}"] = stat_rate(stat, "strikeOuts")
        result[f"bbRate{suffix}"] = stat_rate(stat, "baseOnBalls")
        result[f"pa{suffix}"] = stat.get("plateAppearances", "")
    result["platoonAvgGap"] = round(to_float(result.get("avgVsRHP")) - to_float(result.get("avgVsLHP")), 3)
    return result
'''

new_batter = '''def first_split_stat(data: dict[str, Any]) -> dict[str, Any]:
    for stat_group in data.get("stats", []):
        splits = stat_group.get("splits", [])
        if splits:
            return splits[0].get("stat", {}) or {}
    return {}


def fetch_player_split_stat(player_id: str, season: int, group: str, sit_code: str) -> dict[str, Any]:
    # StatsAPI returns platoon situational splits most reliably through statSplits
    # with one sitCode per request.
    data = mlb_get(f"people/{player_id}/stats", {
        "stats": "statSplits",
        "group": group,
        "sitCodes": sit_code,
        "season": season,
    })
    return first_split_stat(data)


def fetch_batter_platoon(player: dict[str, str], season: int) -> dict[str, Any]:
    player_id = clean(player.get("playerId"))
    result: dict[str, Any] = {
        "season": season,
        "playerId": player_id,
        "player": clean(player.get("player")),
        "team": clean(player.get("team")),
        "updatedAt": now_iso(),
    }

    split_map = {
        "vl": "VsLHP",
        "vr": "VsRHP",
    }

    for sit_code, suffix in split_map.items():
        stat = fetch_player_split_stat(player_id, season, "hitting", sit_code)
        result[f"avg{suffix}"] = stat.get("avg", "")
        result[f"obp{suffix}"] = stat.get("obp", "")
        result[f"slg{suffix}"] = stat.get("slg", "")
        result[f"ops{suffix}"] = stat.get("ops", "")
        result[f"kRate{suffix}"] = stat_rate(stat, "strikeOuts")
        result[f"bbRate{suffix}"] = stat_rate(stat, "baseOnBalls")
        result[f"pa{suffix}"] = stat.get("plateAppearances", "")

    result["platoonAvgGap"] = round(to_float(result.get("avgVsRHP")) - to_float(result.get("avgVsLHP")), 3)
    return result
'''

old_pitcher = '''def fetch_pitcher_platoon(player: dict[str, str], season: int) -> dict[str, Any]:
    player_id = clean(player.get("playerId"))
    result: dict[str, Any] = {
        "season": season,
        "playerId": player_id,
        "player": clean(player.get("player")),
        "team": clean(player.get("team")),
        "updatedAt": now_iso(),
    }
    data = mlb_get(f"people/{player_id}/stats", {
        "stats": "season",
        "group": "pitching",
        "sitCodes": "vl,vr",
        "season": season,
    })
    for split in data.get("stats", [{}])[0].get("splits", []):
        code = clean(split.get("split", {}).get("code")).lower()
        stat = split.get("stat", {})
        suffix = "VsLHB" if code == "vl" else "VsRHB" if code == "vr" else ""
        if not suffix:
            continue
        result[f"avgAllowed{suffix}"] = stat.get("avg", "")
        result[f"babip{suffix}"] = stat.get("babip", "")
        result[f"kRate{suffix}"] = stat_rate(stat, "strikeOuts", "battersFaced")
        result[f"pa{suffix}"] = stat.get("battersFaced") or stat.get("plateAppearances", "")
    result["platoonAvgGapAllowed"] = round(to_float(result.get("avgAllowedVsRHB")) - to_float(result.get("avgAllowedVsLHB")), 3)
    return result
'''

new_pitcher = '''def fetch_pitcher_platoon(player: dict[str, str], season: int) -> dict[str, Any]:
    player_id = clean(player.get("playerId"))
    result: dict[str, Any] = {
        "season": season,
        "playerId": player_id,
        "player": clean(player.get("player")),
        "team": clean(player.get("team")),
        "updatedAt": now_iso(),
    }

    split_map = {
        "vl": "VsLHB",
        "vr": "VsRHB",
    }

    for sit_code, suffix in split_map.items():
        stat = fetch_player_split_stat(player_id, season, "pitching", sit_code)
        result[f"avgAllowed{suffix}"] = stat.get("avg", "")
        result[f"babip{suffix}"] = stat.get("babip", "")
        result[f"kRate{suffix}"] = stat_rate(stat, "strikeOuts", "battersFaced")
        result[f"pa{suffix}"] = stat.get("battersFaced") or stat.get("plateAppearances", "")

    result["platoonAvgGapAllowed"] = round(to_float(result.get("avgAllowedVsRHB")) - to_float(result.get("avgAllowedVsLHB")), 3)
    return result
'''

if old_batter not in text:
    raise SystemExit("Could not find old fetch_batter_platoon block.")
if old_pitcher not in text:
    raise SystemExit("Could not find old fetch_pitcher_platoon block.")

text = text.replace(old_batter, new_batter)
text = text.replace(old_pitcher, new_pitcher)

path.write_text(text, encoding="utf-8")
print("Patched platoon_splits_collector.py to use statSplits per sitCode.")
