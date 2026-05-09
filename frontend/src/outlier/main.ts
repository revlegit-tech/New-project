import "../shared/styles/tokens.css";
import "../shared/styles/layout.css";
import { jsonFetch } from "../shared/api/client";
import { MARKET_SELECT_OPTIONS, MARKETS } from "../shared/markets/markets";
import { number, text, todayIso } from "../shared/formatting";
import { h, clear } from "../shared/components/dom";
import { createInitialOutlierState } from "./app/state";
import { registerKeyboardShortcuts } from "./app/keyboard";
import { renderBoardTable } from "./board";
import { edgeValue, OutlierBoardRow, rowMarketKey, rowPlayer } from "./board/utils";
import { DetailRailController, renderDetailRailShell } from "./detail-rail";
import { freshnessSeverity } from "./trust";

const appState = createInitialOutlierState();
const disabledSports = ["NBA", "NHL", "Soccer", "WNBA", "NCAAFB"];
const SAVE_PICK_LABEL = "Add research pick";
let detailRail: DetailRailController;
let lastBoardSource = "EdgeBoard";

const detailContext = () => ({
  date: appState.date,
  status: appState.status,
  exposure: appState.exposure,
  requestId: appState.requestId,
  savePickLabel: SAVE_PICK_LABEL,
});

document.addEventListener("DOMContentLoaded", () => {
  void boot();
});

async function boot() {
  document.body.classList.add("outlier-production");
  renderShell();
  bindEvents();
  await Promise.allSettled([loadStatus(), loadExposure()]);
  await loadBoard();
}

function renderShell() {
  const root = h("section", { id: "outlierApp", className: "outlier-app" }, [renderSidebar(), renderMain(), renderDetailRailShell()]);
  clear(document.body, [root]);
  detailRail = new DetailRailController(() => document.getElementById("detailRail"));
}

function renderSidebar() {
  return h("aside", { className: "ob-sidebar", attrs: { "aria-label": "Outlier navigation" } }, [
    h("div", { className: "ob-brand" }, [h("div", { className: "ob-mark", attrs: { "aria-hidden": "true" } }), h("div", {}, [h("strong", { text: "Baseball Edge" }), h("span", { text: "MLB research terminal" })])]),
    h("nav", {}, [
      h("button", { className: "ob-nav-button is-active", type: "button", text: "Outlier Board", dataset: { nav: "board" } }),
      h("button", { className: "ob-nav-button", type: "button", text: "My Picks", dataset: { action: "focus-picks" } }),
      h("button", { className: "ob-nav-button", type: "button", text: "Model Room", dataset: { action: "focus-trust" } }),
      ...disabledSports.map((sport) => h("button", { className: "ob-nav-button is-disabled", type: "button", attrs: { disabled: "true", title: `${sport} support is not connected to production data yet.` } }, [document.createTextNode(sport), h("span", { className: "ob-coming", text: "Coming soon" })])),
    ]),
    h("div", { className: "ob-sidebar-card" }, [h("span", { text: "Positive edges" }), h("strong", { id: "positiveEdgeCount", text: "0" }), h("span", { id: "exposureSummary", text: "0.00u active exposure" })]),
  ]);
}

function renderMain() {
  return h("main", { className: "ob-main" }, [
    h("header", { className: "ob-hero" }, [
      h("div", { className: "ob-topbar" }, [
        h("div", {}, [h("p", { className: "ob-kicker", text: "Outlier production UI" }), h("h1", { text: "MLB betting research board" }), h("p", { className: "ob-subtitle", text: "Freshness, model readiness, and exposure are visible before any prop is researched or saved." })]),
        h("button", { className: "ob-button is-primary", type: "button", text: "Reload slate", dataset: { action: "reload" } }),
      ]),
      h("section", { id: "freshnessSurface", className: "ob-trust-grid", attrs: { "aria-label": "Board freshness and trust state", "aria-live": "polite" } }, [trustSkeleton("Collector"), trustSkeleton("Playerboard"), trustSkeleton("Odds"), trustSkeleton("Models"), trustSkeleton("Schema")]),
      renderFilters(),
    ]),
    h("section", { className: "ob-panel" }, [h("div", { id: "boardMeta", className: "ob-board-meta", text: "Loading board…" }), h("div", { id: "boardHost", className: "ob-table-wrap" })]),
  ]);
}

function renderFilters() {
  const market = h("select", { id: "marketFilter", className: "ob-select", attrs: { "aria-label": "Market filter" } });
  MARKET_SELECT_OPTIONS.forEach((item) => {
    const node = option(item.key, item.label);
    market.append(node);
  });
  return h("div", { className: "ob-filter-grid" }, [
    market,
    h("input", { id: "playerFilter", className: "ob-input", value: "", attrs: { type: "search", placeholder: "Search player, team, opponent", "aria-label": "Search board" } }),
    h("select", { id: "sideFilter", className: "ob-select", attrs: { "aria-label": "Side filter" } }, [option("", "Over / Under"), option("over", "Over"), option("under", "Under")]),
    h("input", { id: "dateFilter", className: "ob-input", value: appState.date, attrs: { type: "date", "aria-label": "Slate date" } }),
  ]);
}

