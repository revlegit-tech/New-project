from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]

# Observed OddsPapi MLB participant ids from tournamentId=109.
# Safe metadata-only fallback when /v4/fixtures and /v4/participants are plan-blocked.
# This does NOT fabricate odds, opening lines, totals, implied runs, or CLV.
ODDSPAPI_MLB_PARTICIPANTS: dict[str, str] = {
    "3627": "texas rangers",
    "3628": "philadelphia phillies",
    "3629": "arizona diamondbacks",
    "3630": "new york yankees",
    "3632": "san diego padres",
    "3633": "houston astros",
    "3634": "pittsburgh pirates",
    "3635": "colorado rockies",
    "3636": "st. louis cardinals",
    "3637": "san francisco giants",
    "3638": "atlanta braves",
    "3639": "washington nationals",
    "3640": "new york mets",
    "3641": "chicago white sox",
    "3642": "los angeles angels",
    "3644": "seattle mariners",
    "3645": "baltimore orioles",
    "3646": "tampa bay rays",
    "3647": "chicago cubs",
    "3648": "kansas city royals",
    "3649": "cleveland guardians",
    "3650": "minnesota twins",
    "3651": "detroit tigers",
    "3652": "oakland athletics",
    "3653": "boston red sox",
    "3654": "milwaukee brewers",
    "3655": "cincinnati reds",
    "3656": "los angeles dodgers",
    "5929": "toronto blue jays",
    "5930": "miami marlins",
}

ALIASES: dict[str, str] = {
    "ari": "arizona diamondbacks",
    "atl": "atlanta braves",
    "ath": "oakland athletics",
    "athletics": "oakland athletics",
    "bal": "baltimore orioles",
    "bos": "boston red sox",
    "chc": "chicago cubs",
    "chw": "chicago white sox",
    "cws": "chicago white sox",
    "cin": "cincinnati reds",
    "cle": "cleveland guardians",
    "col": "colorado rockies",
    "det": "detroit tigers",
    "hou": "houston astros",
    "kc": "kansas city royals",
    "kcr": "kansas city royals",
    "laa": "los angeles angels",
    "lad": "los angeles dodgers",
    "mia": "miami marlins",
    "mil": "milwaukee brewers",
    "min": "minnesota twins",
    "nym": "new york mets",
    "nyy": "new york yankees",
    "phi": "philadelphia phillies",
    "pit": "pittsburgh pirates",
    "sd": "san diego padres",
    "sdp": "san diego padres",
    "sea": "seattle mariners",
    "sf": "san francisco giants",
    "sfg": "san francisco giants",
    "stl": "st. louis cardinals",
    "st louis cardinals": "st. louis cardinals",
    "saint louis cardinals": "st. louis cardinals",
    "tb": "tampa bay rays",
    "tbr": "tampa bay rays",
    "tex": "texas rangers",
    "tor": "toronto blue jays",
    "was": "washington nationals",
    "wsh": "washington nationals",
    "wsn": "washington nationals",
}


def _basic_clean_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&amp;", "&")
    text = text.replace(".", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_name(value: Any) -> str:
    text = _basic_clean_name(value)
    alias = ALIASES.get(text)
    if alias:
        # Avoid recursive alias loops such as st louis cardinals -> st. louis cardinals -> st louis cardinals.
        text = _basic_clean_name(alias)
    if text in {"st louis cardinals", "saint louis cardinals"}:
        return "st louis cardinals"
    if text in {"oakland athletics", "athletics"}:
        return "oakland athletics"
    return text


def _canonical_team(value: Any) -> str:
    return _clean_name(value)


def _team_pair_key(team: Any, opponent: Any) -> tuple[str, str]:
    return tuple(sorted([_canonical_team(team), _canonical_team(opponent)]))  # type: ignore[return-value]


def _walk_fixtures(obj: Any) -> Iterable[dict[str, Any]]:
    if isinstance(obj, list):
        for item in obj:
            yield from _walk_fixtures(item)
    elif isinstance(obj, dict):
        if obj.get("fixtureId") or obj.get("fixture_id"):
            yield obj
        for value in obj.values():
            if isinstance(value, (dict, list)):
                yield from _walk_fixtures(value)


def _load_latest_odds_archive(date: str, explicit_path: str | None = None) -> Path:
    if explicit_path:
        path = Path(explicit_path)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            raise FileNotFoundError(f"OddsPapi archive not found: {path}")
        return path

    directory = ROOT / "data" / "warehouse" / "game_context" / "oddspapi" / date
    files = sorted(directory.glob("odds_by_tournaments_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No OddsPapi odds_by_tournaments archive found in {directory}")
    return files[-1]


def _extract_bookmakers(fixture: dict[str, Any]) -> str:
    books = fixture.get("bookmakerOdds")
    if isinstance(books, dict):
        return ",".join(sorted(str(k) for k in books.keys()))
    return ""


def _fixture_status(fixture: dict[str, Any]) -> str:
    status = fixture.get("statusName") or fixture.get("status") or fixture.get("statusId")
    return "" if status is None else str(status)


def _build_fixture_index(odds_archive_path: Path) -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]]]:
    payload = json.loads(odds_archive_path.read_text(encoding="utf-8"))
    index: dict[tuple[str, str], dict[str, Any]] = {}
    fixtures: list[dict[str, Any]] = []

    for fixture in _walk_fixtures(payload):
        p1 = str(fixture.get("participant1Id") or "").strip()
        p2 = str(fixture.get("participant2Id") or "").strip()
        if not p1 or not p2:
            continue

        team1 = ODDSPAPI_MLB_PARTICIPANTS.get(p1, "")
        team2 = ODDSPAPI_MLB_PARTICIPANTS.get(p2, "")
        enriched = dict(fixture)
        enriched["participant1NameFallback"] = team1
        enriched["participant2NameFallback"] = team2
        fixtures.append(enriched)

        if team1 and team2:
            index.setdefault(_team_pair_key(team1, team2), enriched)

    return index, fixtures


