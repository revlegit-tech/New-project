import { createElement, replaceChildren, text, percent, signedPercent, formatOdds, propLabel, dispatch, listen, number } from "/outlier-shared.js";

const detailState = { mounted: false, row: null, tab: "Matchup" };
const TREND_KEYS = [["l5", "L5"], ["l10", "L10"], ["l20", "L20"], ["h2h", "H2H"], ["season", "2026"], ["prevSeason", "2025"]];

export async function mount() {
  if (detailState.mounted) return;
  detailState.mounted = true;
  listen("outlier:open-detail", (event) => {
    detailState.row = event.detail?.row || null;
    detailState.tab = "Matchup";
    renderDetail(detailState.row);
    dispatch("outlier:rail-open", {});
  });
  listen("outlier:rail-close", () => {
    detailState.row = null;
    renderDetail(null);
  });
  document.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-rail-tab]");
    if (!tab) return;
    detailState.tab = tab.dataset.railTab || "Matchup";
    renderDetail(detailState.row);
  });
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
      createElement("div", { className: "ob-rail-body" }, [createElement("p", { className: "ob-pick-copy", text: "Click any board row to inspect matchup, sportsbook ladder, hit-rate graph, model probability, implied price, and data-readiness context." })]),
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
    ["Model", percent(row.finalProbabilityPercent ?? row.modelProbability ?? row.probability)],
    ["Implied", percent(row.sportsbookImpliedPercent ?? row.impliedProbability ?? row.ip)],
    ["Edge", signedPercent(row.finalEdgePercent ?? row.edge)],
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
    return createElement("span", { className: Number.isFinite(pct) ? "" : "is-empty" }, [createElement("b", { text: label }), createElement("em", { text: Number.isFinite(pct) ? percent(pct) : "--" })]);
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
    createElement("div", { className: "ob-trend-label" }, [createElement("span", { text: label }), createElement("b", { text: hasValue ? percent(pct) : "--" }), createElement("em", { text: sample || "" })]),
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
        ["Final", percent(row.finalProbabilityPercent ?? row.modelProbability)],
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

function booksCard(row) {
  const books = Array.isArray(row.books) ? row.books.slice(0, 7) : [];
  if (!books.length) return null;
  return createElement("article", { className: "ob-rail-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "Sportsbook Ladder" }), createElement("span", { text: `Best of ${books.length}` })]),
    createElement("div", { className: "ob-rail-book-list" }, books.map((book, index) => createElement("div", { className: index === 0 ? "is-best" : "" }, [
      createElement("span", { text: text(book.book || book.sportsbook, "Book") }),
      createElement("strong", { text: formatOdds(book.americanOdds || book.odds || book.price) }),
      createElement("em", { text: percent(book.impliedProbabilityPercent || book.ip) }),
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
  if (value === null || value === undefined || value === "") return NaN;
  if (typeof value === "object") return normalizePercent(value.pct ?? value.percent ?? value.rate ?? value.value);
  return normalizePercent(value);
}

function sampleText(row, key) {
  const value = hitWindow(row, key);
  if (!value || typeof value !== "object") return "";
  if (value.hits === undefined || value.total === undefined) return "";
  return `${value.hits}/${value.total}`;
}

function normalizePercent(value) {
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

export const __testHooks = { detailState, renderDetail, hitPercent };
