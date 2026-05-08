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
      createElement("div", { className: "ob-rail-body" }, [createElement("p", { className: "ob-pick-copy", text: "Click any board row to inspect matchup, hit-rate profile, model probability, implied price, and data-readiness context." })]),
    ]),
  ]);
}

function detailPanel(row) {
  const player = text(row.player || row.playerName || row.team, "MLB");
  return createElement("div", {}, [
    railTabs(),
    createElement("article", { className: "ob-rail-card" }, [
      createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: player }), createElement("span", { text: text(row.team || row.away || "MLB") })]),
      createElement("div", { className: "ob-rail-body" }, [
        createElement("p", { className: "ob-pick-title", text: propLabel(row) }),
        createElement("p", { className: "ob-pick-copy", text: matchupCopy(row) }),
        metricGrid(primaryMetrics(row)),
      ]),
    ]),
    detailState.tab === "Trends" ? trendCard(row) : null,
    detailState.tab === "Model" ? modelCard(row) : null,
    detailState.tab === "Matchup" ? trustCard(row) : null,
    bestOnBoardCard(row),
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
    ["Trust", readiness(row)],
  ];
}

function metricGrid(rows) {
  return createElement("div", { className: "ob-rail-metrics" }, rows.map(([label, value]) => createElement("div", { className: "ob-rail-metric" }, [createElement("span", { text: label }), createElement("strong", { text: value })])));
}

function trendCard(row) {
  return createElement("article", { className: "ob-rail-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "Hit-Rate Profile" }), createElement("span", { text: text(row.date || row.boardDate || "Slate") })]),
    createElement("div", { className: "ob-rail-body" }, [
      createElement("div", { className: "ob-trend-bars" }, TREND_KEYS.map(([key, label]) => trendBar(label, hitPercent(row, key)))),
    ]),
  ]);
}

function trendBar(label, pct) {
  const hasValue = Number.isFinite(pct);
  const width = hasValue ? Math.max(0, Math.min(100, pct)) : 0;
  return createElement("div", { className: "ob-trend-row" }, [
    createElement("div", { className: "ob-trend-label" }, [createElement("span", { text: label }), createElement("b", { text: hasValue ? percent(pct) : "--" })]),
    createElement("div", { className: "ob-trend-track" }, [createElement("span", { className: hasValue ? "" : "is-empty", attrs: { style: `width:${width}%` } })]),
  ]);
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

function trustCard(row) {
  return createElement("article", { className: "ob-rail-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "No silent fallback" }), createElement("span", { text: "Trust" })]),
    createElement("div", { className: "ob-rail-body" }, [
      createElement("p", { className: "ob-pick-copy", text: readinessCopy(row) }),
      missingList(row),
    ]),
  ]);
}

function bestOnBoardCard(row) {
  return createElement("article", { className: "ob-rail-card" }, [
    createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "Board Row" }), createElement("span", { text: text(row.marketFamily || row.market, "Prop") })]),
    createElement("div", { className: "ob-rail-body" }, [
      createElement("p", { className: "ob-pick-title", text: `${text(row.player || row.team, "MLB")} ${propLabel(row)}` }),
      createElement("p", { className: "ob-pick-copy", text: `${matchupCopy(row)} · ${signedPercent(row.finalEdgePercent ?? row.edge)} edge` }),
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