def _ensure_fieldnames(fieldnames: list[str], required: Iterable[str]) -> list[str]:
    output = list(fieldnames)
    for field in required:
        if field not in output:
            output.append(field)
    return output


def apply_fixture_metadata(
    *,
    date: str,
    season: int,
    odds_archive_path: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    context_path = ROOT / "data" / "warehouse" / "game_context" / f"game_context_{date}.csv"
    if not context_path.exists():
        raise FileNotFoundError(f"game_context file not found: {context_path}")

    archive = _load_latest_odds_archive(date, odds_archive_path)
    fixture_index, fixtures = _build_fixture_index(archive)

    with context_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    required_fields = [
        "oddspapi_fixture_id",
        "oddspapi_fixture_status",
        "oddspapi_bookmakers",
        "oddspapi_raw_snapshot_path",
        "oddspapi_provider_status",
        "oddspapi_provider_note",
        "oddspapi_matched_at",
        "oddspapi_participant1_id",
        "oddspapi_participant2_id",
        "oddspapi_participant1_name",
        "oddspapi_participant2_name",
    ]
    fieldnames = _ensure_fieldnames(fieldnames, required_fields)

    matched_rows = 0
    candidate_rows = 0
    unmatched_pairs: set[str] = set()

    for row in rows:
        team = row.get("team") or row.get("team_name") or row.get("home_team")
        opponent = row.get("opponent") or row.get("opp") or row.get("away_team")
        if not team or not opponent:
            continue

        candidate_rows += 1
        key = _team_pair_key(team, opponent)
        fixture = fixture_index.get(key)
        if not fixture:
            unmatched_pairs.add(" vs ".join(key))
            continue

        matched_rows += 1
        row["oddspapi_fixture_id"] = str(fixture.get("fixtureId") or fixture.get("fixture_id") or "")
        row["oddspapi_fixture_status"] = _fixture_status(fixture)
        row["oddspapi_bookmakers"] = _extract_bookmakers(fixture)
        row["oddspapi_raw_snapshot_path"] = str(archive)
        row["oddspapi_provider_status"] = "fixture_matched_no_clv"
        row["oddspapi_provider_note"] = (
            "Matched via local OddsPapi MLB participant-id map because fixtures/participants endpoints "
            "were unavailable for this key/plan. No opening lines or CLV were fabricated."
        )
        row["oddspapi_matched_at"] = now
        row["oddspapi_participant1_id"] = str(fixture.get("participant1Id") or "")
        row["oddspapi_participant2_id"] = str(fixture.get("participant2Id") or "")
        row["oddspapi_participant1_name"] = str(fixture.get("participant1NameFallback") or "")
        row["oddspapi_participant2_name"] = str(fixture.get("participant2NameFallback") or "")

    backup_path = ""
    if not dry_run:
        backup = context_path.with_suffix(context_path.suffix + f".phase22v3_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        backup.write_text(context_path.read_text(encoding="utf-8"), encoding="utf-8")
        backup_path = str(backup)

        with context_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    audit_dir = ROOT / "data" / "warehouse" / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit = {
        "status": "ok" if matched_rows else "warning",
        "phase": "22_v3_fixture_metadata_fallback",
        "date": date,
        "season": season,
        "contextPath": str(context_path),
        "oddsArchive": str(archive),
        "fixtureCount": len(fixtures),
        "fixtureIndexPairs": len(fixture_index),
        "contextRows": len(rows),
        "candidateRows": candidate_rows,
        "matchedRows": matched_rows,
        "unmatchedPairs": sorted(unmatched_pairs),
        "dryRun": dry_run,
        "backup": backup_path,
        "notes": [
            "This v3 fallback only fills OddsPapi fixture metadata.",
            "It does not fabricate CLV, opening lines, moneyline movement, totals, or implied runs.",
            "Phase 19 observed movement remains the movement source until CLV is available.",
        ],
    }
    audit_path = audit_dir / f"phase22_v3_fixture_metadata_fallback_{date}.json"
    if not dry_run:
        audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    audit["auditPath"] = str(audit_path)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Phase 22 v3 OddsPapi fixture metadata fallback to game_context.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--odds-archive", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = apply_fixture_metadata(
        date=args.date,
        season=args.season,
        odds_archive_path=args.odds_archive or None,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
