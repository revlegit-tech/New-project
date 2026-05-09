from pathlib import Path

path = Path("build_mlb_team_scores_from_statsapi.py")
text = path.read_text(encoding="utf-8")

insert = r'''
MLB_TEAM_ID_TO_ABBR = {
    108: "LAA",
    109: "ARI",
    110: "BAL",
    111: "BOS",
    112: "CHC",
    113: "CIN",
    114: "CLE",
    115: "COL",
    116: "DET",
    117: "HOU",
    118: "KCR",
    119: "LAD",
    120: "WSN",
    121: "NYM",
    133: "ATH",
    134: "PIT",
    135: "SDP",
    136: "SEA",
    137: "SFG",
    138: "STL",
    139: "TBR",
    140: "TEX",
    141: "TOR",
    142: "MIN",
    143: "PHI",
    144: "ATL",
    145: "CHW",
    146: "MIA",
    147: "NYY",
    158: "MIL",
}

MLB_TEAM_NAME_TO_ABBR = {
    "arizona diamondbacks": "ARI",
    "atlanta braves": "ATL",
    "baltimore orioles": "BAL",
    "boston red sox": "BOS",
    "chicago cubs": "CHC",
    "chicago white sox": "CHW",
    "cincinnati reds": "CIN",
    "cleveland guardians": "CLE",
    "colorado rockies": "COL",
    "detroit tigers": "DET",
    "houston astros": "HOU",
    "kansas city royals": "KCR",
    "los angeles angels": "LAA",
    "los angeles dodgers": "LAD",
    "miami marlins": "MIA",
    "milwaukee brewers": "MIL",
    "minnesota twins": "MIN",
    "new york mets": "NYM",
    "new york yankees": "NYY",
    "athletics": "ATH",
    "oakland athletics": "ATH",
    "philadelphia phillies": "PHI",
    "pittsburgh pirates": "PIT",
    "san diego padres": "SDP",
    "san francisco giants": "SFG",
    "seattle mariners": "SEA",
    "st. louis cardinals": "STL",
    "st louis cardinals": "STL",
    "tampa bay rays": "TBR",
    "texas rangers": "TEX",
    "toronto blue jays": "TOR",
    "washington nationals": "WSN",
}

def statsapi_team_abbr(team_obj):
    team_obj = team_obj or {}

    team_id = team_obj.get("id")
    try:
        team_id = int(team_id)
    except Exception:
        team_id = None

    if team_id in MLB_TEAM_ID_TO_ABBR:
        return MLB_TEAM_ID_TO_ABBR[team_id]

    for key in ["abbreviation", "teamCode", "fileCode"]:
        value = team_obj.get(key)
        if value:
            return norm_team(value)

    name = str(team_obj.get("name") or team_obj.get("teamName") or "").strip().lower()
    if name in MLB_TEAM_NAME_TO_ABBR:
        return MLB_TEAM_NAME_TO_ABBR[name]

    return norm_team(name)
'''

if "MLB_TEAM_ID_TO_ABBR" not in text:
    marker = "def norm_team(value):"
    text = text.replace(marker, insert + "\n" + marker)

text = text.replace(
'''            home_abbr = norm_team(home_team.get("abbreviation"))
            away_abbr = norm_team(away_team.get("abbreviation"))
''',
'''            home_abbr = statsapi_team_abbr(home_team)
            away_abbr = statsapi_team_abbr(away_team)
'''
)

path.write_text(text, encoding="utf-8")
print("Patched build_mlb_team_scores_from_statsapi.py with robust MLB team abbreviation mapping.")
