from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

OUTLIER_DETAIL_JS = r'''import { createElement, replaceChildren, text, signedPercent, formatOdds, propLabel, dispatch, listen, number } from "/outlier-shared.js";

const detailState = { mounted: false, row: null, tab: "Matchup", index: null };
const TREND_KEYS = [["l5", "L5"], ["l10", "L10"], ["l20", "L20"], ["h2h", "H2H"], ["season", "2026"], ["prevSeason", "2025"]];

export async function mount() {
  if (detailState.mounted) return;
  detailState.mounted = true;
  listen("outlier:open-detail", (event) => {
    openRow(event.detail?.row || null, event.detail?.index ?? null);
  });
  listen("outlier:rail-close", () => {
    detailState.row = null;
    detailState.index = null;
    renderDetail(null);
  });
  document.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-rail-tab]");
    if (!tab) return;
    detailState.tab = tab.dataset.railTab || "Matchup";
    renderDetail(detailState.row);
  });
  if (window.__OUTLIER_SELECTED_ROW__?.row) {
    openRow(window.__OUTLIER_SELECTED_ROW__.row, window.__OUTLIER_SELECTED_ROW__.index ?? null);
  }
}

export function openRow(row, index = null) {
  detailState.row = row || null;
  detailState.index = index;
  detailState.tab = detailState.tab || "Matchup";
  if (row) window.__OUTLIER_SELECTED_ROW__ = { row, index };
  renderDetail(detailState.row);
  if (row) dispatch("outlier:rail-open", { row, index });
}

function renderDetail(row) {
  const host = document.getElementById("outlierDetailHost");
  if (!host) return;
  replaceChildren(host, [row ? detailPanel(row) : emptyPanel()]);
}

function emptyPanel() {
  return createElement("div", {}, [
    railTabs(),
    createElement("article", { className: "ob-rail-card" }, [
      createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "Select a prop" }), createElement("span", { text: "Research rail" })]),
      createElement("div", { className: "ob-rail-body" }, [createElement("p", { className: "ob-pick-copy", text: "Click any board row to inspect matchup, sportsbook ladder, hit-rate graph, model probability, implied price, and data-readiness context without leaving the board." })]),
    ]),
  ]);
}

function detailPanel(row) {
  const player = text(row.player || row.playerName || row.team, "MLB");
  return createElement("div", {}, [
    railTabs(),
    createElement("article", { className: "ob-rail-card ob-rail-hero-card" }, [
      createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: player }), createElement("span", { text: text(row.team || row.away || "MLB") })]),
      createElement("div", { className: "ob-rail-body" }, [
        createElement("p", { className: "ob-pick-title", text: propLabel(row) }),
        createElement("p", { className: "ob-pick-copy", text: matchupCopy(row) }),
        metricGrid(primaryMetrics(row)),
        miniHitStrip(row),
      ]),
    ]),
    detailState.tab === "Trends" ? trendCard(row) : null,
    detailState.tab === "Model" ? modelCard(row) : null,
    detailState.tab === "Matchup" ? matchupCard(row) : null,
    gameContextCard(row),
    booksCard(row),
    trustCard(row),
  ].filter(Boolean));
}

function railTabs() {
  return createElement("div", { className: "ob-rail-tabs" }, ["Matchup", "Trends", "Model"].map((name) => createElement("button", { className: detailState.tab === name ? "is-active" : "", type: "button", text: name, dataset: { railTab: name } })));
}

function primaryMetrics(row) {
  return [
    ["Model", formatPercent(row.finalProbabilityPercent ?? row.modelProbability ?? row.probability)],
    ["Implied", formatPercent(row.sportsbookImpliedPercent ?? row.impliedProbability ?? row.ip)],
    ["Edge", signedPercent(normalizePct(row.finalEdgePercent ?? row.edge))],
    ["Odds", formatOdds(row.americanOdds ?? row.odds)],
    ["Line", text(row.line ?? row.propLine)],
    ["Books", row.bookCount ? `Best of ${row.bookCount}` : text(row.book, "1")],
  ];
}

function metricGrid(rows) {
  return createElement("div", { className: "ob-rail-metrics" }, rows.map(([label, value]) => createElement("div", { className: "ob-rail-metric" }, [createElement("span", { text: label }), createElement("strong", { text: value })])));
}

function miniHitStrip(row) {
  return createElement("div", { className: "ob-rail-hit-strip" }, TREND_KEYS.slice(0, 3).map(([key, label]) => {
    const pct = hitPercent(row, key);
    return createElement("span", { className: Number.isFinite(pct) ? "" : "is-empty" }, [createElement("b", { text: label }), createElement("em", { text: Number.isFinite(pct) ? formatPercent(pct) : "--" })]);
  }));
}

function matchupCard(row) {
  return createElement("article", { className: "ob-rail-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "Matchup" }), createElement("span", { text: text(row.marketFamily || row.market, "Prop") })]),
    createElement("div", { className: "ob-rail-body" }, [
      createElement("p", { className: "ob-pick-copy", text: matchupCopy(row) }),
      metricGrid([
        ["Pitcher", text(row.pitcher || row.probablePitcher, "Starter pending")],
        ["Side", text(row.rawLabel || row.side, "Over")],
        ["Market", text(row.marketDisplay || row.market, "Market")],
        ["Trust", readiness(row)],
      ]),
    ]),
  ]);
}

function trendCard(row) {
  return createElement("article", { className: "ob-rail-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "Hit-Rate Profile" }), createElement("span", { text: text(row.date || row.boardDate || "Slate") })]),
    createElement("div", { className: "ob-rail-body" }, [
      createElement("div", { className: "ob-trend-bars" }, TREND_KEYS.map(([key, label]) => trendBar(label, hitPercent(row, key), sampleText(row, key)))),
      railGameGraph(row),
    ]),
  ]);
}

function trendBar(label, pct, sample) {
  const hasValue = Number.isFinite(pct);
  const width = hasValue ? Math.max(0, Math.min(100, pct)) : 0;
  return createElement("div", { className: "ob-trend-row" }, [
    createElement("div", { className: "ob-trend-label" }, [createElement("span", { text: label }), createElement("b", { text: hasValue ? formatPercent(pct) : "--" }), createElement("em", { text: sample || "" })]),
    createElement("div", { className: "ob-trend-track" }, [createElement("span", { className: hasValue ? "" : "is-empty", attrs: { style: `width:${width}%` } })]),
  ]);
}

function railGameGraph(row) {
  const games = Array.isArray(row.recentGames) ? row.recentGames.slice(-12) : [];
  if (!games.length) return createElement("p", { className: "ob-pick-copy", text: "Recent game graph is unavailable until game logs are cached for this market." });
  const maxValue = Math.max(1, ...games.map((game) => number(game.value, 0)));
  return createElement("div", { className: "ob-rail-game-graph" }, games.map((game) => {
    const value = number(game.value, 0);
    const height = Math.max(8, Math.min(100, (value / maxValue) * 92));
    return createElement("span", { className: game.hit ? "is-hit" : "is-miss", attrs: { title: `${text(game.date, "date")} ${text(game.opponent, "")} · ${text(game.value, "--")}` } }, [createElement("i", { attrs: { style: `height:${height}%` } }), createElement("b", { text: text(game.value, "--") })]);
  }));
}

function modelCard(row) {
  const card = row.modelCard || {};
  return createElement("article", { className: "ob-rail-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "Model Context" }), createElement("span", { text: text(row.confidence || card.status, "Research") })]),
    createElement("div", { className: "ob-rail-body" }, [
      metricGrid([
        ["Final", formatPercent(row.finalProbabilityPercent ?? row.modelProbability)],
        ["Market", text(row.marketDisplay || row.market)],
        ["Backtest", text(card.backtestRows ?? card.backtestCount ?? row.backtestRows)],
        ["Eligible", card.productionEligible === true ? "Yes" : "No"],
      ]),
      createElement("p", { className: "ob-pick-copy", text: text(card.message || card.reason || row.recommendation, "Model card is unavailable for this market. Treat as Research Only.") }),
    ]),
  ]);
}

function gameContextCard(row) {
  const markers = gameContextMarkers(row);
  const source = text(row.gameContextSource || row.game_context_source || row.gameLineSource || row.game_line_source, "Context");
  return createElement("article", { className: "ob-rail-card ob-game-context-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "Game Context" }), createElement("span", { text: source })]),
    createElement("div", { className: "ob-rail-body" }, [
      metricGrid([
        ["Team ML", formatOdds(row.teamMoneyline ?? row.team_moneyline)],
        ["Opp ML", formatOdds(row.opponentMoneyline ?? row.opponent_moneyline)],
        ["Game Total", formatDecimal(row.gameTotal ?? row.game_total)],
        ["ML IP", formatPercent(row.moneylineImpliedProbability ?? row.moneyline_implied_probability)],
        ["Team Runs", formatDecimal(row.teamImpliedRuns ?? row.team_implied_runs, 2)],
        ["Opp Runs", formatDecimal(row.opponentImpliedRuns ?? row.opponent_implied_runs, 2)],
        ["Open ML", formatOdds(row.openTeamMoneyline ?? row.open_team_moneyline) || "Pending"],
        ["ML Move", movement(row.moneylineMove ?? row.moneyline_move)],
        ["Open Total", formatDecimal(row.openGameTotal ?? row.open_game_total) || "Pending"],
        ["Total Move", movement(row.totalMove ?? row.total_move)],
        ["Park", formatDecimal(row.parkFactor ?? row.park_factor, 2)],
        ["Weather", weatherSummary(row)],
        ["Roof", titleCase(row.roofStatus ?? row.roof_status)],
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
    { label: "moneyline", ready: hasValue(row.teamMoneyline ?? row.team_moneyline) && hasValue(row.opponentMoneyline ?? row.opponent_moneyline) },
    { label: "game total", ready: hasValue(row.gameTotal ?? row.game_total) },
    { label: "implied runs", ready: hasValue(row.teamImpliedRuns ?? row.team_implied_runs) && hasValue(row.opponentImpliedRuns ?? row.opponent_implied_runs) },
  ];
}

function contextMissingList(row) {
  const raw = text(row.gameContextMissing || row.game_context_missing, "");
  const missing = raw.split("|").map((item) => item.trim()).filter(Boolean);
  if (!missing.length) return createElement("p", { className: "ob-pick-copy", text: "Game context markets are available for this row." });
  return createElement("ul", { className: "ob-missing-list" }, missing.map((item) => createElement("li", { text: item.replace(/_/g, " ") })));
}

function weatherSummary(row) {
  const temp = cleanValue(row.weatherTemperatureF ?? row.weather_temperature_f);
  const wind = cleanValue(row.weatherWindMph ?? row.weather_wind_mph);
  const direction = cleanValue(row.weatherWindDirection ?? row.weather_wind_direction);
  const humidity = cleanValue(row.weatherHumidity ?? row.weather_humidity);
  const precip = cleanValue(row.weatherPrecipProbability ?? row.weather_precip_probability);
  const parts = [];
  if (temp) parts.push(`${formatDecimal(temp, 0)}°F`);
  if (wind) parts.push(`Wind ${formatDecimal(wind, 1)} mph${direction ? ` ${direction}` : ""}`);
  if (humidity) parts.push(`Humidity ${formatDecimal(humidity, 0)}%`);
  if (precip) parts.push(`${formatDecimal(precip, 0)}% precip`);
  return parts.length ? parts.join(" · ") : "Missing";
}

function booksCard(row) {
  const books = Array.isArray(row.books) ? row.books.slice(0, 7) : [];
  if (!books.length) return null;
  return createElement("article", { className: "ob-rail-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "Sportsbook Ladder" }), createElement("span", { text: `Best of ${books.length}` })]),
    createElement("div", { className: "ob-rail-book-list" }, books.map((book, index) => createElement("div", { className: index === 0 ? "is-best" : "" }, [
      createElement("span", { text: text(book.book || book.sportsbook, "Book") }),
      createElement("strong", { text: formatOdds(book.americanOdds || book.odds || book.price) }),
      createElement("em", { text: formatPercent(book.impliedProbabilityPercent || book.ip) }),
    ]))),
  ]);
}

function trustCard(row) {
  return createElement("article", { className: "ob-rail-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "Trust Surface" }), createElement("span", { text: readiness(row) })]),
    createElement("div", { className: "ob-rail-body" }, [
      createElement("p", { className: "ob-pick-copy", text: readinessCopy(row) }),
      missingList(row),
    ]),
  ]);
}

function missingList(row) {
  const items = Array.isArray(row.missingData) ? row.missingData.map((item) => text(item, "")).filter(Boolean) : [];
  if (!items.length) return createElement("p", { className: "ob-pick-copy", text: "No missing data flags were attached to this row." });
  return createElement("ul", { className: "ob-missing-list" }, items.slice(0, 8).map((item) => createElement("li", { text: item })));
}

function matchupCopy(row) {
  const away = text(row.away || row.team, "");
  const home = text(row.home || row.opponent, "");
  const pitcher = text(row.pitcher || row.probablePitcher, "Starter pending");
  const matchup = away && home ? `${away} @ ${home}` : text(row.game || row.matchup, "Matchup unavailable");
  return `${matchup} · vs ${pitcher}`;
}

function readiness(row) {
  return text(row.modelCard?.status || row.readiness || row.confidence || (Array.isArray(row.missingData) && row.missingData.length ? "Research Only" : "Ready Check"));
}

function readinessCopy(row) {
  if (Array.isArray(row.missingData) && row.missingData.length) {
    return "This row has explicit Missing Data flags. It can be researched, but should not be treated as production-ready.";
  }
  return "Model and data-readiness values are shown explicitly. Missing readiness should be treated as Research Only, not as a generic fallback.";
}

function hitWindow(row, key) {
  const hitRates = row.hitRates || row.hit_rate || row.hitRate || row.hitProfile || {};
  const aliases = {
    l5: ["L5", "l5", "last5", "last_5", "last5Rate", "l5Percent", "l5_hit_rate", "hitRateL5"],
    l10: ["L10", "l10", "last10", "last_10", "last10Rate", "l10Percent", "l10_hit_rate", "hitRateL10"],
    l20: ["L20", "l20", "last20", "last_20", "last20Rate", "l20Percent", "l20_hit_rate", "hitRateL20"],
    h2h: ["H2H", "h2h", "headToHead", "bvp", "bvpRate", "h2hPercent", "h2h_hit_rate"],
    season: ["season", "2026", "currentSeason", "seasonRate", "currentSeasonPercent", "season_hit_rate", "hitRateSeason"],
    prevSeason: ["prevSeason", "2025", "previousSeason", "lastSeason", "prevSeasonPercent", "hitRatePrevSeason"],
  };
  for (const alias of aliases[key] || [key]) {
    if (hitRates && hitRates[alias] !== undefined) return hitRates[alias];
    if (row && row[alias] !== undefined) return row[alias];
  }
  return null;
}

function hitPercent(row, key) {
  const value = hitWindow(row, key);
  return normalizePct(value && typeof value === "object" ? value.pct ?? value.percent ?? value.rate ?? value.value : value);
}

function sampleText(row, key) {
  const value = hitWindow(row, key);
  if (!value || typeof value !== "object") return "";
  if (value.hits === undefined || value.total === undefined) return "";
  return `${value.hits}/${value.total}`;
}

function normalizePct(value) {
  if (value === null || value === undefined || value === "") return NaN;
  if (typeof value === "string") {
    const parsed = Number(value.replace("%", "").trim());
    if (!Number.isFinite(parsed)) return NaN;
    return parsed <= 1 && parsed >= -1 ? parsed * 100 : parsed;
  }
  const parsed = number(value, NaN);
  if (!Number.isFinite(parsed)) return NaN;
  return parsed <= 1 && parsed >= -1 ? parsed * 100 : parsed;
}

function formatPercent(value, fallback = "--") {
  const pct = normalizePct(value);
  if (!Number.isFinite(pct)) return fallback;
  const digits = Math.abs(pct) >= 10 ? 0 : 1;
  return `${pct.toFixed(digits)}%`;
}

function formatDecimal(value, digits = 1) {
  const raw = cleanValue(value);
  if (!raw) return "--";
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return raw;
  return parsed.toFixed(digits).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
}

function movement(value) {
  const raw = cleanValue(value);
  if (!raw) return "Pending";
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return raw;
  return `${parsed > 0 ? "+" : ""}${formatDecimal(parsed, 1)}`;
}

function titleCase(value) {
  const raw = cleanValue(value);
  if (!raw) return "Missing";
  return raw.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function hasValue(value) {
  return cleanValue(value) !== "";
}

function cleanValue(value) {
  return value === null || value === undefined ? "" : String(value).trim();
}

export const __testHooks = { detailState, renderDetail, hitPercent, openRow };
'''

