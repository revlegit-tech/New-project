import { createElement, replaceChildren, jsonFetch, text, todayIso, dispatch } from "/outlier-shared.js";

const NAV_ITEMS = [
  { label: "Insights", module: "model-room" },
  { label: "Popular", module: "board" },
  { label: "Games", module: "board" },
  { label: "Props", module: "board" },
  { label: "EV+", module: "board" },
  { label: "Boosts", module: "board" },
  { label: "Arbitrage", module: "board" },
  { label: "Middle Bets", module: "board" },
];

const moduleLoaders = {
  board: () => import("/outlier-board.js"),
  detail: () => import("/outlier-detail.js"),
  picks: () => import("/outlier-picks.js"),
  "model-room": () => import("/outlier-model-room.js"),
  admin: () => import("/outlier-admin.js"),
};

const loaded = new Map();
const state = {
  nav: "Props",
  activeModule: "board",
  date: todayIso(),
  status: null,
  requestId: "",
  selected: null,
  railOpen: false,
  boardStats: { total: 0, positive: 0, avgEdge: 0 },
};

export async function bootOutlierApp({ params } = {}) {
  if (params?.get("view") && params.get("view") !== "outlier") return;
  createShell();
  bindShellEvents();
  await Promise.allSettled([loadStatus(), ensureModule("detail")]);
  await activateNav("Props");
}

function createShell() {
  document.body.classList.add("outlier-mode");
  const currentMain = document.querySelector("main.app-shell") || document.querySelector("main") || document.body;
  const root = createElement("section", { id: "outlierApp", className: "outlier-app", attrs: { "data-visual": "classic-outlier" } });
  root.append(renderSidebar(), renderMain(), renderRightRailHost(), renderRailOverlay());
  currentMain.replaceWith(root);
}

function renderSidebar() {
  const sidebar = createElement("aside", { className: "ob-sidebar", attrs: { "aria-label": "Application navigation" } });
  sidebar.append(
    createElement("div", { className: "ob-brand" }, [
      createElement("div", { className: "ob-brand-lockup" }, [
        createElement("div", { className: "ob-mark", attrs: { "aria-hidden": "true" } }),
        createElement("div", {}, [
          createElement("strong", { text: "Baseball Edge" }),
          createElement("span", { text: "MLB props" }),
        ]),
      ]),
      createElement("div", { className: "ob-season-chip", text: "2026" }),
    ]),
    createElement("nav", { className: "ob-nav", attrs: { "aria-label": "Outlier sections" } }, NAV_ITEMS.map((item) => navButton(item))),
    renderSidebarFooter()
  );
  return sidebar;
}

function navButton(item) {
  return createElement("button", {
    className: item.label === state.nav ? "is-active" : "",
    type: "button",
    dataset: { nav: item.label, module: item.module },
    attrs: { "aria-label": item.label },
  }, [
    createElement("span", { className: "ob-nav-icon", attrs: { "aria-hidden": "true" } }),
    createElement("span", { text: item.label }),
  ]);
}

function renderSidebarFooter() {
  const total = Number(state.boardStats.total || 0);
  const positive = Number(state.boardStats.positive || 0);
  const avgEdge = Number(state.boardStats.avgEdge || 0);
  return createElement("div", { className: "ob-sidebar-footer" }, [
    createElement("div", { className: "ob-mini-metric" }, [
      createElement("span", { text: "Positive edges" }),
      createElement("strong", { id: "obSidebarPositive", text: String(positive) }),
      createElement("span", { id: "obSidebarAverage", text: `${total ? signed(avgEdge) : "+0.0%"} avg edge` }),
    ]),
  ]);
}

function renderMain() {
  return createElement("main", { className: "ob-main" }, [
    createElement("div", { id: "outlierTrustSurface", className: "ob-trust-strip", attrs: { "aria-live": "polite" } }),
    createElement("section", { id: "outlierWorkspace", className: "ob-workspace", attrs: { "aria-live": "polite" } }),
  ]);
}

function renderRightRailHost() {
  const rail = createElement("aside", { id: "outlierDetailHost", className: "ob-right-rail", attrs: { "aria-label": "Matchup rail" } });
  rail.append(renderRailEmpty());
  return rail;
}

function renderRailOverlay() {
  return createElement("button", {
    className: "ob-rail-overlay",
    type: "button",
    attrs: { "aria-label": "Close matchup panel" },
    dataset: { action: "closeRail" },
  });
}

function renderRailEmpty() {
  return createElement("div", {}, [
    createElement("div", { className: "ob-rail-tabs" }, [
      createElement("button", { className: "is-active", type: "button", text: "Matchup" }),
      createElement("button", { type: "button", text: "Trends" }),
      createElement("button", { type: "button", text: "Model" }),
    ]),
    createElement("article", { className: "ob-rail-card" }, [
      createElement("div", { className: "ob-rail-card-header" }, [
        createElement("h3", { text: "Select a prop" }),
        createElement("span", { text: "Research rail" }),
      ]),
      createElement("div", { className: "ob-rail-body" }, [
        createElement("p", { className: "ob-pick-copy", text: "Open a board row to inspect matchup, model, and trust-context details without leaving the high-density board." }),
      ]),
    ]),
  ]);
}

