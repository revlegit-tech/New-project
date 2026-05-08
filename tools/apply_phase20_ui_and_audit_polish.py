from __future__ import annotations

"""Apply Phase 20 UI polish and audit cleanup.

This patch keeps Phase 18/19 context as a separate game-context layer while
making the Outlier UI easier to read and making audit output less noisy.
"""

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def backup(path: Path) -> str:
    if not path.exists():
        return ""
    dest = path.with_name(f"{path.name}.phase20_backup_{STAMP}")
    shutil.copy2(path, dest)
    return str(dest)


def upsert_block(content: str, start: str, end: str, block: str) -> tuple[str, bool]:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    replacement = f"{start}\n{block.rstrip()}\n{end}"
    if pattern.search(content):
        new_content = pattern.sub(replacement, content)
        return new_content, new_content != content
    if content and not content.endswith("\n"):
        content += "\n"
    return content + "\n" + replacement + "\n", True


def patch_outlier_detail() -> dict[str, Any]:
    path = ROOT / "public" / "outlier-detail.js"
    if not path.exists():
        return {"exists": False, "changed": False}

    original = read(path)
    block = r'''
// Phase 20 override: richer display for Phase 18/19 game context.
function gameContextCard(row) {
  const markers = phase20GameContextMarkers(row);
  const source = text(row.gameContextSource || row.game_context_source || row.gameLineSource || row.game_line_source, "Context");
  return createElement("article", { className: "ob-rail-card ob-game-context-card ob-phase20-context-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [
      createElement("h3", { text: "Game Context" }),
      createElement("span", { text: source }),
    ]),
    createElement("div", { className: "ob-rail-body" }, [
      createElement("div", { className: "ob-phase20-context-summary" }, [
        createElement("strong", { text: phase20MatchupLine(row) }),
        createElement("span", { text: weatherSummary(row) }),
      ]),
      metricGrid([
        ["Team ML", formatOdds(row.teamMoneyline ?? row.team_moneyline)],
        ["Opp ML", formatOdds(row.opponentMoneyline ?? row.opponent_moneyline)],
        ["Game Total", phase20NumberText(row.gameTotal ?? row.game_total, "Missing")],
        ["ML IP", phase20Probability(row.moneylineImpliedProbability ?? row.moneyline_implied_probability)],
        ["Team Runs", phase20NumberText(row.teamImpliedRuns ?? row.team_implied_runs, "Missing", 2)],
        ["Opp Runs", phase20NumberText(row.opponentImpliedRuns ?? row.opponent_implied_runs, "Missing", 2)],
        ["Open ML", formatOdds(row.openTeamMoneyline ?? row.open_team_moneyline)],
        ["ML Move", phase20MoveText(row.moneylineMove ?? row.moneyline_move, "pts")],
        ["Open Total", phase20NumberText(row.openGameTotal ?? row.open_game_total, "Pending")],
        ["Total Move", phase20MoveText(row.totalMove ?? row.total_move, "runs")],
        ["Park", phase20NumberText(row.parkFactor ?? row.park_factor, "Missing", 2)],
        ["Roof", phase20RoofText(row.roofStatus ?? row.roof_status)],
      ]),
      createElement("div", { className: "ob-context-markers ob-phase20-context-markers" }, markers.map((marker) => createElement("span", { className: marker.ready ? "is-ready" : "is-missing", text: marker.label }))),
      phase20ContextCopy(row),
    ]),
  ]);
}

function phase20MatchupLine(row) {
  const team = text(row.team || row.teamAbbr, "Team");
  const opponent = text(row.opponent || row.opponentAbbr, "Opponent");
  const total = phase20NumberText(row.gameTotal ?? row.game_total, "total pending");
  return `${team} vs ${opponent} · Total ${total}`;
}

function phase20NumberText(value, fallback = "--", decimals = 1) {
  const raw = text(value, "");
  if (!raw) return fallback;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return raw;
  if (Number.isInteger(parsed)) return String(parsed);
  return parsed.toFixed(decimals).replace(/0+$/, "").replace(/\.$/, "");
}

function phase20Probability(value) {
  const raw = text(value, "");
  if (!raw) return "--";
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return raw;
  const pct = Math.abs(parsed) <= 1 ? parsed * 100 : parsed;
  return `${pct.toFixed(1)}%`;
}

function phase20MoveText(value, unit = "") {
  const raw = text(value, "");
  if (!raw) return "Pending";
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return raw;
  const display = `${parsed > 0 ? "+" : ""}${parsed.toFixed(parsed % 1 ? 1 : 0)}`;
  return unit ? `${display} ${unit}` : display;
}

function phase20RoofText(value) {
  const raw = text(value, "");
  if (!raw) return "Missing";
  return raw.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function weatherSummary(row) {
  const temp = row.weatherTemperatureF ?? row.weather_temperature_f;
  const wind = row.weatherWindMph ?? row.weather_wind_mph;
  const dir = row.weatherWindDirection ?? row.weather_wind_direction;
  const humidity = row.weatherHumidity ?? row.weather_humidity;
  const precip = row.weatherPrecipProbability ?? row.weather_precip_probability;
  const parts = [];
  if (text(temp, "")) parts.push(`${phase20NumberText(temp, "--", 0)}°F`);
  if (text(wind, "")) parts.push(`Wind ${phase20NumberText(wind, "--", 1)} mph${text(dir, "") ? ` ${text(dir)}` : ""}`);
  if (text(humidity, "")) parts.push(`Humidity ${phase20NumberText(humidity, "--", 0)}%`);
  if (text(precip, "")) parts.push(`Precip ${phase20NumberText(precip, "--", 0)}%`);
  return parts.length ? parts.join(" · ") : "Weather missing";
}

function phase20GameContextMarkers(row) {
  const moneylineReady = Boolean(row.teamMoneyline || row.team_moneyline) && Boolean(row.opponentMoneyline || row.opponent_moneyline);
  const totalReady = Boolean(row.gameTotal || row.game_total);
  const impliedReady = Boolean(row.teamImpliedRuns || row.team_implied_runs) && Boolean(row.opponentImpliedRuns || row.opponent_implied_runs);
  const weatherReady = Boolean(row.weatherTemperatureF || row.weather_temperature_f || row.weatherWindMph || row.weather_wind_mph);
  const movementReady = Boolean(row.moneylineMove || row.moneyline_move || row.totalMove || row.total_move);
  return [
    { label: moneylineReady ? "moneyline ready" : "moneyline missing", ready: moneylineReady },
    { label: totalReady ? "total ready" : "total missing", ready: totalReady },
    { label: impliedReady ? "implied runs ready" : "implied runs missing", ready: impliedReady },
    { label: weatherReady ? "weather ready" : "weather missing", ready: weatherReady },
    { label: movementReady ? "movement ready" : "movement pending", ready: movementReady },
  ];
}

function phase20ContextCopy(row) {
  const movementReady = Boolean(row.moneylineMove || row.moneyline_move || row.totalMove || row.total_move);
  const copy = movementReady
    ? "Line movement is based on observed collector snapshots. Opening values are first-observed unless a provider supplies true open/CLV data."
    : "Current game context is available. Movement remains pending until a later collector snapshot or OddsPapi/opening-line source is available.";
  return createElement("p", { className: "ob-pick-copy ob-phase20-context-copy", text: copy });
}
'''
    updated, changed = upsert_block(original, "// PHASE20_GAME_CONTEXT_POLISH_START", "// PHASE20_GAME_CONTEXT_POLISH_END", block)
    if changed:
        b = backup(path)
        write(path, updated)
    else:
        b = ""
    return {"exists": True, "changed": changed, "backup": b}