BOARD_OPEN_ADVANCED_REPLACEMENT = r'''async function openRailRow(row, index) {
  if (!row) return;
  window.__OUTLIER_SELECTED_ROW__ = { row, index };
  try {
    const detailModule = await import("/outlier-detail.js");
    await detailModule.mount?.();
    if (detailModule.openRow) {
      detailModule.openRow(row, index);
    } else {
      dispatch("outlier:open-detail", { row, index });
      dispatch("outlier:rail-open", { row, index });
    }
  } catch (error) {
    console.error("Could not update Outlier rail", error);
    dispatch("outlier:open-detail", { row, index });
    dispatch("outlier:rail-open", { row, index });
  }
}

async function openAdvancedStats(index) {
  const row = boardState.filteredRows[index];
  if (!row) return;

  await openRailRow(row, index);

  try {
    await import("/prop-detail.js");
    const launcher = document.createElement("button");
    launcher.type = "button";
    launcher.textContent = "Advanced stats";
    launcher.style.display = "none";
    hydrateDetailDataset(launcher, row);
    document.body.appendChild(launcher);
    if (window.MlbPropDetail?.openFromButton) {
      await window.MlbPropDetail.openFromButton(launcher);
    } else {
      throw new Error("Prop detail module did not expose openFromButton");
    }
    launcher.remove();
  } catch (error) {
    console.error("Could not open advanced prop detail", error);
  } finally {
    setTimeout(() => openRailRow(row, index), 25);
    setTimeout(() => openRailRow(row, index), 200);
  }
}'''

