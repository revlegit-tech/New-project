from __future__ import annotations

"""Phase 19: observed line-movement tracking.

This module keeps line movement in the game-context layer, not in batter/pitcher
prop markets. It snapshots the current PropLine/OddsPapi-backed game context and
then computes observed first/latest movement for each team/opponent game row.

Trust rule: we never fabricate opening lines. `open_*` here means first observed
by our collector, and the source/status fields make that explicit.
"""

import argparse
import csv
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GAME_CONTEXT_DIR = DATA / "warehouse" / "game_context"
SNAPSHOT_DIR = GAME_CONTEXT_DIR / "line_snapshots"
AUDIT_DIR = DATA / "warehouse" / "audits"

TEAM_ALIASES = {
    "ari": "ARI", "arizona": "ARI", "arizona diamondbacks": "ARI",
    "atl": "ATL", "atlanta": "ATL", "atlanta braves": "ATL",
    "bal": "BAL", "baltimore": "BAL", "baltimore orioles": "BAL",
    "bos": "BOS", "boston": "BOS", "boston red sox": "BOS",
    "chc": "CHC", "chicago cubs": "CHC", "cubs": "CHC",
    "chw": "CHW", "cws": "CHW", "chicago white sox": "CHW", "white sox": "CHW",
    "cin": "CIN", "cincinnati": "CIN", "cincinnati reds": "CIN",
    "cle": "CLE", "cleveland": "CLE", "cleveland guardians": "CLE",
    "col": "COL", "colorado": "COL", "colorado rockies": "COL",
    "det": "DET", "detroit": "DET", "detroit tigers": "DET",
    "hou": "HOU", "houston": "HOU", "houston astros": "HOU",
    "kc": "KCR", "kcr": "KCR", "kansas city": "KCR", "kansas city royals": "KCR",
    "laa": "LAA", "los angeles angels": "LAA", "angels": "LAA",
    "lad": "LAD", "los angeles dodgers": "LAD", "dodgers": "LAD",
    "mia": "MIA", "miami": "MIA", "miami marlins": "MIA",
    "mil": "MIL", "milwaukee": "MIL", "milwaukee brewers": "MIL",
    "min": "MIN", "minnesota": "MIN", "minnesota twins": "MIN",
    "nym": "NYM", "new york mets": "NYM", "mets": "NYM",
    "nyy": "NYY", "new york yankees": "NYY", "yankees": "NYY",
    "ath": "ATH", "oak": "ATH", "oakland athletics": "ATH", "athletics": "ATH", "a s": "ATH",
    "phi": "PHI", "philadelphia": "PHI", "philadelphia phillies": "PHI",
    "pit": "PIT", "pittsburgh": "PIT", "pittsburgh pirates": "PIT",
    "sd": "SDP", "sdp": "SDP", "san diego": "SDP", "san diego padres": "SDP", "padres": "SDP",
    "sea": "SEA", "seattle": "SEA", "seattle mariners": "SEA",
    "sf": "SFG", "sfg": "SFG", "san francisco": "SFG", "san francisco giants": "SFG",
    "stl": "STL", "st louis": "STL", "st louis cardinals": "STL", "saint louis cardinals": "STL", "cardinals": "STL",
    "tb": "TBR", "tbr": "TBR", "tampa bay": "TBR", "tampa bay rays": "TBR",
    "tex": "TEX", "texas": "TEX", "texas rangers": "TEX",
    "tor": "TOR", "toronto": "TOR", "toronto blue jays": "TOR",
    "wsh": "WSN", "wsn": "WSN", "washington": "WSN", "washington nationals": "WSN",
}

SNAPSHOT_FIELDS = [
    "snapshot_id", "snapshot_at", "date", "season", "team", "opponent", "team_key", "opponent_key",
    "team_moneyline", "opponent_moneyline", "game_total", "moneyline_implied_probability",
    "team_implied_runs", "opponent_implied_runs", "line_source", "context_source",
]