function bindEvents() {
  document.body.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const row = target.closest("[data-row-index]");
    if (row) {
      selectRow(Number(row.getAttribute("data-row-index")));
      return;
    }
    const action = target.closest("[data-action]");
    if (!action) return;
    const name = action.getAttribute("data-action");
    if (name === "reload") await loadBoard();
    if (name === "save-pick") await saveSelectedPick();
    if (name === "focus-picks") document.getElementById("detailRail")?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (name === "focus-trust") document.getElementById("freshnessSurface")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  document.body.addEventListener("input", (event) => {
    const target = event.target;
    if (target instanceof HTMLInputElement && target.id === "playerFilter") {
      appState.query = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
  });

  document.body.addEventListener("change", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;
    if (target.id === "marketFilter") {
      appState.market = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "sideFilter") {
      appState.side = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "dateFilter") {
      appState.date = target.value || todayIso();
      await loadBoard();
    }
  });

  registerKeyboardShortcuts({
    selectNext: () => moveSelection(1),
    selectPrevious: () => moveSelection(-1),
    openSelected,
    closeRail,
    focusSearch,
  });
}

async function loadStatus() {
  try {
    const { payload, requestId } = await jsonFetch<any>("/api/app/status");
    appState.status = payload;
    appState.requestId = requestId || payload?.meta?.requestId || "";
    renderTrustSurface(payload, appState.requestId);
    detailRail?.rerender(detailContext());
  } catch (error) {
    clear(document.getElementById("freshnessSurface"), [trustCard("Status", "Unavailable", error instanceof Error ? error.message : "App status could not be loaded.", "unavailable")]);
  }
}

async function loadExposure() {
  try {
    const { payload } = await jsonFetch<any>("/api/exposure/summary");
    appState.exposure = payload?.exposure || payload;
    updateExposure();
    detailRail?.rerender(detailContext());
  } catch (error) {
    appState.exposure = { totalStakeUnits: 0, warnings: [error instanceof Error ? error.message : String(error)] };
    updateExposure();
  }
}

async function loadBoard() {
  appState.loading = true;
  renderLoading();
  try {
    const params = new URLSearchParams({ limit: "5000" });
    if (appState.date) params.set("date", appState.date);
    const { payload, requestId } = await jsonFetch<any>(`/api/edge-board?${params.toString()}`);
    appState.rows = normalizeRows(payload);
    appState.requestId = requestId || payload?.meta?.requestId || appState.requestId;
    appState.selectedIndex = -1;
    lastBoardSource = payload?.source?.label || payload?.source?.path || "EdgeBoard";
    applyFilters();
    renderBoard({ resetScroll: true });
    detailRail.close();
  } catch (error) {
    clear(document.getElementById("boardHost"), [h("div", { className: "ob-empty" }, [h("strong", { text: "Board unavailable" }), h("span", { text: error instanceof Error ? error.message : "The EdgeBoard API did not return a usable payload." })])]);
    setMeta("0 props · board unavailable");
  } finally {
    appState.loading = false;
  }
}

function normalizeRows(payload: any): OutlierBoardRow[] {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.rows)) return payload.rows;
  if (Array.isArray(payload?.data?.rows)) return payload.data.rows;
  return [];
}

function applyFilters() {
  const q = appState.query.trim().toLowerCase();
  appState.filteredRows = appState.rows.filter((row: OutlierBoardRow) => {
    const marketOk = !appState.market || rowMarketKey(row) === appState.market;
    const sideText = String(row.side || row.rawLabel || "").toLowerCase();
    const sideOk = !appState.side || sideText.includes(appState.side) || (!sideText && appState.side === "over");
    const haystack = [row.player, row.playerName, row.team, row.opponent, row.marketDisplay, row.market].map((part) => String(part || "").toLowerCase()).join(" ");
    return marketOk && sideOk && (!q || haystack.includes(q));
  });
  if (appState.selectedIndex >= appState.filteredRows.length) appState.selectedIndex = -1;
}

function renderBoard(options: { resetScroll?: boolean } = {}) {
  const severity = freshnessSeverity(appState.status);
  const result = renderBoardTable({
    host: document.getElementById("boardHost"),
    rows: appState.filteredRows,
    selectedIndex: appState.selectedIndex,
    freshnessFallback: severity.label,
    resetScroll: options.resetScroll,
  });
  const windowCopy = result.rowCount > result.renderedCount ? ` · rendering rows ${result.startIndex + 1}-${result.endIndex} of ${result.rowCount}` : "";
  setMeta(`${appState.filteredRows.length}/${appState.rows.length} MLB props · ${lastBoardSource}${windowCopy}${appState.requestId ? ` · ${appState.requestId}` : ""}`);
  updatePositiveCount();
}

function selectRow(index: number) {
  if (!appState.filteredRows.length) return;
  appState.selectedIndex = Math.max(0, Math.min(index, appState.filteredRows.length - 1));
  renderBoard();
  detailRail.open(appState.filteredRows[appState.selectedIndex], appState.selectedIndex, detailContext());
}

