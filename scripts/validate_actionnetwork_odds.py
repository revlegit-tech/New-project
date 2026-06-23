from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from mlb_app.services.mlb_truth_log_resolver import load_truth_logs


BATTER_LOG = Path("data/cloud/season_logs/batter_game_logs_2026.csv")
PITCHER_LOG = Path("data/cloud/season_logs/pitcher_game_logs_2026.csv")
TEAM_LOG = Path("data/cloud/season_logs/team_game_logs_2026.csv")
ODDS_DIR = Path("data/warehouse/normalized/odds")
QUALITY_DIR = Path("data/warehouse/quality")
LABEL_DIR = Path("data/warehouse/ml_labels")

EVENT_OVERLAP_PATH = QUALITY_DIR / "actionnetwork_backfill_event_overlap_2026.csv"
SUMMARY_PATH = QUALITY_DIR / "actionnetwork_backfill_integrity_summary_2026.csv"


def norm(value: Any) -> str:
    value = "" if value is None else str(value)
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def norm_name(value: Any) -> str:
    value = "" if value is None else str(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = re.sub(r"\s+", " ", value).strip().split()

    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    while tokens and tokens[-1] in suffixes:
        tokens.pop()

    if not tokens:
        return ""

    # C J Abrams -> cj abrams, A J Ewing -> aj ewing, O Hoppe -> ohoppe
    leading = []
    while tokens and len(tokens[0]) == 1:
        leading.append(tokens.pop(0))

    if leading:
        if len(leading) >= 2:
            tokens.insert(0, "".join(leading))
        elif tokens:
            tokens.insert(0, leading[0] + tokens.pop(0))
        else:
            tokens.insert(0, leading[0])

    return " ".join(tokens)


def parse_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_suspect_dates(overlap_threshold: float = 80.0) -> set[str]:
    suspect: set[str] = set()

    if EVENT_OVERLAP_PATH.exists():
        for row in read_csv(EVENT_OVERLAP_PATH):
            overlap = parse_float(row.get("event_overlap_pct")) or 0
            if overlap >= overlap_threshold:
                suspect.add(row.get("previous_date", ""))
                suspect.add(row.get("current_date", ""))

    if SUMMARY_PATH.exists():
        rows = read_csv(SUMMARY_PATH)
        fp_counts = Counter(row.get("fingerprint", "") for row in rows if row.get("fingerprint", ""))
        duplicated = {fp for fp, count in fp_counts.items() if count > 1}
        for row in rows:
            if row.get("fingerprint") in duplicated:
                suspect.add(row.get("date", ""))

    return {d for d in suspect if d}


def game_pk(row: dict[str, str]) -> str:
    return str(row.get("gamePk") or row.get("game_pk") or row.get("game_id") or "").strip()


def index_logs(rows: list[dict[str, str]], player_col: str = "player") -> tuple[dict[tuple[str, str], list[dict[str, str]]], set[str]]:
    by_date_player: dict[tuple[str, str], list[dict[str, str]]] = {}
    known_players: set[str] = set()

    for row in rows:
        date = row.get("date", "")
        player = norm_name(row.get(player_col, ""))
        if not date or not player:
            continue

        known_players.add(player)
        by_date_player.setdefault((date, player), []).append(row)

    return by_date_player, known_players


def index_logs_by_game(rows: list[dict[str, str]], player_col: str = "player") -> dict[tuple[str, str], list[dict[str, str]]]:
    by_game_player: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        player = norm_name(row.get(player_col, ""))
        pk = game_pk(row)
        if player and pk:
            by_game_player.setdefault((pk, player), []).append(row)
    return by_game_player


def index_team_logs(rows: list[dict[str, str]]) -> tuple[dict[tuple[str, str], list[dict[str, str]]], set[str]]:
    by_date_team: dict[tuple[str, str], list[dict[str, str]]] = {}
    known_teams: set[str] = set()

    for row in rows:
        date = row.get("date", "")
        keys = {norm(row.get("team", "")), norm(row.get("teamName", ""))}
        keys = {k for k in keys if k}

        for team in keys:
            known_teams.add(team)
            by_date_team.setdefault((date, team), []).append(row)

    return by_date_team, known_teams


def market_stat(row: dict[str, str]) -> tuple[str | None, str | None]:
    raw_group = (row.get("market_group") or "").strip().lower()
    group = raw_group.replace("-", "_").replace(" ", "_")
    market = norm(row.get("market"))
    market_type = norm(row.get("market_type"))

    text = f"{group} {market} {market_type}"

    if group == "team_total":
        return "team", "runs"

    if group in {"pitching", "alt_strikeouts"}:
        if "earned" in text:
            return "pitcher", "earnedRuns"
        if "outs" in text:
            return "pitcher", "outsRecorded"
        if "hit" in text and "allowed" in text:
            return "pitcher", "hits"
        if "strikeout" in text or " k" in f" {text} " or "ks" in text:
            return "pitcher", "strikeOuts"
        return "pitcher", "strikeOuts"

    if group in {"home_runs", "alt_home_runs"} or "home run" in text or re.search(r"\bhr\b", text):
        return "batter", "homeRuns"

    if group == "alt_hits" or "hit" in text:
        return "batter", "hits"

    if group in {"alt_bases", "runs_and_bases"} or "base" in text:
        return "batter", "totalBases"

    if group == "alt_runs" or re.search(r"\bruns?\b", text):
        return "batter", "runs"

    if group == "alt_stolen_bases" or "stolen" in text or re.search(r"\bsb\b", text):
        return "batter", "stolenBases"

    if "rbi" in text:
        return "batter", "rbi"

    if "walk" in text or "base on balls" in text:
        return "batter", "baseOnBalls"

    if "strikeout" in text:
        return "batter", "strikeOuts"

    return None, None


def actual_value(row: dict[str, str], stat: str) -> float | None:
    if stat == "outsRecorded":
        ip = row.get("inningsPitched", "")
        if not ip:
            return None

        text = str(ip)
        if "." in text:
            whole, frac = text.split(".", 1)
            return (float(whole) * 3) + float(frac[:1] or 0)

        return float(text) * 3

    value = parse_float(row.get(stat))
    return value


def score_result(actual: float, line: float, side: str) -> str:
    if actual == line:
        return "push"

    if side == "over_yes":
        return "win" if actual > line else "loss"

    if side == "under_no":
        return "win" if actual < line else "loss"

    return "bad_side"


def validate_row(
    row: dict[str, str],
    *,
    batter_by_date: dict[tuple[str, str], list[dict[str, str]]],
    pitcher_by_date: dict[tuple[str, str], list[dict[str, str]]],
    team_by_date: dict[tuple[str, str], list[dict[str, str]]],
    batter_by_game: dict[tuple[str, str], list[dict[str, str]]],
    pitcher_by_game: dict[tuple[str, str], list[dict[str, str]]],
    known_batters: set[str],
    known_pitchers: set[str],
    known_teams: set[str],
    suspect_dates: set[str],
    apply_integrity_gate: bool,
    bridge_by_event: dict[tuple[str, str], dict[str, str]],
    truth_logs_available: bool,
    requested_date_covered: bool,
) -> dict[str, str]:
    out = dict(row)

    out.update(
        {
            "validation_status": "",
            "truth_source": "",
            "matched_name": "",
            "gamePk": "",
            "bridge_status": "",
            "event_game_confidence": "",
            "actual_stat": "",
            "label_result": "",
            "label_win": "",
            "exclude_from_ml": "1",
            "exclude_reason": "",
        }
    )

    game_date = row.get("game_date", "")
    side = row.get("bet_side", "")
    line = parse_float(row.get("line"))
    odds = parse_float(row.get("american_odds"))

    if not truth_logs_available:
        out["validation_status"] = "truth_logs_missing"
        out["exclude_reason"] = "Required MLB truth logs are missing or header-only."
        return out

    if not requested_date_covered:
        out["validation_status"] = "truth_logs_missing_for_date"
        out["exclude_reason"] = "Requested date is outside truth log coverage."
        return out

    if apply_integrity_gate and game_date in suspect_dates:
        out["validation_status"] = "reused_board_suspect"
        out["exclude_reason"] = "ActionNetwork date parameter appears to return reused board/event set."
        return out

    if side not in {"over_yes", "under_no"}:
        out["validation_status"] = "bad_side"
        out["exclude_reason"] = "Missing or invalid bet_side."
        return out

    if line is None:
        out["validation_status"] = "bad_line"
        out["exclude_reason"] = "Missing or invalid line."
        return out

    if odds is None:
        out["validation_status"] = "bad_odds"
        out["exclude_reason"] = "Missing or invalid american_odds."
        return out

    entity_type, stat = market_stat(row)
    if not entity_type or not stat:
        out["validation_status"] = "unknown_market"
        out["exclude_reason"] = f"Could not map market_group={row.get('market_group')} market={row.get('market')}."
        return out

    if entity_type == "team":
        team_key = norm(row.get("team_name") or row.get("team_id"))
        matches = team_by_date.get((game_date, team_key), [])

        if not matches:
            if team_key in known_teams:
                out["validation_status"] = "wrong_date_or_team_did_not_play"
            else:
                out["validation_status"] = "unmatched_team"
            out["exclude_reason"] = "Could not match team/date to team game logs."
            return out

        truth = matches[0]
        actual = actual_value(truth, stat)

        if actual is None:
            out["validation_status"] = "valid_unlabeled"
            out["truth_source"] = "team_game_logs"
            out["matched_name"] = truth.get("teamName") or truth.get("team", "")
            out["exclude_reason"] = f"Stat {stat} unavailable."
            return out

        result = score_result(actual, line, side)
        bridge = bridge_by_event.get((game_date, row.get("event_id", "")))
        if not bridge:
            out["validation_status"] = "event_bridge_missing"
            out["exclude_reason"] = "No ActionNetwork event_id to MLB gamePk bridge row."
            return out
        out["bridge_status"] = bridge.get("bridge_status", "")
        out["event_game_confidence"] = bridge.get("confidence", "")
        out["gamePk"] = bridge.get("gamePk", "")
        if bridge.get("bridge_status") != "confirmed" or bridge.get("duplicate_best_gamePk") == "1":
            out["validation_status"] = "event_bridge_rejected"
            out["exclude_reason"] = bridge.get("exclude_reason") or "ActionNetwork event bridge was not confirmed."
            return out

        out["validation_status"] = "valid_labeled_event_confirmed" if result in {"win", "loss"} else "valid_labeled_date_only_diagnostic"
        out["truth_source"] = "team_game_logs"
        out["matched_name"] = truth.get("teamName") or truth.get("team", "")
        out["actual_stat"] = str(actual)
        out["label_result"] = result
        out["label_win"] = "1" if result == "win" else "0" if result == "loss" else ""
        live_forward = row.get("collection_mode") == "live_forward"
        out["exclude_from_ml"] = "0" if result in {"win", "loss"} and live_forward else "1"
        out["exclude_reason"] = "" if out["exclude_from_ml"] == "0" else (result if result not in {"win", "loss"} else "not_live_forward")
        return out

    player_key = norm_name(row.get("player_name"))

    if entity_type == "batter":
        matches = batter_by_date.get((game_date, player_key), [])
        game_matches = batter_by_game
        known = known_batters
        source = "batter_game_logs"
    else:
        matches = pitcher_by_date.get((game_date, player_key), [])
        game_matches = pitcher_by_game
        known = known_pitchers
        source = "pitcher_game_logs"

    if not matches:
        if player_key in known:
            out["validation_status"] = "did_not_play"
            out["exclude_reason"] = "Player exists in season logs but did not appear on this date."
        else:
            out["validation_status"] = "unmatched_player"
            out["exclude_reason"] = "Player name not found in season logs."
        return out

    truth = matches[0]
    bridge = bridge_by_event.get((game_date, row.get("event_id", "")))
    if not bridge:
        out["validation_status"] = "event_bridge_missing"
        out["exclude_reason"] = "No ActionNetwork event_id to MLB gamePk bridge row."
        return out
    out["bridge_status"] = bridge.get("bridge_status", "")
    out["event_game_confidence"] = bridge.get("confidence", "")
    out["gamePk"] = bridge.get("gamePk", "")
    if bridge.get("bridge_status") != "confirmed" or bridge.get("duplicate_best_gamePk") == "1":
        out["validation_status"] = "event_bridge_rejected"
        out["exclude_reason"] = bridge.get("exclude_reason") or "ActionNetwork event bridge was not confirmed."
        return out
    confirmed_matches = game_matches.get((bridge.get("gamePk", ""), player_key), [])
    if not confirmed_matches:
        out["validation_status"] = "player_not_in_confirmed_game"
        out["exclude_reason"] = "Player did not appear in the confirmed MLB gamePk."
        return out
    truth = confirmed_matches[0]
    actual = actual_value(truth, stat)

    if actual is None:
        out["validation_status"] = "valid_unlabeled"
        out["truth_source"] = source
        out["matched_name"] = truth.get("player", "")
        out["exclude_reason"] = f"Stat {stat} unavailable."
        return out

    result = score_result(actual, line, side)

    out["validation_status"] = "valid_labeled_event_confirmed" if result in {"win", "loss"} else "valid_labeled_date_only_diagnostic"
    out["truth_source"] = source
    out["matched_name"] = truth.get("player", "")
    out["actual_stat"] = str(actual)
    out["label_result"] = result
    out["label_win"] = "1" if result == "win" else "0" if result == "loss" else ""
    live_forward = row.get("collection_mode") == "live_forward"
    out["exclude_from_ml"] = "0" if result in {"win", "loss"} and live_forward else "1"
    out["exclude_reason"] = "" if out["exclude_from_ml"] == "0" else (result if result not in {"win", "loss"} else "not_live_forward")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and label ActionNetwork MLB odds against local season game logs.")
    parser.add_argument("--date", default=None, help="Validate one YYYY-MM-DD date.")
    parser.add_argument("--season", default="2026")
    parser.add_argument("--no-integrity-gate", action="store_true", help="Do not block reused-board suspect dates.")
    parser.add_argument("--overlap-threshold", type=float, default=80.0)
    parser.add_argument("--truth-dir", default=None, help="Optional directory containing season truth logs.")
    parser.add_argument("--bridge-path", default=None, help="Optional ActionNetwork event bridge CSV.")
    args = parser.parse_args()

    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    LABEL_DIR.mkdir(parents=True, exist_ok=True)

    truth = load_truth_logs(args.season, truth_dir=args.truth_dir)
    batter_rows = truth.batter_rows
    pitcher_rows = truth.pitcher_rows
    team_rows = truth.team_rows

    batter_by_date, known_batters = index_logs(batter_rows)
    pitcher_by_date, known_pitchers = index_logs(pitcher_rows)
    team_by_date, known_teams = index_team_logs(team_rows)
    batter_by_game = index_logs_by_game(batter_rows)
    pitcher_by_game = index_logs_by_game(pitcher_rows)

    suspect_dates = load_suspect_dates(args.overlap_threshold)
    apply_integrity_gate = not args.no_integrity_gate

    if args.date:
        odds_files = [ODDS_DIR / f"actionnetwork_all_markets_{args.date}.csv"]
    else:
        odds_files = sorted(ODDS_DIR.glob(f"actionnetwork_all_markets_{args.season}-*.csv"))

    odds_files = [path for path in odds_files if path.exists()]

    if not odds_files:
        raise SystemExit("No ActionNetwork odds files found for validation.")

    validated: list[dict[str, str]] = []
    requested_date = args.date or (read_csv(odds_files[0])[0].get("game_date", "") if odds_files and read_csv(odds_files[0]) else None)
    requested_date_covered = truth.covers(requested_date)
    bridge_path = Path(args.bridge_path) if args.bridge_path else QUALITY_DIR / f"actionnetwork_event_game_bridge_{requested_date}.csv"
    bridge_rows = read_csv(bridge_path)
    bridge_by_event = {(row.get("game_date", ""), row.get("event_id", "")): row for row in bridge_rows}

    for odds_path in odds_files:
        print("validating:", odds_path)
        for row in read_csv(odds_path):
            validated.append(
                validate_row(
                    row,
                    batter_by_date=batter_by_date,
                    pitcher_by_date=pitcher_by_date,
                    team_by_date=team_by_date,
                    batter_by_game=batter_by_game,
                    pitcher_by_game=pitcher_by_game,
                    known_batters=known_batters,
                    known_pitchers=known_pitchers,
                    known_teams=known_teams,
                    suspect_dates=suspect_dates,
                    apply_integrity_gate=apply_integrity_gate,
                    bridge_by_event=bridge_by_event,
                    truth_logs_available=bool(truth.source_dir),
                    requested_date_covered=requested_date_covered,
                )
            )

    validation_path = QUALITY_DIR / f"actionnetwork_validation_{args.season}.csv"
    labels_path = LABEL_DIR / f"actionnetwork_prop_labels_{args.season}.csv"
    summary_path = QUALITY_DIR / f"actionnetwork_validation_summary_{args.season}.json"

    if validated:
        fieldnames = list(validated[0].keys())

        with validation_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(validated)

        label_rows = [
            row
            for row in validated
            if row.get("validation_status") == "valid_labeled_event_confirmed"
            and row.get("exclude_from_ml") == "0"
            and row.get("label_result") in {"win", "loss"}
            and row.get("collection_mode") == "live_forward"
            and row.get("bridge_status") == "confirmed"
        ]

        with labels_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(label_rows)

    status_counts = Counter(row.get("validation_status", "") for row in validated)
    market_counts = Counter(row.get("market_group", "") for row in validated)
    label_counts = Counter(row.get("label_result", "") for row in validated if row.get("label_result", ""))

    summary = {
        "season": args.season,
        "date_filter": args.date,
        "odds_files": [str(p) for p in odds_files],
        "total_rows": len(validated),
        "apply_integrity_gate": apply_integrity_gate,
        "suspect_dates": sorted(suspect_dates),
        "status_counts": dict(status_counts),
        "market_counts": dict(market_counts),
        "label_counts": dict(label_counts),
        **truth.summary(requested_date),
        "bridge_csv": str(bridge_path),
        "validation_csv": str(validation_path),
        "labels_csv": str(labels_path),
    }

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("")
    print("total_rows:", len(validated))
    print("status_counts:")
    for key, count in status_counts.most_common():
        print(f"  {key}: {count}")

    print("")
    print("label_counts:")
    for key, count in label_counts.most_common():
        print(f"  {key}: {count}")

    print("")
    print("validation_csv:", validation_path)
    print("labels_csv:", labels_path)
    print("summary_json:", summary_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
