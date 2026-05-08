import { createElement, replaceChildren, text, percent, signedPercent, formatOdds, propLabel, dispatch, listen } from "/outlier-shared.js";

const detailState = { mounted: false, row: null };

export async function mount() {
  if (detailState.mounted) return;
  detailState.mounted = true;
  listen("outlier:open-detail", (event) => {
    detailState.row = event.detail?.row || null;
    renderDetail(detailState.row);
    dispatch("outlier:rail-open", {});
  });
  listen("outlier:rail-close", () => {
    detailState.row = null;
    renderDetail(null);
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
      createElement("div", { className: "ob-rail-body" }, [createElement("p", { className: "ob-pick-copy", text: "Click any board row to inspect matchup, model probability, implied price, and data-readiness context." })]),
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
        metricGrid([["Model", percent(row.finalProbabilityPercent || row.modelProbability || row.probability)], ["Implied", percent(row.sportsbookImpliedPercent || row.impliedProbability)], ["Edge", signedPercent(row.finalEdgePercent || row.edge)], ["Odds", formatOdds(row.americanOdds || row.odds)], ["Line", text(row.line || row.propLine)], ["Trust", readiness(row)]]),
      ]),
    ]),
    createElement("article", { className: "ob-rail-card" }, [
      createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: "No silent fallback" }), createElement("span", { text: "Trust" })]),
      createElement("div", { className: "ob-rail-body" }, [createElement("p", { className: "ob-pick-copy", text: readinessCopy(row) })]),
    ]),
  ]);
}

function railTabs() {
  return createElement("div", { className: "ob-rail-tabs" }, [createElement("button", { className: "is-active", type: "button", text: "Matchup" }), createElement("button", { type: "button", text: "Trends" }), createElement("button", { type: "button", text: "Model" })]);
}

function metricGrid(rows) {
  return createElement("div", { className: "ob-rail-metrics" }, rows.map(([label, value]) => createElement("div", { className: "ob-rail-metric" }, [createElement("span", { text: label }), createElement("strong", { text: value })])));
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
    return `Missing Data: ${row.missingData.map((item) => text(item, "")).filter(Boolean).join(", ")}`;
  }
  return "Model and data-readiness values are shown explicitly. Missing readiness should be treated as Research Only, not as a generic fallback.";
}

export const __testHooks = { detailState, renderDetail };
