from __future__ import annotations

import csv
from pathlib import Path

from tools import phase19_line_movement as p19


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_phase19_snapshot_and_apply_line_movement(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setattr(p19, "DATA", data)
    monkeypatch.setattr(p19, "GAME_CONTEXT_DIR", data / "warehouse" / "game_context")
    monkeypatch.setattr(p19, "SNAPSHOT_DIR", data / "warehouse" / "game_context" / "line_snapshots")
    monkeypatch.setattr(p19, "AUDIT_DIR", data / "warehouse" / "audits")

    context_path = p19.GAME_CONTEXT_DIR / "game_context_2026-05-07.csv"
    write_csv(context_path, [
        {"date": "2026-05-07", "team": "san diego padres", "opponent": "st. louis cardinals", "team_moneyline": "-110", "opponent_moneyline": "+100", "game_total": "7.5"},
        {"date": "2026-05-07", "team": "st. louis cardinals", "opponent": "san diego padres", "team_moneyline": "+100", "opponent_moneyline": "-110", "game_total": "7.5"},
    ])

    snap1 = p19.snapshot_current_lines("2026-05-07", 2026)
    assert snap1["appendedRows"] == 2

    rows = read_csv(context_path)
    rows[0]["team_moneyline"] = "-102"
    rows[0]["opponent_moneyline"] = "+102"
    rows[0]["game_total"] = "8"
    rows[1]["team_moneyline"] = "+102"
    rows[1]["opponent_moneyline"] = "-102"
    rows[1]["game_total"] = "8"
    write_csv(context_path, rows)

    snap2 = p19.snapshot_current_lines("2026-05-07", 2026)
    assert snap2["appendedRows"] == 2
    result = p19.apply_line_movement("2026-05-07", 2026)
    assert result["updatedContextRows"] == 2

    updated = read_csv(context_path)
    sdp = next(row for row in updated if p19.team_key(row["team"]) == "SDP")
    assert sdp["open_team_moneyline"] == "-110"
    assert sdp["close_team_moneyline"] == "-102"
    assert sdp["moneyline_move"] == "8"
    assert sdp["open_game_total"] == "7.5"
    assert sdp["close_game_total"] == "8"
    assert sdp["total_move"] == "0.5"
    assert sdp["line_movement_status"] == "ready"


def test_single_snapshot_is_explicit_not_fabricated(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setattr(p19, "DATA", data)
    monkeypatch.setattr(p19, "GAME_CONTEXT_DIR", data / "warehouse" / "game_context")
    monkeypatch.setattr(p19, "SNAPSHOT_DIR", data / "warehouse" / "game_context" / "line_snapshots")
    monkeypatch.setattr(p19, "AUDIT_DIR", data / "warehouse" / "audits")

    context_path = p19.GAME_CONTEXT_DIR / "game_context_2026-05-07.csv"
    write_csv(context_path, [{"date": "2026-05-07", "team": "SDP", "opponent": "STL", "team_moneyline": "-102", "opponent_moneyline": "102", "game_total": "7.5"}])
    p19.snapshot_current_lines("2026-05-07", 2026)
    p19.apply_line_movement("2026-05-07", 2026)
    row = read_csv(context_path)[0]
    assert row["open_team_moneyline"] == "-102"
    assert row["close_team_moneyline"] == "-102"
    assert row["moneyline_move"] == ""
    assert row["line_movement_status"] == "single_snapshot_first_observed"