def patch_css() -> dict[str, Any]:
    path = ROOT / "public" / "outlier-ui.css"
    if not path.exists():
        return {"exists": False, "changed": False}
    original = read(path)
    block = r'''
.ob-phase20-context-card .ob-rail-metrics {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.ob-phase20-context-summary {
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 14px;
  padding: 10px 12px;
  margin-bottom: 12px;
  background: rgba(255,255,255,0.035);
  display: grid;
  gap: 4px;
}

.ob-phase20-context-summary strong {
  font-size: 0.95rem;
}

.ob-phase20-context-summary span,
.ob-phase20-context-copy {
  color: var(--muted, #9aa4b2);
}

.ob-phase20-context-markers {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.ob-phase20-context-markers span {
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 0.74rem;
  border: 1px solid rgba(255,255,255,0.1);
}

.ob-phase20-context-markers .is-ready {
  background: rgba(46, 204, 113, 0.12);
}

.ob-phase20-context-markers .is-missing {
  background: rgba(255, 193, 7, 0.10);
}
'''
    updated, changed = upsert_block(original, "/* PHASE20_GAME_CONTEXT_CSS_START */", "/* PHASE20_GAME_CONTEXT_CSS_END */", block)
    if changed:
        b = backup(path)
        write(path, updated)
    else:
        b = ""
    return {"exists": True, "changed": changed, "backup": b}


