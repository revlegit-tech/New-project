import { createElement, jsonFetch, replaceChildren, text, renderStatePanel, listen, signedPercent } from "/outlier-shared.js";

let mounted = false;

export async function mount() {
  if (mounted) return;
  mounted = true;
  listen("outlier:view", (event) => {
    if (event.detail.module === "model-room") renderModelRoom(event.detail || {});
  });
}

async function renderModelRoom(detail = {}) {
  const host = document.getElementById("outlierWorkspace");
  if (!host) return;
  const nav = detail.nav || detail.state?.nav || "Insights";
  replaceChildren(host, [renderStatePanel("Loading insights", "Fetching model-card and data-health contracts.", "partial")]);
  try {
    const [models, health, board] = await Promise.allSettled([
      jsonFetch("/api/model-cards"),
      jsonFetch("/api/data-health/dashboard"),
      jsonFetch(`/api/edge-board?date=${encodeURIComponent(detail.state?.date || today())}&limit=25`),
    ]);
    const cards = models.status === "fulfilled" ? normalizeCards(models.value.payload) : [];
    const healthPayload = health.status === "fulfilled" ? health.value.payload : null;
    const boardRows = board.status === "fulfilled" ? normalizeRows(board.value.payload) : [];
    const requestId = models.value?.requestId || health.value?.requestId || board.value?.requestId || "";
    replaceChildren(host, [nav === "Insights" ? insightsView(cards, healthPayload, boardRows, requestId) : modelRoomView(cards, healthPayload, requestId)]);
  } catch (error) {
    replaceChildren(host, [renderStatePanel("Insights unavailable", text(error?.message, "Model readiness is unavailable."), "bad")]);
  }
}

function insightsView(cards, healthPayload, rows, requestId) {
  const positive = rows.filter((row) => Number(row.finalEdgePercent || row.edge || 0) > 0);
  const avgEdge = rows.length ? rows.reduce((sum, row) => sum + Number(row.finalEdgePercent || row.edge || 0), 0) / rows.length : 0;
  return createElement("section", { className: "ob-insights-module" }, [
    createElement("div", { className: "ob-insights-hero" }, [
      createElement("div", {}, [
        createElement("p", { className: "ob-kicker", text: "Insights" }),
        createElement("h1", { text: "Slate intelligence" }),
        createElement("p", { text: "Research-first readout of edge availability, model readiness, and data-health blockers." }),
      ]),
      createElement("span", { className: "ob-board-meta-inline", text: requestId || "contracts checked" }),
    ]),
    createElement("div", { className: "ob-insight-metrics" }, [
      metricCard("Props loaded", rows.length, "EdgeBoard rows available to the high-density board."),
      metricCard("Positive edges", positive.length, "Rows above market-implied price."),
      metricCard("Avg edge", signedPercent(avgEdge), "Mean edge across the current preview."),
      metricCard("Trust", healthStatus(healthPayload), "Data health and grading state."),
    ]),
    createElement("div", { className: "ob-insights-grid" }, [
      topPropsCard(rows),
      healthCard(healthPayload),
      readinessCard(cards),
    ]),
  ]);
}

function modelRoomView(cards, healthPayload, requestId) {
  return createElement("section", { className: "ob-model-room" }, [
    createElement("div", { className: "ob-section-heading" }, [
      createElement("div", {}, [createElement("p", { className: "ob-kicker", text: "Model Room" }), createElement("h2", { text: "Readiness & grading" })]),
      createElement("span", { className: "ob-board-meta-inline", text: requestId || "contract checked" }),
    ]),
    cards.length ? cardGrid(cards) : renderStatePanel("Missing model cards", "No model-card markets were returned. Keep markets research-only.", "bad"),
    healthCard(healthPayload),
  ]);
}

function normalizeRows(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.rows)) return payload.rows;
  if (Array.isArray(payload?.data?.rows)) return payload.data.rows;
  if (Array.isArray(payload?.board)) return payload.board;
  return [];
}

function normalizeCards(payload) {
  if (Array.isArray(payload?.markets)) return payload.markets;
  if (Array.isArray(payload?.modelCards)) return payload.modelCards;
  if (Array.isArray(payload?.cards)) return payload.cards;
  return [];
}