function bindShellEvents() {
  document.addEventListener("click", async (event) => {
    const action = event.target.closest("[data-action]");
    if (action?.dataset.action === "closeRail") {
      closeRail();
      return;
    }

    const nav = event.target.closest("[data-nav]");
    if (nav) {
      await activateNav(nav.dataset.nav || "Props");
    }
  });

  document.addEventListener("outlier:board-stats", (event) => {
    state.boardStats = event.detail || state.boardStats;
    updateSidebarStats();
  });

  document.addEventListener("outlier:rail-open", () => {
    state.railOpen = true;
    document.getElementById("outlierApp")?.classList.add("is-rail-open");
  });

  document.addEventListener("outlier:rail-close", closeRail);
}

async function activateNav(label) {
  const item = NAV_ITEMS.find((entry) => entry.label === label) || NAV_ITEMS.find((entry) => entry.label === "Props");
  state.nav = item.label;
  state.activeModule = item.module;
  document.querySelectorAll(".ob-nav button").forEach((node) => {
    node.classList.toggle("is-active", node.dataset.nav === state.nav);
  });
  await ensureModule(item.module);
  dispatch("outlier:view", { nav: state.nav, module: item.module, state: { ...state } });
}

async function ensureModule(name) {
  if (loaded.has(name)) return loaded.get(name);
  const loader = moduleLoaders[name];
  if (!loader) throw new Error(`Unknown Outlier module: ${name}`);
  const module = await loader();
  if (typeof module.mount === "function") {
    await module.mount({ state });
  }
  loaded.set(name, module);
  return module;
}

async function loadStatus() {
  const host = document.getElementById("outlierTrustSurface");
  if (!host) return;
  replaceChildren(host, [renderTrustSkeleton()]);
  try {
    const { payload, requestId } = await jsonFetch("/api/app/status");
    state.status = payload;
    state.requestId = requestId || payload?.meta?.requestId || "";
    replaceChildren(host, [renderTrustCompact(payload, state.requestId)]);
  } catch (error) {
    replaceChildren(host, [renderTrustFailure(error)]);
  }
}

function renderTrustSkeleton() {
  return createElement("div", { className: "ob-trust-compact is-partial" }, [
    createElement("span", { className: "ob-trust-badge", text: "Research Only" }),
    createElement("strong", { text: "Checking model readiness" }),
    createElement("span", { text: "Board remains research-only until data health is confirmed." }),
  ]);
}

function renderTrustCompact(payload, requestId) {
  const label = text(payload?.productStateDetail?.label || payload?.productState, "Research Only");
  const confidence = text(payload?.dataConfidence || payload?.playerboard?.dataConfidence, "Missing");
  const grading = text(payload?.grading?.state, "not_started");
  const boardDate = text(payload?.latestBoardDate || payload?.playerboard?.latestAvailableDate, "--");
  const markets = Array.isArray(payload?.productionEligibleMarkets) ? payload.productionEligibleMarkets.length : 0;
  return createElement("div", { className: `ob-trust-compact ${confidence.toLowerCase() === "good" ? "is-good" : "is-partial"}` }, [
    createElement("span", { className: "ob-trust-badge", text: label }),
    createElement("strong", { text: "Trust surface live" }),
    trustMetric("Date", boardDate),
    trustMetric("Confidence", confidence),
    trustMetric("Grading", grading),
    trustMetric("Markets", String(markets)),
    requestId ? trustMetric("Request", requestId) : null,
  ].filter(Boolean));
}

function trustMetric(label, value) {
  return createElement("span", { className: "ob-trust-mini" }, [
    createElement("em", { text: label }),
    createElement("b", { text: text(value) }),
  ]);
}

function renderTrustFailure(error) {
  return createElement("div", { className: "ob-trust-compact is-bad" }, [
    createElement("span", { className: "ob-trust-badge", text: "Research Only" }),
    createElement("strong", { text: "Status unavailable" }),
    createElement("span", { text: text(error?.message, "Missing app-status contract. Treat all markets as research-only.") }),
  ]);
}

function updateSidebarStats() {
  const positive = document.getElementById("obSidebarPositive");
  const avg = document.getElementById("obSidebarAverage");
  const total = Number(state.boardStats.total || 0);
  const positiveCount = Number(state.boardStats.positive || 0);
  const avgEdge = Number(state.boardStats.avgEdge || 0);
  if (positive) positive.textContent = String(positiveCount);
  if (avg) avg.textContent = `${total ? signed(avgEdge) : "+0.0%"} avg edge`;
}

function closeRail() {
  state.railOpen = false;
  document.getElementById("outlierApp")?.classList.remove("is-rail-open");
}

function signed(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "+0.0%";
  return `${parsed >= 0 ? "+" : ""}${parsed.toFixed(1)}%`;
}

export const __testHooks = { moduleLoaders, loaded, state, activateNav };