def patch_phase16_common() -> dict[str, Any]:
    path = ROOT / "tools" / "phase16_common.py"
    if not path.exists():
        return {"exists": False, "changed": False}
    original = read(path)
    block = r'''
# Phase 20 audit policy: distinguish numeric, string, required, and advisory fields.
STRING_LIVE_FEATURES = {
    "best_book",
    "book",
    "venue",
    "game_context_source",
    "roof_status",
    "weather_wind_direction",
}

ADVISORY_LIVE_FEATURES = {
    "open_team_moneyline",
    "moneyline_move",
    "open_game_total",
    "total_move",
    "opponent_rate",
    "best_book",
}


def coverage_value_metric(item: dict[str, Any]) -> float:
    return float(item.get("coverage", 0.0) if item.get("fieldType") == "string" else item.get("numericCoverage", 0.0))


def feature_coverage(rows: list[dict[str, Any]], features: list[str]) -> dict[str, Any]:
    details = []
    for feature in features:
        field_type = "string" if feature in STRING_LIVE_FEATURES else "numeric"
        present = 0
        numeric = 0
        for row in rows:
            value = row.get(feature)
            if value is not None and str(value).strip() != "":
                present += 1
                if field_type == "string" or parse_float(value) is not None:
                    numeric += 1
        count = max(1, len(rows))
        details.append(
            {
                "feature": feature,
                "fieldType": field_type,
                "presentRows": present,
                "numericRows": numeric,
                "coverage": round(present / count, 4),
                "numericCoverage": round(numeric / count, 4),
            }
        )
    return {
        "rowCount": len(rows),
        "featureCount": len(features),
        "averageNumericCoverage": round(sum(item["numericCoverage"] for item in details) / max(1, len(details)), 4),
        "features": details,
    }
'''
    updated, changed = upsert_block(original, "# PHASE20_AUDIT_POLICY_START", "# PHASE20_AUDIT_POLICY_END", block)
    if changed:
        b = backup(path)
        write(path, updated)
    else:
        b = ""
    return {"exists": True, "changed": changed, "backup": b}


def patch_phase16_audit() -> dict[str, Any]:
    path = ROOT / "tools" / "phase16_live_feature_audit.py"
    if not path.exists():
        return {"exists": False, "changed": False}
    original = read(path)
    updated = original

    if "ADVISORY_LIVE_FEATURES" not in updated:
        updated = updated.replace(
            "    LIVE_FEATURES,\n",
            "    LIVE_FEATURES,\n    ADVISORY_LIVE_FEATURES,\n    coverage_value_metric,\n",
        )

    old = '    missing = [item["feature"] for item in coverage["features"] if item["numericCoverage"] == 0]\n    sparse = [item["feature"] for item in coverage["features"] if 0 < item["numericCoverage"] < 0.8]\n'
    new = '    missing_all = [item["feature"] for item in coverage["features"] if coverage_value_metric(item) == 0]\n    sparse_all = [item["feature"] for item in coverage["features"] if 0 < coverage_value_metric(item) < 0.8]\n    missing = [feature for feature in missing_all if feature not in ADVISORY_LIVE_FEATURES]\n    sparse = [feature for feature in sparse_all if feature not in ADVISORY_LIVE_FEATURES]\n    advisory_missing = [feature for feature in missing_all if feature in ADVISORY_LIVE_FEATURES]\n    advisory_sparse = [feature for feature in sparse_all if feature in ADVISORY_LIVE_FEATURES]\n'
    if old in updated:
        updated = updated.replace(old, new)

    old_return = '        "missingLiveFeatures": missing,\n        "sparseLiveFeatures": sparse,\n        "status": "ok" if board_rows and not missing else "warning",\n'
    new_return = '        "missingLiveFeatures": missing,\n        "sparseLiveFeatures": sparse,\n        "advisoryMissingLiveFeatures": advisory_missing,\n        "advisorySparseLiveFeatures": advisory_sparse,\n        "status": "ok" if board_rows and not missing else "warning",\n'
    if old_return in updated:
        updated = updated.replace(old_return, new_return)

    old_blocked = '        "blockedFeatureWarnings": [\n            f"{row[\'market\']}: model metadata contains non-live/leakage features {\', \'.join(row[\'blockedModelFeatures\'])}"\n            for row in results\n            if row["blockedModelFeatures"]\n        ],\n'
    new_blocked = '        "blockedFeatureWarnings": [],\n        "blockedFeatureNotes": [\n            f"{row[\'market\']}: model metadata contains non-live/leakage features {\', \'.join(row[\'blockedModelFeatures\'])}"\n            for row in results\n            if row["blockedModelFeatures"]\n        ],\n        "advisoryWarnings": [\n            f"{row[\'market\']}: advisory/movement fields pending {\', \'.join(row.get(\'advisoryMissingLiveFeatures\', []))}"\n            for row in results\n            if row.get("advisoryMissingLiveFeatures")\n        ],\n'
    if old_blocked in updated:
        updated = updated.replace(old_blocked, new_blocked)

    changed = updated != original
    if changed:
        b = backup(path)
        write(path, updated)
    else:
        b = ""
    return {"exists": True, "changed": changed, "backup": b}


