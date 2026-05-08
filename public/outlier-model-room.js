import { createElement, jsonFetch, replaceChildren, text, renderStatePanel, listen } from "/outlier-shared.js";

let mounted = false;

export async function mount() {
  if (mounted) return;
  mounted = true;
  listen("outlier:view", (event) => {
    if (event.detail.module === "model-room") renderModelRoom(event.detail.view);
  });
}

async function renderModelRoom(view = "models") {
  const host = document.getElementById("outlierWorkspace");
  if (!host) return;
  replaceChildren(host, [renderStatePanel("Loading model room", "Fetching model-card and data-health contracts.", "partial")]);
  try {
    const [models, health] = await Promise.allSettled([jsonFetch("/api/model-cards"), jsonFetch("/api/data-health/dashboard")]);
    const cards = models.status === "fulfilled" ? normalizeCards(models.value.payload) : [];
    const healthPayload = health.status === "fulfilled" ? health.value.payload : null;
    replaceChildren(host, [
      createElement("section", { className: "ob-model-room" }, [
        createElement("div", { className: "ob-section-heading" }, [
          createElement("div", {}, [createElement("p", { className: "ob-kicker", text: view === "health" ? "Data Health" : "Model Room" }), createElement("h2", { text: "Readiness & grading" })]),
          createElement("span", { className: "ob-board-meta", text: models.value?.requestId || health.value?.requestId || "contract checked" }),
        ]),
        cards.length ? cardGrid(cards) : renderStatePanel("Missing model cards", "No model-card markets were returned. Keep markets research-only.", "bad"),
        healthSummary(healthPayload),
      ]),
    ]);
  } catch (error) {
    replaceChildren(host, [renderStatePanel("Model room unavailable", text(error?.message, "Model readiness is unavailable."), "bad")]);
  }
}

function normalizeCards(payload) {
  if (Array.isArray(payload?.markets)) return payload.markets;
  if (Array.isArray(payload?.modelCards)) return payload.modelCards;
  if (Array.isArray(payload?.cards)) return payload.cards;
  return [];
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

function healthSummary(payload) {
  const status = payload?.status || payload?.state || "unknown";
  return createElement("section", { className: "ob-health-summary" }, [
    createElement("h3", { text: "Data-health dashboard" }),
    createElement("p", { text: text(payload?.message || payload?.summary, "No silent fallback: unavailable data health blocks production confidence.") }),
    createElement("dl", { className: "ob-mini-dl" }, [
      pair("Status", status),
      pair("Latest board", payload?.latestBoardDate || payload?.playerboard?.latestAvailableDate),
      pair("Missing sources", Array.isArray(payload?.missingSources) ? payload.missingSources.length : payload?.missingCount),
    ]),
  ]);
}

function pair(label, value) {
  return createElement("div", {}, [createElement("dt", { text: label }), createElement("dd", { text: text(value) })]);
}

export const __testHooks = { normalizeCards, cardGrid, healthSummary };