function metricCard(label, value, copy) {
  return createElement("article", { className: "ob-insight-metric" }, [
    createElement("span", { text: label }),
    createElement("strong", { text: text(value) }),
    createElement("p", { text: copy }),
  ]);
}

function topPropsCard(rows) {
  const sorted = [...rows].sort((a, b) => Number(b.finalEdgePercent || b.edge || 0) - Number(a.finalEdgePercent || a.edge || 0)).slice(0, 6);
  return createElement("article", { className: "ob-insight-card" }, [
    cardHeader("Best on board", `${sorted.length} props`),
    sorted.length ? createElement("div", { className: "ob-list-stack" }, sorted.map((row) => createElement("div", { className: "ob-list-row" }, [
      createElement("strong", { text: text(row.player || row.team, "MLB") }),
      createElement("span", { text: `${text(row.marketDisplay || row.market)} · ${signedPercent(row.finalEdgePercent || row.edge)}` }),
    ]))) : createElement("p", { className: "ob-pick-copy", text: "No board rows are available yet." }),
  ]);
}

function healthCard(payload) {
  const checks = healthChecks(payload).slice(0, 8);
  return createElement("article", { className: "ob-insight-card" }, [
    cardHeader("Data-health dashboard", healthStatus(payload)),
    createElement("p", { className: "ob-pick-copy", text: text(payload?.message || payload?.summary || payload?.overallStatus, "No silent fallback: unavailable data health blocks production confidence.") }),
    checks.length ? createElement("div", { className: "ob-health-checks" }, checks.map(checkRow)) : createElement("p", { className: "ob-pick-copy", text: "No health checks were returned." }),
  ]);
}

function readinessCard(cards) {
  const visible = cards.slice(0, 6);
  return createElement("article", { className: "ob-insight-card" }, [
    cardHeader("Model readiness", `${cards.length} markets`),
    visible.length ? createElement("div", { className: "ob-model-mini-list" }, visible.map((card) => createElement("div", { className: "ob-model-mini" }, [
      createElement("strong", { text: text(card.marketDisplay || card.market, "Market") }),
      createElement("span", { text: text(card.message || card.reason || card.status || card.state, "Research Only") }),
    ]))) : createElement("p", { className: "ob-pick-copy", text: "Missing market-specific model artifacts. Keep markets research-only." }),
  ]);
}

function cardGrid(cards) {
  return createElement("div", { className: "ob-model-grid" }, cards.map((card) => createElement("article", { className: "ob-model-card" }, [
    createElement("p", { className: "ob-kicker", text: text(card.status || card.state, "Research Only") }),
    createElement("h3", { text: text(card.marketDisplay || card.market, "Market") }),
    createElement("p", { text: text(card.message || card.reason, "Readiness details unavailable; keep this market research-only.") }),
    createElement("dl", { className: "ob-mini-dl" }, [
      pair("Backtest rows", card.backtestRows || card.backtestCount),
      pair("Eligible", card.productionEligible === true ? "Yes" : "No"),
    ]),
  ])));
}

function healthChecks(payload) {
  if (Array.isArray(payload?.checks)) return payload.checks;
  if (Array.isArray(payload?.cards)) return payload.cards;
  if (Array.isArray(payload?.sections)) return payload.sections;
  if (Array.isArray(payload?.dailyHealth?.checks)) return payload.dailyHealth.checks;
  return [];
}

function healthStatus(payload) {
  return text(payload?.overallStatus || payload?.status || payload?.state || payload?.productState, "Partial");
}

function checkRow(check) {
  const status = text(check.status || check.state || check.ok, "Partial");
  return createElement("div", { className: `ob-health-check is-${status.toLowerCase().replace(/[^a-z]+/g, "-")}` }, [
    createElement("strong", { text: text(check.label || check.key || check.name, "Health check") }),
    createElement("span", { text: status }),
    createElement("p", { text: text(check.summary || check.message || check.detail, "No detail supplied.") }),
  ]);
}

function cardHeader(title, meta) {
  return createElement("div", { className: "ob-rail-card-header" }, [createElement("h3", { text: title }), createElement("span", { text: text(meta) })]);
}

function pair(label, value) {
  return createElement("div", {}, [createElement("dt", { text: label }), createElement("dd", { text: text(value) })]);
}

function today() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

export const __testHooks = { normalizeCards, cardGrid, healthCard, insightsView };