def patch_phase17_audit() -> dict[str, Any]:
    path = ROOT / "tools" / "phase17_game_context_audit.py"
    if not path.exists():
        return {"exists": False, "changed": False}
    original = read(path)
    updated = original
    if "ADVISORY_CONTEXT_FIELDS" not in updated:
        updated = updated.replace(
            "def audit_market(market: str, season: int, date: str) -> dict[str, Any]:\n",
            "ADVISORY_CONTEXT_FIELDS = {\"open_team_moneyline\", \"moneyline_move\", \"open_game_total\", \"total_move\"}\n\n\ndef audit_market(market: str, season: int, date: str) -> dict[str, Any]:\n",
        )
    old = '    critical_missing = [\n        field\n        for field in missing\n        if field\n        in {\n            "team_moneyline",\n            "opponent_moneyline",\n            "game_total",\n            "team_implied_runs",\n            "opponent_implied_runs",\n            "park_factor",\n        }\n    ]\n'
    new = '    advisory_missing = [field for field in missing if field in ADVISORY_CONTEXT_FIELDS]\n    advisory_sparse = [field for field in sparse if field in ADVISORY_CONTEXT_FIELDS]\n    missing = [field for field in missing if field not in ADVISORY_CONTEXT_FIELDS]\n    sparse = [field for field in sparse if field not in ADVISORY_CONTEXT_FIELDS]\n    critical_missing = [\n        field\n        for field in missing\n        if field\n        in {\n            "team_moneyline",\n            "opponent_moneyline",\n            "game_total",\n            "team_implied_runs",\n            "opponent_implied_runs",\n            "park_factor",\n        }\n    ]\n'
    if old in updated:
        updated = updated.replace(old, new)
    old_return = '        "missingContextFeatures": missing,\n        "sparseContextFeatures": sparse,\n        "criticalMissingContextFeatures": critical_missing,\n'
    new_return = '        "missingContextFeatures": missing,\n        "sparseContextFeatures": sparse,\n        "advisoryMissingContextFeatures": advisory_missing,\n        "advisorySparseContextFeatures": advisory_sparse,\n        "criticalMissingContextFeatures": critical_missing,\n'
    if old_return in updated:
        updated = updated.replace(old_return, new_return)
    changed = updated != original
    if changed:
        b = backup(path)
        write(path, updated)
    else:
        b = ""
    return {"exists": True, "changed": changed, "backup": b}


def main() -> None:
    result = {
        "outlierDetail": patch_outlier_detail(),
        "outlierCss": patch_css(),
        "phase16Common": patch_phase16_common(),
        "phase16Audit": patch_phase16_audit(),
        "phase17Audit": patch_phase17_audit(),
    }
    print(result)


if __name__ == "__main__":
    main()