CSS_APPEND = r'''

/* Phase 20 v3: keep rail selection visible and reduce modal dead space. */
.ob-app-rail,
#outlierDetailHost {
  min-width: 300px;
}
.ob-rail-card .ob-rail-metrics {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.ob-game-context-card .ob-rail-metrics {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.outlier-prop-detail-v2 .prop-detail-dialog {
  width: min(1180px, calc(100vw - 64px));
  max-width: 1180px;
}
.outlier-prop-detail-v2 .prop-detail-grid-v2 {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(380px, 0.92fr);
  gap: 16px;
  align-items: start;
}
.outlier-prop-detail-v2 #propDetailSportsbooks,
.outlier-prop-detail-v2 #propDetailModel,
.outlier-prop-detail-v2 #propDetailRisk {
  grid-column: 1 / -1;
}
.outlier-prop-detail-v2 .prop-detail-panel {
  min-width: 0;
}
.outlier-prop-detail-v2 .prop-detail-metric-row.compact {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
@media (max-width: 980px) {
  .outlier-prop-detail-v2 .prop-detail-dialog {
    width: calc(100vw - 24px);
  }
  .outlier-prop-detail-v2 .prop-detail-grid-v2 {
    grid-template-columns: 1fr;
  }
}
'''


def backup(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.phase20v3_backup_{stamp}")
    if path.exists():
      backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


def replace_function(source: str, function_name: str, replacement: str) -> str:
    marker = f"async function {function_name}("
    start = source.find(marker)
    if start == -1:
        raise RuntimeError(f"Could not find {function_name}")
    brace = source.find("{", start)
    if brace == -1:
        raise RuntimeError(f"Could not find body for {function_name}")
    depth = 0
    end = None
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise RuntimeError(f"Could not find end for {function_name}")
    # Include a preceding openRailRow if a previous patch already inserted it.
    prior = source.rfind("async function openRailRow(", 0, start)
    if prior != -1 and source[prior:start].strip().startswith("async function openRailRow"):
        start = prior
    return source[:start] + replacement + source[end:]


def main() -> None:
    PUBLIC.mkdir(exist_ok=True)
    detail = PUBLIC / "outlier-detail.js"
    board = PUBLIC / "outlier-board.js"
    css = PUBLIC / "outlier-ui.css"

    result = {}

    detail_backup = backup(detail)
    detail.write_text(OUTLIER_DETAIL_JS, encoding="utf-8")
    result["outlierDetailJs"] = {"changed": True, "backup": str(detail_backup)}

    if board.exists():
        board_text = board.read_text(encoding="utf-8")
        board_backup = backup(board)
        board_new = replace_function(board_text, "openAdvancedStats", BOARD_OPEN_ADVANCED_REPLACEMENT)
        board.write_text(board_new, encoding="utf-8")
        result["outlierBoardJs"] = {"changed": board_new != board_text, "backup": str(board_backup)}
    else:
        result["outlierBoardJs"] = {"changed": False, "warning": "missing public/outlier-board.js"}

    if css.exists():
        css_text = css.read_text(encoding="utf-8")
        css_backup = backup(css)
        if "Phase 20 v3: keep rail selection visible" not in css_text:
            css.write_text(css_text.rstrip() + CSS_APPEND + "\n", encoding="utf-8")
            changed = True
        else:
            changed = False
        result["outlierUiCss"] = {"changed": changed, "backup": str(css_backup)}
    else:
        css.write_text(CSS_APPEND.strip() + "\n", encoding="utf-8")
        result["outlierUiCss"] = {"changed": True, "created": True}

    print(result)


if __name__ == "__main__":
    main()
