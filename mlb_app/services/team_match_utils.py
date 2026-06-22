from __future__ import annotations

import re
from typing import Any

TEAM_ALIASES: dict[str, str] = {
    "ARI": "ARI",
    "AZ": "ARI",
    "ARIZONA": "ARI",
    "ARIZONA DIAMONDBACKS": "ARI",
    "DIAMONDBACKS": "ARI",
    "ATL": "ATL",
    "ATLANTA": "ATL",
    "ATLANTA BRAVES": "ATL",
    "BRAVES": "ATL",
    "BAL": "BAL",
    "BALTIMORE": "BAL",
    "BALTIMORE ORIOLES": "BAL",
    "ORIOLES": "BAL",
    "BOS": "BOS",
    "BOSTON": "BOS",
    "BOSTON RED SOX": "BOS",
    "RED SOX": "BOS",
    "CHC": "CHC",
    "CHICAGO CUBS": "CHC",
    "CUBS": "CHC",
    "CHW": "CHW",
    "CWS": "CHW",
    "CHICAGO WHITE SOX": "CHW",
    "WHITE SOX": "CHW",
    "CIN": "CIN",
    "CINCINNATI": "CIN",
    "CINCINNATI REDS": "CIN",
    "REDS": "CIN",
    "CLE": "CLE",
    "CLEVELAND": "CLE",
    "CLEVELAND GUARDIANS": "CLE",
    "CLEVELAND INDIANS": "CLE",
    "GUARDIANS": "CLE",
    "INDIANS": "CLE",
    "COL": "COL",
    "COLORADO": "COL",
    "COLORADO ROCKIES": "COL",
    "ROCKIES": "COL",
    "DET": "DET",
    "DETROIT": "DET",
    "DETROIT TIGERS": "DET",
    "TIGERS": "DET",
    "HOU": "HOU",
    "HOUSTON": "HOU",
    "HOUSTON ASTROS": "HOU",
    "ASTROS": "HOU",
    "KC": "KCR",
    "KCR": "KCR",
    "KANSAS CITY": "KCR",
    "KANSAS CITY ROYALS": "KCR",
    "ROYALS": "KCR",
    "LAA": "LAA",
    "ANA": "LAA",
    "LOS ANGELES ANGELS": "LAA",
    "LA ANGELS": "LAA",
    "ANGELS": "LAA",
    "LAD": "LAD",
    "LOS ANGELES DODGERS": "LAD",
    "LA DODGERS": "LAD",
    "DODGERS": "LAD",
    "MIA": "MIA",
    "MIAMI": "MIA",
    "MIAMI MARLINS": "MIA",
    "MARLINS": "MIA",
    "MIL": "MIL",
    "MILWAUKEE": "MIL",
    "MILWAUKEE BREWERS": "MIL",
    "BREWERS": "MIL",
    "MIN": "MIN",
    "MINNESOTA": "MIN",
    "MINNESOTA TWINS": "MIN",
    "TWINS": "MIN",
    "NYM": "NYM",
    "NEW YORK METS": "NYM",
    "NY METS": "NYM",
    "METS": "NYM",
    "NYY": "NYY",
    "NEW YORK YANKEES": "NYY",
    "NY YANKEES": "NYY",
    "YANKEES": "NYY",
    "OAK": "ATH",
    "ATH": "ATH",
    "OAKLAND": "ATH",
    "OAKLAND ATHLETICS": "ATH",
    "ATHLETICS": "ATH",
    "PHI": "PHI",
    "PHILADELPHIA": "PHI",
    "PHILADELPHIA PHILLIES": "PHI",
    "PHILLIES": "PHI",
    "PIT": "PIT",
    "PITTSBURGH": "PIT",
    "PITTSBURGH PIRATES": "PIT",
    "PIRATES": "PIT",
    "SD": "SDP",
    "SDP": "SDP",
    "SAN DIEGO": "SDP",
    "SAN DIEGO PADRES": "SDP",
    "PADRES": "SDP",
    "SEA": "SEA",
    "SEATTLE": "SEA",
    "SEATTLE MARINERS": "SEA",
    "MARINERS": "SEA",
    "SF": "SFG",
    "SFG": "SFG",
    "SAN FRANCISCO": "SFG",
    "SAN FRANCISCO GIANTS": "SFG",
    "GIANTS": "SFG",
    "STL": "STL",
    "ST. LOUIS": "STL",
    "ST LOUIS": "STL",
    "ST. LOUIS CARDINALS": "STL",
    "ST LOUIS CARDINALS": "STL",
    "CARDINALS": "STL",
    "TB": "TBR",
    "TBR": "TBR",
    "TAMPA BAY": "TBR",
    "TAMPA BAY RAYS": "TBR",
    "RAYS": "TBR",
    "TEX": "TEX",
    "TEXAS": "TEX",
    "TEXAS RANGERS": "TEX",
    "RANGERS": "TEX",
    "TOR": "TOR",
    "TORONTO": "TOR",
    "TORONTO BLUE JAYS": "TOR",
    "BLUE JAYS": "TOR",
    "WSH": "WSN",
    "WSN": "WSN",
    "WAS": "WSN",
    "WASHINGTON": "WSN",
    "WASHINGTON NATIONALS": "WSN",
    "NATIONALS": "WSN",
}


def normalize_team_alias(value: Any) -> str:
    """Return a canonical MLB abbreviation without fuzzy matching."""

    candidates: list[Any] = []
    if isinstance(value, dict):
        candidates.extend(
            [
                value.get("shortName"),
                value.get("abbreviation"),
                value.get("teamCode"),
                value.get("fullName"),
                value.get("displayName"),
                value.get("name"),
                value.get("nickname"),
            ]
        )
    else:
        candidates.append(value)

    for candidate in candidates:
        key = team_alias_key(candidate)
        if key in TEAM_ALIASES:
            return TEAM_ALIASES[key]
    fallback = team_alias_key(candidates[0] if candidates else "")
    return fallback[:4] if fallback else ""


def team_alias_key(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9.]+", " ", text)
    text = " ".join(text.split())
    return text
