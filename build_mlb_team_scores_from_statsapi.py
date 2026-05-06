import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

import pandas as pd

TEAM_ABBR_FIXES = {
    "ATH": "ATH",
    "OAK": "ATH",
    "AZ": "ARI",
    "WSH": "WSN",
    "TB": "TBR",
    "SD": "SDP",
    "SF": "SFG",
    "KC": "KCR",
    "CHW": "CHW",
    "CWS": "CHW",
    "NYM": "NYM",
    "NYY": "NYY",
    "BOS": "BOS",
    "DET": "DET",
    "COL": "COL",
}


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

def norm_team(value):
    value = str(value or "").upper().strip()
    return TEAM_ABBR_FIXES.get(value, value)

def fetch_json(url):
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "New-project-MLB-score-builder/1.0"})
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        raise SystemExit(f"HTTP ERROR {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
    except URLError as exc:
        raise SystemExit(f"URL ERROR: {exc}") from exc

def first_team_to_score(linescore, home_abbr, away_abbr):
    innings = linescore.get("innings", []) or []

    for inning in innings:
        away_runs = ((inning.get("away") or {}).get("runs"))
        home_runs = ((inning.get("home") or {}).get("runs"))

        away_runs = int(away_runs or 0)
        home_runs = int(home_runs or 0)

        if away_runs > 0 and home_runs > 0:
            # Same inning. For MLB, away bats top first, so away scores first.
            return away_abbr

        if away_runs > 0:
            return away_abbr

        if home_runs > 0:
            return home_abbr

    return ""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--latest-props", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    props = pd.read_csv(args.latest_props)
    wanted = props[["fixtureId", "date", "team", "opponent"]].drop_duplicates().copy()
    wanted["date"] = wanted["date"].astype(str).str[:10]
    wanted["team"] = wanted["team"].map(norm_team)
    wanted["opponent"] = wanted["opponent"].map(norm_team)

    url = "https://statsapi.mlb.com/api/v1/schedule?" + urlencode({
        "sportId": 1,
        "startDate": args.from_date,
        "endDate": args.to_date,
        "hydrate": "linescore",
    })

    print("GET", url)

    data = fetch_json(url)

    games = []
    for date_block in data.get("dates", []) or []:
        for game in date_block.get("games", []) or []:
            status = ((game.get("status") or {}).get("detailedState") or "").lower()
            if "final" not in status:
                continue

            home = game.get("teams", {}).get("home", {}) or {}
            away = game.get("teams", {}).get("away", {}) or {}

            home_team = home.get("team", {}) or {}
            away_team = away.get("team", {}) or {}

            home_abbr = statsapi_team_abbr(home_team)
            away_abbr = statsapi_team_abbr(away_team)

            game_date = str(game.get("gameDate", ""))[:10]
            linescore = game.get("linescore", {}) or {}

            first = first_team_to_score(linescore, home_abbr, away_abbr)

            games.append({
                "date": game_date,
                "home": home_abbr,
                "away": away_abbr,
                "homeRuns": home.get("score", ""),
                "awayRuns": away.get("score", ""),
                "firstToScoreTeam": first,
            })

    game_df = pd.DataFrame(games)
    print("final MLB games found:", len(game_df))

    rows = []

    for _, want in wanted.iterrows():
        date = want["date"]
        team = norm_team(want["team"])
        opp = norm_team(want["opponent"])

        match = game_df[
            (game_df["date"].astype(str).str[:10] == date)
            & (
                ((game_df["home"] == team) & (game_df["away"] == opp))
                | ((game_df["away"] == team) & (game_df["home"] == opp))
            )
        ]

        if match.empty:
            rows.append({
                "fixtureId": want["fixtureId"],
                "date": date,
                "team": team,
                "opponent": opp,
                "runs": "",
                "firstToScore": "",
                "matchStatus": "not_found_or_not_final",
            })
            continue

        game = match.iloc[0]

        if game["home"] == team:
            runs = game["homeRuns"]
        else:
            runs = game["awayRuns"]

        rows.append({
            "fixtureId": want["fixtureId"],
            "date": date,
            "team": team,
            "opponent": opp,
            "runs": runs,
            "firstToScore": int(team == game["firstToScoreTeam"]),
            "matchStatus": "matched_final",
        })

    out = pd.DataFrame(rows)
    out.to_csv(args.output, index=False)

    print("output:", args.output)
    print("rows:", len(out))
    print()
    print(out.to_string(index=False))

    missing = out[out["matchStatus"] != "matched_final"]
    if len(missing):
        print("\nWARNING: unmatched rows:")
        print(missing.to_string(index=False))

if __name__ == "__main__":
    main()