MOVEMENT_FIELDS = [
    "open_team_moneyline", "close_team_moneyline", "moneyline_move", "opponent_moneyline_move",
    "open_game_total", "close_game_total", "total_move", "line_snapshot_count",
    "line_movement_source", "line_movement_status", "line_open_snapshot_at", "line_close_snapshot_at",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def text_key(value: Any) -> str:
    text = clean(value).lower().replace("&", " and ")
    chars = [ch if ch.isalnum() else " " for ch in text]
    return " ".join("".join(chars).split())


def team_key(value: Any) -> str:
    key = text_key(value)
    if not key:
        return ""
    return TEAM_ALIASES.get(key, key.upper())


def to_float(value: Any) -> float | None:
    text = clean(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fmt_num(value: float | None) -> str:
    if value is None:
        return ""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return (f"{value:.3f}".rstrip("0").rstrip("."))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv_atomic(path: Path, rows: list[dict[str, Any]], field_order: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for field in field_order or []:
        if field and field not in fields:
            fields.append(field)
    for row in rows:
        for key in row.keys():
            if key not in fields:
                fields.append(key)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with tmp_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: clean(row.get(field, "")) for field in fields})
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def game_context_path(date_label: str) -> Path:
    return GAME_CONTEXT_DIR / f"game_context_{date_label}.csv"


def snapshot_path(date_label: str) -> Path:
    return SNAPSHOT_DIR / f"game_line_snapshots_{date_label}.csv"


def playerboard_path(season: int) -> Path:
    return DATA / "playerboard" / f"playerboard_{season}.csv"


def snapshot_current_lines(date_label: str, season: int = 2026, *, source: str = "phase18_game_context") -> dict[str, Any]:
    """Append the current game-context lines to the observed line snapshot store."""
    context_rows = read_csv(game_context_path(date_label))
    snapshot_rows = read_csv(snapshot_path(date_label))
    stamp = now_iso()
    snapshot_id = stamp.replace(":", "").replace("-", "").replace("Z", "Z")

    appended: list[dict[str, Any]] = []
    for row in context_rows:
        team = team_key(row.get("team") or row.get("team_abbr"))
        opponent = team_key(row.get("opponent") or row.get("opponent_abbr"))
        if not team or not opponent:
            continue
        if not (clean(row.get("team_moneyline")) or clean(row.get("game_total"))):
            continue
        appended.append({
            "snapshot_id": snapshot_id,
            "snapshot_at": stamp,
            "date": date_label,
            "season": season,
            "team": clean(row.get("team")),
            "opponent": clean(row.get("opponent")),
            "team_key": team,
            "opponent_key": opponent,
            "team_moneyline": clean(row.get("team_moneyline")),
            "opponent_moneyline": clean(row.get("opponent_moneyline")),
            "game_total": clean(row.get("game_total")),
            "moneyline_implied_probability": clean(row.get("moneyline_implied_probability")),
            "team_implied_runs": clean(row.get("team_implied_runs")),
            "opponent_implied_runs": clean(row.get("opponent_implied_runs")),
            "line_source": clean(row.get("moneyline_source") or row.get("total_source") or source),
            "context_source": clean(row.get("game_context_source") or source),
        })

    all_rows = snapshot_rows + appended
    if appended:
        write_csv_atomic(snapshot_path(date_label), all_rows, SNAPSHOT_FIELDS)

    result = {
        "status": "ok" if appended else "warning",
        "date": date_label,
        "season": season,
        "snapshotId": snapshot_id,
        "snapshotAt": stamp,
        "contextRows": len(context_rows),
        "appendedRows": len(appended),
        "snapshotPath": str(snapshot_path(date_label)),
    }
    write_json(AUDIT_DIR / f"phase19_line_snapshot_{date_label}.json", result)
    return result


def _movement_for_group(rows: list[dict[str, str]]) -> dict[str, str]:
    rows = sorted(rows, key=lambda row: clean(row.get("snapshot_at")))
    if not rows:
        return {}
    first = rows[0]
    latest = rows[-1]
    count = len(rows)

    open_ml = to_float(first.get("team_moneyline"))
    close_ml = to_float(latest.get("team_moneyline"))
    open_opp_ml = to_float(first.get("opponent_moneyline"))
    close_opp_ml = to_float(latest.get("opponent_moneyline"))
    open_total = to_float(first.get("game_total"))
    close_total = to_float(latest.get("game_total"))

    status = "ready" if count >= 2 else "single_snapshot_first_observed"
    return {
        "open_team_moneyline": fmt_num(open_ml),
        "close_team_moneyline": fmt_num(close_ml),
        "moneyline_move": fmt_num(close_ml - open_ml) if count >= 2 and open_ml is not None and close_ml is not None else "",
        "opponent_moneyline_move": fmt_num(close_opp_ml - open_opp_ml) if count >= 2 and open_opp_ml is not None and close_opp_ml is not None else "",
        "open_game_total": fmt_num(open_total),
        "close_game_total": fmt_num(close_total),
        "total_move": fmt_num(close_total - open_total) if count >= 2 and open_total is not None and close_total is not None else "",
        "line_snapshot_count": str(count),
        "line_movement_source": "phase19_observed_first_latest_snapshot",
        "line_movement_status": status,
        "line_open_snapshot_at": clean(first.get("snapshot_at")),
        "line_close_snapshot_at": clean(latest.get("snapshot_at")),
    }


def movement_index(date_label: str) -> dict[tuple[str, str], dict[str, str]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in read_csv(snapshot_path(date_label)):
        team = team_key(row.get("team_key") or row.get("team"))
        opponent = team_key(row.get("opponent_key") or row.get("opponent"))
        if team and opponent:
            groups.setdefault((team, opponent), []).append(row)
    return {key: _movement_for_group(rows) for key, rows in groups.items()}


def apply_line_movement(date_label: str, season: int = 2026, *, patch_playerboard: bool = False) -> dict[str, Any]:
    idx = movement_index(date_label)
    context_path = game_context_path(date_label)
    rows = read_csv(context_path)
    updated = 0
    for row in rows:
        key = (team_key(row.get("team") or row.get("team_abbr")), team_key(row.get("opponent") or row.get("opponent_abbr")))
        movement = idx.get(key) or {}
        if not movement:
            continue
        changed = False
        for field, value in movement.items():
            if value and clean(row.get(field)) != value:
                row[field] = value
                changed = True
        if changed:
            updated += 1
    if rows:
        field_order = list(rows[0].keys()) + [field for field in MOVEMENT_FIELDS if field not in rows[0]]
        write_csv_atomic(context_path, rows, field_order)

    playerboard_result = {"status": "skipped", "reason": "canonical EdgeBoard join reads game_context directly"}
    if patch_playerboard:
        playerboard_result = apply_line_movement_to_playerboard(date_label, season, idx)

    ready_rows = sum(1 for row in rows if clean(row.get("line_movement_status")) == "ready")
    result = {
        "status": "ok" if updated or rows else "warning",
        "date": date_label,
        "season": season,
        "contextRows": len(rows),
        "updatedContextRows": updated,
        "readyMovementRows": ready_rows,
        "singleSnapshotRows": sum(1 for row in rows if clean(row.get("line_movement_status")) == "single_snapshot_first_observed"),
        "snapshotGroups": len(idx),
        "contextPath": str(context_path),
        "snapshotPath": str(snapshot_path(date_label)),
        "playerboardPatch": playerboard_result,
    }
    write_json(AUDIT_DIR / f"phase19_line_movement_{date_label}.json", result)
    return result


def apply_line_movement_to_playerboard(date_label: str, season: int, idx: dict[tuple[str, str], dict[str, str]]) -> dict[str, Any]:
    path = playerboard_path(season)
    rows = read_csv(path)
    updated = 0
    for row in rows:
        if clean(row.get("date")) != date_label:
            continue
        key = (team_key(row.get("team")), team_key(row.get("opponent")))
        movement = idx.get(key) or {}
        if not movement:
            continue
        changed = False
        for field, value in movement.items():
            if value and clean(row.get(field)) != value:
                row[field] = value
                changed = True
        if changed:
            updated += 1
    if rows:
        write_csv_atomic(path, rows)
    return {"status": "ok", "path": str(path), "rows": len(rows), "updatedRows": updated}


def run_phase19(date_label: str, season: int = 2026, *, source: str = "phase18_game_context", patch_playerboard: bool = False) -> dict[str, Any]:
    snap = snapshot_current_lines(date_label, season, source=source)
    movement = apply_line_movement(date_label, season, patch_playerboard=patch_playerboard)
    result = {"status": "ok" if movement.get("status") == "ok" else "warning", "snapshot": snap, "movement": movement}
    write_json(AUDIT_DIR / f"phase19_run_{date_label}.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 19 observed line movement tracker.")
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--date", required=True)
    snap.add_argument("--season", type=int, default=2026)
    snap.add_argument("--source", default="phase18_game_context")

    apply = sub.add_parser("apply")
    apply.add_argument("--date", required=True)
    apply.add_argument("--season", type=int, default=2026)
    apply.add_argument("--patch-playerboard", action="store_true")

    run = sub.add_parser("run")
    run.add_argument("--date", required=True)
    run.add_argument("--season", type=int, default=2026)
    run.add_argument("--source", default="phase18_game_context")
    run.add_argument("--patch-playerboard", action="store_true")

    args = parser.parse_args()
    if args.command == "snapshot":
        payload = snapshot_current_lines(args.date, args.season, source=args.source)
    elif args.command == "apply":
        payload = apply_line_movement(args.date, args.season, patch_playerboard=args.patch_playerboard)
    else:
        payload = run_phase19(args.date, args.season, source=args.source, patch_playerboard=args.patch_playerboard)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
