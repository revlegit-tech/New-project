from pathlib import Path

path = Path("umpire_collector.py")
text = path.read_text(encoding="utf-8")

old = '''def fetch_game_umpire(game_pk: str) -> dict[str, Any]:
    data = mlb_get(f"game/{game_pk}/linescore")
    for official in data.get("officials", []):
        if clean(official.get("officialType")).lower() == "home plate":
            person = official.get("official", {})
            return {
                "homePlateUmpireId": clean(person.get("id")),
                "homePlateUmpireName": clean(person.get("fullName")),
            }
    return {}
'''

new = '''def extract_home_plate_umpire(payload: Any) -> dict[str, Any]:
    """Find home-plate umpire from MLB StatsAPI payloads."""
    if isinstance(payload, dict):
        officials = payload.get("officials")
        if isinstance(officials, list):
            for official in officials:
                if not isinstance(official, dict):
                    continue

                official_type = clean(
                    official.get("officialType")
                    or official.get("type")
                    or official.get("role")
                ).lower()

                if "home" in official_type and "plate" in official_type:
                    person = official.get("official") or official.get("person") or {}

                    if isinstance(person, dict):
                        return {
                            "homePlateUmpireId": clean(person.get("id")),
                            "homePlateUmpireName": clean(
                                person.get("fullName")
                                or person.get("name")
                                or person.get("full_name")
                            ),
                        }

                    return {
                        "homePlateUmpireId": clean(official.get("id")),
                        "homePlateUmpireName": clean(
                            official.get("fullName")
                            or official.get("name")
                            or official.get("full_name")
                        ),
                    }

        for value in payload.values():
            found = extract_home_plate_umpire(value)
            if found:
                return found

    elif isinstance(payload, list):
        for value in payload:
            found = extract_home_plate_umpire(value)
            if found:
                return found

    return {}


def fetch_game_umpire(game_pk: str) -> dict[str, Any]:
    endpoints = [
        f"game/{game_pk}/boxscore",
        f"game/{game_pk}/feed/live",
        f"game/{game_pk}/linescore",
    ]

    for endpoint in endpoints:
        try:
            data = mlb_get(endpoint)
        except Exception:
            continue

        found = extract_home_plate_umpire(data)
        if found:
            return found

    return {}
'''

if old not in text:
    raise SystemExit("Could not find old fetch_game_umpire block. It may already be patched.")

path.write_text(text.replace(old, new), encoding="utf-8")
print("Patched fetch_game_umpire to try boxscore, live feed, and linescore.")