function moveSelection(delta: number) {
  if (!appState.filteredRows.length) return;
  const start = appState.selectedIndex < 0 ? 0 : appState.selectedIndex;
  selectRow(start + delta);
}

function openSelected() {
  if (!appState.filteredRows.length) return;
  selectRow(appState.selectedIndex < 0 ? 0 : appState.selectedIndex);
}

function closeRail() {
  appState.selectedIndex = -1;
  renderBoard();
  detailRail.close();
}

function focusSearch() {
  document.getElementById("playerFilter")?.focus();
}

async function saveSelectedPick() {
  const row = detailRail.selectedRow() || appState.filteredRows[appState.selectedIndex];
  const status = document.getElementById("savePickStatus");
  if (!row || !status) return;
  status.textContent = "Saving research-only pick…";
  try {
    const body = {
      date: appState.date,
      player: rowPlayer(row),
      team: text(row.team, ""),
      opponent: text(row.opponent || row.home, ""),
      market: text(row.market || row.baseMarket, "unknown_market"),
      marketDisplay: text(row.marketDisplay || rowMarketKey(row), "Prop"),
      line: row.line ?? row.propLine ?? null,
      americanOdds: row.americanOdds ?? row.odds ?? null,
      decisionLabel: "Watchlist",
      readinessLabel: "Research only",
      suggestedStake: "Research only",
      stakeUnits: 0,
      source: "outlier-ui",
    };
    const { payload } = await jsonFetch<any>("/api/my-picks", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Baseball-Prop-Action": "1" },
      body: JSON.stringify(body),
    });
    appState.exposure = payload?.exposure || appState.exposure;
    status.textContent = `Saved ${text(payload?.pick?.player || body.player)} as 0u research pick.`;
    updateExposure();
    detailRail.rerender(detailContext());
    showToast("Pick saved", "Research-only pick saved with 0.00u exposure.");
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "Save failed.";
  }
}

function renderTrustSurface(payload: any, requestId: string) {
  const severity = freshnessSeverity(payload);
  const boardDate = text(payload?.latestBoardDate || payload?.playerboard?.latestAvailableDate || payload?.date, "Unavailable");
  const schemaVersion = text(payload?.playerboard?.schemaVersion || payload?.schemaVersion || payload?.contracts?.playerboard || "playerboard.v3", "Unknown");
  const marketsReady = Array.isArray(payload?.productionEligibleMarkets) ? payload.productionEligibleMarkets.length : MARKETS.filter((market) => market.modelReady).length;
  clear(document.getElementById("freshnessSurface"), [
    trustCard("Last collector run", text(payload?.workflows?.lastCompletedAt || payload?.collector?.finishedAt || boardDate), severity.label, severity.tone),
    trustCard("Playerboard data", boardDate, text(payload?.dataConfidence || payload?.playerboard?.dataConfidence, "Missing"), severity.tone),
    trustCard("Odds freshness", text(payload?.odds?.latestSnapshotAt || payload?.oddsFreshness || boardDate), severity.copy, severity.tone),
    trustCard("Model readiness", `${marketsReady} MLB markets`, text(payload?.productStateDetail?.label || payload?.productState, "Research Mode"), marketsReady ? "fresh" : "aging"),
    trustCard("Schema version", schemaVersion, requestId ? `Request ${requestId}` : "Contract checked", "fresh"),
  ]);
}

function trustSkeleton(label: string) { return trustCard(label, "Checking", "Loading trust signal…", "aging"); }
function trustCard(label: string, value: unknown, copy: unknown, tone: string) { return h("article", { className: `ob-trust-card is-${tone}` }, [h("span", { text: label }), h("strong", { text: value }), h("em", { text: copy })]); }
function renderLoading() { clear(document.getElementById("boardHost"), [h("div", { className: "ob-empty" }, [h("strong", { text: "Loading board" }), h("span", { text: "Fetching EdgeBoard rows and trust metadata." })])]); }
function option(value: string, label: string) { const node = h("option", { text: label }); node.value = value; return node; }
function setMeta(copy: string) { const meta = document.getElementById("boardMeta"); if (meta) meta.textContent = copy; }
function exposureCopy() { const units = number(appState.exposure?.totalStakeUnits, 0).toFixed(2); return `0u research pick saved. ${units}u active exposure. Research-only picks stay at 0u.`; }
function updateExposure() { const target = document.getElementById("exposureSummary"); if (target) target.textContent = exposureCopy(); }
function updatePositiveCount() { const total = appState.filteredRows.filter((row: OutlierBoardRow) => edgeValue(row) > 0).length; const target = document.getElementById("positiveEdgeCount"); if (target) target.textContent = String(total); }
function showToast(title: string, copy: string) { const toast = h("div", { className: "ob-toast", attrs: { role: "status" } }, [h("strong", { text: title }), h("span", { text: copy })]); document.body.append(toast); setTimeout(() => toast.remove(), 3200); }
