#!/usr/bin/env python3
"""Patch Outlier rail UI to show Game Context as a distinct section.

This script is intentionally conservative. It inserts one call to gameContextCard(row)
and appends helper functions only if they are not already present.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "public" / "outlier-detail.js"

CALL = "    gameContextCard(row),\n"
FUNCTION = r'''

function gameContextCard(row) {
  const markers = gameContextMarkers(row);
  const source = text(row.gameContextSource || row.game_context_source || row.gameLineSource || row.game_line_source, "Context");
  return createElement("article", { className: "ob-rail-card ob-game-context-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "Game Context" }), createElement("span", { text: source })]),
    createElement("div", { className: "ob-rail-body" }, [
      metricGrid([
        ["Team ML", formatOdds(row.teamMoneyline ?? row.team_moneyline)],
        ["Opp ML", formatOdds(row.opponentMoneyline ?? row.opponent_moneyline)],
        ["Game Total", text(row.gameTotal ?? row.game_total, "Missing")],
        ["ML IP", percent(row.moneylineImpliedProbability ?? row.moneyline_implied_probability)],
        ["Team Runs", text(row.teamImpliedRuns ?? row.team_implied_runs, "Missing")],
        ["Opp Runs", text(row.opponentImpliedRuns ?? row.opponent_implied_runs, "Missing")],
        ["Park", text(row.parkFactor ?? row.park_factor, "Missing")],
        ["Weather", weatherSummary(row)],
      ]),
      createElement("div", { className: "ob-context-markers" }, markers.map((marker) => createElement("span", { className: marker.ready ? "is-ready" : "is-missing", text: marker.label }))),
      contextMissingList(row),
    ]),
  ]);
}

function gameContextMarkers(row) {
  const explicit = text(row.gameContextMarkets || row.game_context_markets, "");
  if (explicit) {
    return explicit.split(";").map((part) => {
      const pieces = part.split(":");
      const key = text(pieces[0], "Context").replace(/_/g, " ");
      const value = text(pieces[1], "missing");
      return { label: `${key}: ${value}`, ready: value === "ready" };
    });
  }
  return [
    { label: "moneyline", ready: Boolean(row.teamMoneyline || row.team_moneyline) && Boolean(row.opponentMoneyline || row.opponent_moneyline) },
    { label: "game total", ready: Boolean(row.gameTotal || row.game_total) },
    { label: "implied runs", ready: Boolean(row.teamImpliedRuns || row.team_implied_runs) && Boolean(row.opponentImpliedRuns || row.opponent_implied_runs) },
  ];
}

function contextMissingList(row) {
  const raw = text(row.gameContextMissing || row.game_context_missing, "");
  const missing = raw.split("|").map((item) => item.trim()).filter(Boolean);
  if (!missing.length) return createElement("p", { className: "ob-pick-copy", text: "Game context markets are available for this row." });
  return createElement("ul", { className: "ob-missing-list" }, missing.map((item) => createElement("li", { text: item.replace(/_/g, " ") })));
}

function weatherSummary(row) {
  const temp = row.weatherTemperatureF ?? row.weather_temperature_f;
  const wind = row.weatherWindMph ?? row.weather_wind_mph;
  if (temp && wind) return `${temp}°F · ${wind} mph`;
  if (temp) return `${temp}°F`;
  if (wind) return `${wind} mph wind`;
  return "Missing";
}
'''

CSS = r'''

.ob-context-markers { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.ob-context-markers span { border: 1px solid rgba(255,255,255,.14); border-radius: 999px; padding: 5px 8px; font-size: 11px; letter-spacing: .02em; text-transform: uppercase; }
.ob-context-markers .is-ready { background: rgba(83, 255, 184, .09); color: #a7ffd8; }
.ob-context-markers .is-missing { background: rgba(255, 185, 83, .08); color: #ffd59b; }
'''


def patch_js() -> bool:
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)
    text_content = TARGET.read_text(encoding="utf-8")
    changed = False
    if "gameContextCard(row)" not in text_content:
        needle = "    detailState.tab === \"Matchup\" ? matchupCard(row) : null,\n"
        if needle in text_content:
            text_content = text_content.replace(needle, needle + CALL, 1)
            changed = True
    if "function gameContextCard(row)" not in text_content:
        marker = "function booksCard(row)"
        if marker in text_content:
            text_content = text_content.replace(marker, FUNCTION + "\n" + marker, 1)
            changed = True
    if changed:
        TARGET.write_text(text_content, encoding="utf-8")
    return changed


def patch_css() -> bool:
    css_path = ROOT / "public" / "outlier-ui.css"
    if not css_path.exists():
        return False
    content = css_path.read_text(encoding="utf-8")
    if ".ob-context-markers" in content:
        return False
    css_path.write_text(content.rstrip() + CSS + "\n", encoding="utf-8")
    return True


def main() -> None:
    js_changed = patch_js()
    css_changed = patch_css()
    print({"status": "ok", "jsChanged": js_changed, "cssChanged": css_changed})


if __name__ == "__main__":
    main()
