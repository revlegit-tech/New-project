import "../shared/styles/tokens.css";
import "../shared/styles/layout.css";
import { jsonFetch } from "../shared/api/client";
import { fallbackMarketGroups, MARKETS, MarketRegistryPayload, RegistryMarket, RegistryMarketGroup } from "../shared/markets/markets";
import { number, text, todayIso } from "../shared/formatting";
import { h, clear } from "../shared/components/dom";
import { applyDensity, densityRowHeight, normalizeDensity } from "./app/density";
import { createInitialOutlierState } from "./app/state";
import { registerKeyboardShortcuts } from "./app/keyboard";
import { renderBoardTable } from "./board";
import {
  edgeValue,
  OutlierBoardRow,
  rowAvailableBooks,
  rowBestBook,
  rowBestOdds,
  rowLine,
  rowMarketKey,
  rowModelProbability,
  rowPlayer,
  rowQuoteCount,
  rowSelectedBook,
  rowSelectedOdds,
} from "./board/utils";
import { DetailRailController, renderDetailRailShell } from "./detail-rail";
import { freshnessSeverity, rowIsTrustedMarket, rowTrustSummary, trustStatusLabel, uniqueTrustValues } from "./trust";
import { loadResearchReport, renderResearchReport, renderResearchReportError, renderResearchReportLoading } from "./research-report";

const appState = createInitialOutlierState();
const disabledSports = ["NBA", "NHL", "Soccer", "WNBA", "NCAAFB"];
const SAVE_PICK_LABEL = "Add research pick";
let detailRail: DetailRailController;
let lastBoardSource = "EdgeBoard";
let latestStatusExtras: { actionnetwork?: any; runtime?: any; workflow?: any; ml?: any } = {};

const detailContext = () => ({
  date: appState.date,
  status: appState.boardFreshness || appState.status,
  exposure: appState.exposure,
  requestId: appState.requestId,
  savePickLabel: SAVE_PICK_LABEL,
});

document.addEventListener("DOMContentLoaded", () => {
  void boot();
});

async function boot() {
  document.body.classList.add("outlier-production");
  applyDensity(appState.density);
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
      h("button", { className: "ob-nav-button", type: "button", text: "Daily Report", dataset: { action: "focus-report" } }),
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
        h("div", { className: "ob-action-row" }, [
          h("button", { className: "ob-button is-ghost", type: "button", text: "Generate report", dataset: { action: "reload-report" } }),
          h("button", { className: "ob-button is-primary", type: "button", text: "Reload slate", dataset: { action: "reload" } }),
        ]),
      ]),
      h("section", { id: "freshnessSurface", className: "ob-trust-grid", attrs: { "aria-label": "Board freshness and trust state", "aria-live": "polite" } }, [trustSkeleton("Collector"), trustSkeleton("Playerboard"), trustSkeleton("Odds"), trustSkeleton("Models"), trustSkeleton("Schema")]),
      renderFilters(),
    ]),
    h("section", { id: "researchReportPanel", className: "ob-panel ob-report-panel" }),
    h("section", { id: "marketCoveragePanel", className: "ob-panel ob-coverage-panel" }),
    h("section", { className: "ob-panel" }, [h("div", { id: "boardMeta", className: "ob-board-meta", text: "Loading board…" }), h("div", { id: "boardHost", className: "ob-table-wrap" })]),
  ]);
}

function renderFilters() {
  const market = h("select", { id: "marketFilter", className: "ob-select", attrs: { "aria-label": "Market filter" } });
  renderMarketOptions(market, null);
  const sportsbook = h("select", { id: "sportsbookFilter", className: "ob-select", attrs: { "aria-label": "Sportsbook selector" } }, [option("", "Best Available")]);
  const book = h("select", { id: "bookFilter", className: "ob-select", attrs: { "aria-label": "Book coverage filter" } }, [option("", "Any book")]);
  const marketGroup = h("select", { id: "marketGroupFilter", className: "ob-select", attrs: { "aria-label": "Market group filter" } }, [
    option("", "Any group"),
    option("batter", "Batter"),
    option("pitcher", "Pitcher"),
    option("team", "Team"),
    option("game", "Game"),
    option("first5", "First 5"),
    option("alt", "Alt / ladder"),
    option("unknown", "Unknown"),
  ]);
  const action = h("select", { id: "actionLabelFilter", className: "ob-select", attrs: { "aria-label": "Action label filter" } }, [option("", "Any action")]);
  const capability = h("select", { id: "marketCapabilityFilter", className: "ob-select", attrs: { "aria-label": "Market capability filter" } }, [option("", "Any capability")]);
  const production = h("select", { id: "productionEligibleFilter", className: "ob-select", attrs: { "aria-label": "Production eligibility filter" } }, [option("", "Any eligibility"), option("true", "Production eligible"), option("false", "Research only")]);
  const modelState = h("select", { id: "productionStatusFilter", className: "ob-select", attrs: { "aria-label": "Model state filter" } }, [option("", "Any model state")]);
  const calibration = h("select", { id: "calibrationStatusFilter", className: "ob-select", attrs: { "aria-label": "Calibration status filter" } }, [option("", "Any calibration")]);
  const backtest = h("select", { id: "backtestStatusFilter", className: "ob-select", attrs: { "aria-label": "Backtest status filter" } }, [option("", "Any backtest")]);
  const freshness = h("select", { id: "freshnessStatusFilter", className: "ob-select", attrs: { "aria-label": "Freshness status filter" } }, [option("", "Any freshness")]);
  return h("div", { className: "ob-filter-grid" }, [
    sportsbook,
    market,
    marketGroup,
    book,
    h("input", { id: "playerFilter", className: "ob-input", value: "", attrs: { type: "search", placeholder: "Search player, team, opponent", "aria-label": "Search board" } }),
    h("select", { id: "sideFilter", className: "ob-select", attrs: { "aria-label": "Side filter" } }, [option("", "Over / Under"), option("over", "Over"), option("under", "Under")]),
    h("input", { id: "minQuoteCountFilter", className: "ob-input", value: "", attrs: { type: "number", min: "0", step: "1", placeholder: "Min quotes", "aria-label": "Minimum quote count" } }),
    h("input", { id: "dateFilter", className: "ob-input", value: appState.date, attrs: { type: "date", "aria-label": "Slate date" } }),
    action,
    capability,
    production,
    modelState,
    calibration,
    backtest,
    freshness,
    h("label", { className: "ob-check" }, [h("input", { id: "missingDataOnlyFilter", attrs: { type: "checkbox" } }), h("span", { text: "Missing data only" })]),
    h("label", { className: "ob-check" }, [h("input", { id: "trustedMarketsOnlyFilter", attrs: { type: "checkbox" } }), h("span", { text: "Trusted markets only" })]),
    h("label", { className: "ob-check" }, [h("input", { id: "modeledOnlyFilter", attrs: { type: "checkbox" } }), h("span", { text: "Modeled only" })]),
    h("label", { className: "ob-check" }, [h("input", { id: "oddsOnlyFilter", attrs: { type: "checkbox" } }), h("span", { text: "Odds only" })]),
    h("label", { className: "ob-check" }, [h("input", { id: "hideOddsOnlyFilter", attrs: { type: "checkbox" } }), h("span", { text: "Hide odds-only" })]),
    h("label", { className: "ob-check" }, [h("input", { id: "showAltMarketsFilter", attrs: { type: "checkbox", checked: "checked" } }), h("span", { text: "Alt markets" })]),
    h("label", { className: "ob-check" }, [h("input", { id: "showGameMarketsFilter", attrs: { type: "checkbox" } }), h("span", { text: "Game markets" })]),
    h("label", { className: "ob-check" }, [h("input", { id: "hasSelectedBookQuoteFilter", attrs: { type: "checkbox" } }), h("span", { text: "Selected quote" })]),
    h("label", { className: "ob-check" }, [h("input", { id: "hasModelProbabilityFilter", attrs: { type: "checkbox" } }), h("span", { text: "Has model" })]),
    h("label", { className: "ob-check" }, [h("input", { id: "hasEdgeFilter", attrs: { type: "checkbox" } }), h("span", { text: "Has edge" })]),
    renderDensityToggle(),
    h("button", { className: "ob-button is-ghost", type: "button", text: "Reset filters", dataset: { action: "reset-filters" } }),
  ]);
}

function bindEvents() {
  document.body.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const density = target.closest("[data-density]");
    if (density) {
      setDensity(density.getAttribute("data-density"));
      return;
    }
    const row = target.closest("[data-row-index]");
    if (row) {
      selectRow(Number(row.getAttribute("data-row-index")));
      return;
    }
    const sort = target.closest("[data-sort]");
    if (sort) {
      setSort(sort.getAttribute("data-sort") || "");
      return;
    }
    const action = target.closest("[data-action]");
    if (!action) return;
    const name = action.getAttribute("data-action");
    if (name === "reload") await loadBoard();
    if (name === "reload-report") await loadReport();
    if (name === "reset-filters") resetFilters();
    if (name === "save-pick") await saveSelectedPick();
    if (name === "focus-report") document.getElementById("researchReportPanel")?.scrollIntoView({ behavior: "smooth", block: "start" });
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
    if (target.id === "sportsbookFilter") {
      appState.sportsbook = target.value;
      await loadBoard();
    }
    if (target.id === "bookFilter") {
      appState.bookFilter = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "marketGroupFilter") {
      appState.marketGroup = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
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
    if (target.id === "actionLabelFilter") {
      appState.actionLabel = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "marketCapabilityFilter") {
      appState.marketCapabilityStatus = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "productionEligibleFilter") {
      appState.modelProductionEligible = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "productionStatusFilter") {
      appState.productionStatus = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "calibrationStatusFilter") {
      appState.calibrationStatus = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "backtestStatusFilter") {
      appState.backtestStatus = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "freshnessStatusFilter") {
      appState.freshnessStatus = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "missingDataOnlyFilter") {
      appState.missingDataOnly = target.checked;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "trustedMarketsOnlyFilter") {
      appState.trustedMarketsOnly = target.checked;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    if (target.id === "dateFilter") {
      appState.date = target.value || todayIso();
      await loadBoard();
    }
    if (target.id === "minQuoteCountFilter") {
      appState.minQuoteCount = target.value;
      applyFilters();
      renderBoard({ resetScroll: true });
    }
    toggleFilter(target, "modeledOnlyFilter", "modeledOnly");
    toggleFilter(target, "oddsOnlyFilter", "oddsOnly");
    toggleFilter(target, "hideOddsOnlyFilter", "hideOddsOnly");
    toggleFilter(target, "showAltMarketsFilter", "showAltMarkets");
    toggleFilter(target, "showGameMarketsFilter", "showGameMarkets");
    toggleFilter(target, "hasSelectedBookQuoteFilter", "hasSelectedBookQuote");
    toggleFilter(target, "hasBestBookQuoteFilter", "hasBestBookQuote");
    toggleFilter(target, "hasModelProbabilityFilter", "hasModelProbability");
    toggleFilter(target, "hasEdgeFilter", "hasEdge");
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
    const [{ payload, requestId }, actionnetwork, runtime, workflow, ml] = await Promise.all([
      jsonFetch<any>("/api/app/status"),
      optionalJson(`/api/actionnetwork/trust?date=${encodeURIComponent(appState.date)}`),
      optionalJson("/api/runtime/status"),
      optionalJson("/api/workflow/status"),
      optionalJson("/api/ml-models/status"),
    ]);
    appState.status = payload;
    appState.requestId = requestId || payload?.meta?.requestId || "";
    latestStatusExtras = { actionnetwork, runtime, workflow, ml };
    renderTrustSurface(payload, appState.requestId, latestStatusExtras);
    detailRail?.rerender(detailContext());
  } catch (error) {
    clear(document.getElementById("freshnessSurface"), [trustCard("Status", "Unavailable", error instanceof Error ? error.message : "App status could not be loaded.", "unavailable")]);
  }
}

async function optionalJson(path: string): Promise<any> {
  try {
    const { payload } = await jsonFetch<any>(path);
    return payload;
  } catch (error) {
    return { status: "missing", ok: false, warnings: [error instanceof Error ? error.message : String(error)] };
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
    if (appState.sportsbook) params.set("selectedBook", appState.sportsbook);
    const { payload, requestId } = await jsonFetch<any>(`/api/edge-board?${params.toString()}`);
    appState.rows = normalizeRows(payload);
    appState.requestId = requestId || payload?.meta?.requestId || appState.requestId;
    appState.boardFreshness = payload?.freshness || null;
    appState.boardTrust = payload?.trust || null;
    appState.marketRegistry = payload?.marketRegistry || null;
    appState.marketCoverage = payload?.marketCoverage || payload?.marketRegistry?.marketCoverage || null;
    appState.selectedIndex = -1;
    lastBoardSource = payload?.source?.label || payload?.source?.path || "EdgeBoard";
    renderTrustSurface(payload, appState.requestId, latestStatusExtras);
    await loadMarketRegistry();
    renderMarketCoverage();
    syncTrustFilters();
    syncSportsbookFilters();
    applyFilters();
    renderBoard({ resetScroll: true });
    detailRail.close();
    void loadReport();
  } catch (error) {
    clear(document.getElementById("boardHost"), [h("div", { className: "ob-empty" }, [h("strong", { text: "Board unavailable" }), h("span", { text: error instanceof Error ? error.message : "The EdgeBoard API did not return a usable payload." })])]);
    setMeta("0 props · board unavailable");
  } finally {
    appState.loading = false;
  }
}

async function loadReport() {
  const host = document.getElementById("researchReportPanel");
  renderResearchReportLoading(host);
  try {
    const report = await loadResearchReport(appState.date);
    renderResearchReport(host, report);
  } catch (error) {
    renderResearchReportError(host, error instanceof Error ? error.message : "Research report could not be generated.");
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
  const minQuotes = Number(appState.minQuoteCount || 0);
  appState.filteredRows = appState.rows.filter((row: OutlierBoardRow) => {
    const marketOk = !appState.market || rowMarketKey(row) === appState.market;
    const marketGroupOk = !appState.marketGroup || rowMarketGroup(row) === appState.marketGroup;
    const trust = rowTrustSummary(row);
    const sideText = String(row.trust?.propIdentity?.side || row.side || row.rawLabel || "").toLowerCase();
    const sideOk = !appState.side || sideText.includes(appState.side) || (!sideText && appState.side === "over");
    const rowBooks = new Set([rowSelectedBook(row), rowBestBook(row), ...rowAvailableBooks(row)].filter(Boolean));
    const bookOk = !appState.bookFilter || rowBooks.has(appState.bookFilter);
    const selectedQuoteOk = !appState.hasSelectedBookQuote || hasSelectedBookQuote(row);
    const bestQuoteOk = !appState.hasBestBookQuote || rowBestOdds(row) !== null && rowBestOdds(row) !== undefined && rowBestOdds(row) !== "";
    const modelProbabilityOk = !appState.hasModelProbability || numericValue(rowModelProbability(row)) !== null;
    const edgeOk = !appState.hasEdge || edgeValue(row) !== null;
    const quoteCountOk = !Number.isFinite(minQuotes) || rowQuoteCount(row) >= minQuotes;
    const oddsOnly = rowIsOddsOnly(row);
    const modeledOk = !appState.modeledOnly || rowHasModel(row);
    const oddsOnlyOk = (!appState.oddsOnly || oddsOnly) && (!appState.hideOddsOnly || !oddsOnly);
    const altOk = appState.showAltMarkets || !rowIsAltMarket(row);
    const gameOk = appState.showGameMarkets || !rowIsGameMarket(row);
    const unknownOk = appState.includeUnknownMarkets || rowMarketGroup(row) !== "unknown";
    const haystack = [row.trust?.propIdentity?.player, row.player, row.playerName, row.trust?.propIdentity?.team, row.team, row.trust?.propIdentity?.opponent, row.opponent, row.marketDisplay, row.trust?.propIdentity?.market, row.market].map((part) => String(part || "").toLowerCase()).join(" ");
    const actionOk = !appState.actionLabel || normalizeFilter(trust.actionLabel) === appState.actionLabel;
    const capabilityOk = !appState.marketCapabilityStatus || trust.marketCapabilityStatus === appState.marketCapabilityStatus;
    const productionOk = !appState.modelProductionEligible || String(trust.modelProductionEligible) === appState.modelProductionEligible;
    const modelOk = !appState.productionStatus || trust.productionStatus === appState.productionStatus;
    const calibrationOk = !appState.calibrationStatus || trust.calibrationStatus === appState.calibrationStatus;
    const backtestOk = !appState.backtestStatus || trust.backtestStatus === appState.backtestStatus;
    const freshnessOk = !appState.freshnessStatus || trust.freshnessStatus === appState.freshnessStatus;
    const missingOk = !appState.missingDataOnly || trust.missingDataCount > 0;
    const trustedOk = !appState.trustedMarketsOnly || rowIsTrustedMarket(row);
    return marketOk && marketGroupOk && sideOk && bookOk && selectedQuoteOk && bestQuoteOk && modelProbabilityOk && edgeOk && quoteCountOk && modeledOk && oddsOnlyOk && altOk && gameOk && unknownOk && actionOk && capabilityOk && productionOk && modelOk && calibrationOk && backtestOk && freshnessOk && missingOk && trustedOk && (!q || haystack.includes(q));
  });
  appState.filteredRows = sortRows(appState.filteredRows);
  if (appState.selectedIndex >= appState.filteredRows.length) appState.selectedIndex = -1;
}

function renderBoard(options: { resetScroll?: boolean } = {}) {
  const severity = freshnessSeverity(appState.boardFreshness || appState.status);
  const result = renderBoardTable({
    host: document.getElementById("boardHost"),
    rows: appState.filteredRows,
    selectedIndex: appState.selectedIndex,
    freshnessFallback: severity.label,
    emptyState: appState.trustedMarketsOnly
      ? { title: "No rows are currently production eligible.", copy: "Trusted markets require production eligibility, confident-pick visibility, fresh data, supported markets, and no critical missing data." }
      : currentEmptyState(),
    rowHeight: densityRowHeight(appState.density),
    sportsbook: appState.sportsbook,
    sortBy: appState.sortBy,
    sortDir: appState.sortDir,
    resetScroll: options.resetScroll,
  });
  const windowCopy = result.rowCount > result.renderedCount ? ` · rendering rows ${result.startIndex + 1}-${result.endIndex} of ${result.rowCount}` : "";
  setMeta(boardMetaCopy(windowCopy));
  updatePositiveCount();
}

function renderMarketOptions(select: HTMLSelectElement, registry: MarketRegistryPayload | null) {
  const current = select.value;
  const groups = marketGroups(registry);
  const allCount = coverageCount(registry, "rawPropsPulled") || groups.reduce((total, group) => total + Number(group.rowCount || 0), 0);
  select.replaceChildren(option("", `All MLB markets${allCount ? ` - ${allCount}` : ""}`));
  groups.filter((group) => group.key !== "all" && Array.isArray(group.markets) && group.markets.length).forEach((group) => {
    const optgroup = document.createElement("optgroup");
    optgroup.label = group.label;
    group.markets
      .filter((market) => appState.showGameMarkets || market.category !== "game")
      .filter((market) => appState.includeUnknownMarkets || !market.badges?.some((badge) => badge.toLowerCase().includes("unknown")))
      .forEach((market) => optgroup.append(option(market.marketKey, marketOptionLabel(market))));
    select.append(optgroup);
  });
  select.value = current && Array.from(select.options).some((item) => item.value === current) ? current : "";
  appState.market = select.value;
}

function marketGroups(registry: MarketRegistryPayload | null): RegistryMarketGroup[] {
  const groups = Array.isArray(registry?.groups) ? registry!.groups : [];
  return groups.length ? groups : fallbackMarketGroups();
}

function marketOptionLabel(market: RegistryMarket): string {
  const count = Number(market.rowCount || market.quoteCount || 0);
  const badges = (market.badges || []).slice(0, 2).join(", ");
  const suffix = [count ? String(count) : "", badges].filter(Boolean).join(" - ");
  return `${market.displayName || market.marketKey}${suffix ? ` - ${suffix}` : ""}`;
}

function renderMarketCoverage() {
  const host = document.getElementById("marketCoveragePanel");
  const coverage = appState.marketCoverage || {};
  const registry = appState.marketRegistry || {};
  const markets = Array.isArray(registry.markets) ? registry.markets : [];
  const topMarkets = markets.filter((market: RegistryMarket) => Number(market.rowCount || 0) > 0).slice(0, 12);
  const modeled = markets.filter((market: RegistryMarket) => market.hasModel).length;
  const oddsOnly = markets.filter((market: RegistryMarket) => market.hasOdds && !market.hasModel).length;
  const missingModel = markets.filter((market: RegistryMarket) => market.missingModelMarket || market.modelUnavailable).length;
  clear(host, [
    h("div", { className: "ob-coverage-head" }, [
      h("div", {}, [h("strong", { text: "Market Coverage" }), h("span", { text: `${number(coverage.marketsFound, markets.length)} markets found` })]),
      h("div", { className: "ob-coverage-badges" }, [
        coverageBadge("Visible", coverage.marketsShownInDropdown?.length),
        coverageBadge("Hidden", coverage.marketsHiddenFromDropdown?.length),
        coverageBadge("Odds only", coverage.oddsOnlyMarketCount),
        coverageBadge("Missing model", coverage.missingModelMarketCount),
      ]),
    ]),
    h("div", { className: "ob-coverage-grid" }, [
      coverageStat("Modeled", modeled),
      coverageStat("Odds-only", oddsOnly || coverage.oddsOnlyMarketCount),
      coverageStat("Missing model", missingModel || coverage.missingModelMarketCount),
      coverageStat("Raw props", coverage.rawPropsPulled),
      coverageStat("Rows w/ market", coverage.marketsWithRows?.length),
      coverageStat("Alt markets", coverage.altMarketsFound?.length),
      coverageStat("Game markets", coverage.gameMarketsFound?.length),
      coverageStat("Team markets", coverage.teamMarketsFound?.length),
      coverageStat("F5 markets", coverage.firstFiveMarketsFound?.length),
      coverageStat("Moneyline rows", coverage.moneylineRowsLoaded),
      coverageStat("Run line rows", coverage.runLineRowsLoaded),
      coverageStat("Totals rows", coverage.totalsRowsLoaded),
    ]),
    h("div", { className: "ob-coverage-buckets" }, [
      coverageList("Unknown / needs mapping", coverage.unknownMarketsFound || coverage.sampleUnknownMarkets),
      coverageList("Hidden from board", coverage.marketsHiddenFromDropdown),
      coverageList("Model but no odds", coverage.marketsWithModelButNoOdds),
      coverageList("Odds but no model", coverage.marketsWithOddsButNoModel),
    ]),
    h("div", { className: "ob-coverage-list" }, topMarkets.map((market: RegistryMarket) => h("div", { className: "ob-coverage-row" }, [
      h("span", { text: market.displayName || market.marketKey }),
      h("em", { text: `${number(market.rowCount, 0)} rows / ${number(market.quoteCount, 0)} quotes` }),
      h("strong", { text: `${market.modelStatus || "unknown"}${market.availableBooks?.length ? ` / ${market.availableBooks.length} books` : ""}` }),
    ]))),
  ]);
}

function coverageBadge(label: string, value: unknown) { return h("span", { className: "ob-chip", text: `${label}: ${number(value, 0)}` }); }
function coverageStat(label: string, value: unknown) { return h("div", { className: "ob-coverage-stat" }, [h("span", { text: label }), h("strong", { text: number(value, 0) })]); }
function coverageList(label: string, values: unknown) {
  const items = Array.isArray(values) ? values.map((value) => typeof value === "string" ? value : text((value as any)?.market || (value as any)?.marketKey || JSON.stringify(value), "")).filter(Boolean).slice(0, 8) : [];
  return h("div", { className: "ob-coverage-bucket" }, [
    h("strong", { text: `${label}: ${items.length}` }),
    h("span", { text: items.length ? items.join(", ") : "None" }),
  ]);
}
function coverageCount(registry: MarketRegistryPayload | null, key: string): number {
  return Number(registry?.marketCoverage?.[key] || registry?.coverage?.[key] || 0);
}

function syncSportsbookFilters() {
  const books = availableSportsbooks();
  fillBookSelect("sportsbookFilter", books, "Best Available", appState.sportsbook);
  fillBookSelect("bookFilter", books, "Any book", appState.bookFilter);
}

function availableSportsbooks(): string[] {
  const fromRegistry = Array.isArray(appState.marketRegistry?.markets)
    ? appState.marketRegistry.markets.flatMap((market: RegistryMarket) => market.availableBooks || [])
    : [];
  const fromCoverage = Object.values(appState.marketCoverage?.booksByMarket || {}).flatMap((books: any) => Array.isArray(books) ? books : []);
  const fromRows = appState.rows.flatMap((row: OutlierBoardRow) => [rowSelectedBook(row), rowBestBook(row), ...rowAvailableBooks(row)]);
  const preferred = ["DraftKings", "FanDuel", "Bovada", "Pinnacle", "Novig", "PrizePicks", "Sleeper", "Underdog Fantasy"];
  const all = uniqueStrings([...preferred, ...fromRegistry, ...fromCoverage, ...fromRows]);
  return all.filter((book) => preferred.includes(book) || fromRegistry.includes(book) || fromCoverage.includes(book) || fromRows.includes(book));
}

function fillBookSelect(id: string, books: string[], allLabel: string, current: string) {
  const select = document.getElementById(id);
  if (!(select instanceof HTMLSelectElement)) return;
  select.replaceChildren(option("", allLabel), ...books.map((book) => option(book, book)));
  select.value = books.includes(current) ? current : "";
  if (id === "sportsbookFilter") appState.sportsbook = select.value;
  if (id === "bookFilter") appState.bookFilter = select.value;
}

function boardMetaCopy(windowCopy: string): string {
  const coverage = appState.marketCoverage || {};
  const rawProps = number(coverage.rawPropsPulled, 0);
  const uniqueProps = number(coverage.uniquePropIdentities, 0);
  const quotes = number(coverage.uniqueBookQuotes || coverage.rawBookQuotesPulled, 0);
  const selected = appState.sportsbook || "Best Available";
  const selectedCoverage = appState.sportsbook ? `${selectedBookCoverage()} selected-book quotes` : "";
  const activeMarkets = new Set(appState.filteredRows.map((row: OutlierBoardRow) => rowMarketKey(row)).filter(Boolean)).size;
  const hidden = Array.isArray(coverage.marketsHiddenFromDropdown) ? coverage.marketsHiddenFromDropdown.length : 0;
  const oddsOnly = number(coverage.oddsOnlyMarketCount, appState.rows.filter(rowIsOddsOnly).length);
  const missingModel = number(coverage.missingModelMarketCount, appState.rows.filter((row: OutlierBoardRow) => !rowHasModel(row)).length);
  const parts = [
    `Visible ${appState.filteredRows.length} of ${appState.rows.length} board rows`,
    rawProps ? `${rawProps.toLocaleString()} raw props` : "",
    uniqueProps ? `${uniqueProps.toLocaleString()} unique props` : "",
    quotes ? `${quotes.toLocaleString()} quotes` : "",
    `${activeMarkets} active markets`,
    selected,
    selectedCoverage,
    hidden ? `${hidden} hidden markets` : "",
    oddsOnly ? `${oddsOnly} odds-only markets` : "",
    missingModel ? `${missingModel} missing-model markets` : "",
    activeFilterCopy(),
    lastBoardSource,
    windowCopy.replace(/^ · /, ""),
  ].filter(Boolean);
  return parts.join(" · ");
}

function selectedBookCoverage(): string {
  if (!appState.sportsbook) return "";
  const quoted = appState.rows.filter(hasSelectedBookQuote).length;
  return `${quoted}/${appState.rows.length}`;
}

function activeFilterCopy(): string {
  const parts = [
    appState.market ? `Market: ${marketLabel(appState.market)}` : "",
    appState.marketGroup ? `Group: ${appState.marketGroup}` : "",
    appState.bookFilter ? `Book: ${appState.bookFilter}` : "",
    appState.side ? `${appState.side[0].toUpperCase()}${appState.side.slice(1)} only` : "",
    appState.query ? `Search: ${appState.query}` : "",
    appState.minQuoteCount ? `Min quotes: ${appState.minQuoteCount}` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

function uniqueStrings(values: unknown[]): string[] {
  return Array.from(new Set(values.map((value) => text(value, "")).filter(Boolean))).sort((a, b) => a.localeCompare(b));
}

function rowMarketGroup(row: OutlierBoardRow): string {
  const market = rowMarketKey(row).toLowerCase();
  const display = text(row.marketDisplay, "").toLowerCase();
  if (rowIsAltMarket(row)) return "alt";
  if (market.includes("first5") || market.includes("first_5") || market.includes("f5")) return "first5";
  if (rowIsGameMarket(row)) return "game";
  if (market.startsWith("team_")) return "team";
  if (market.startsWith("pitcher_")) return "pitcher";
  if (market.startsWith("batter_")) return "batter";
  if (display.includes("unknown") || market.includes("unknown")) return "unknown";
  return "batter";
}

function rowIsAltMarket(row: OutlierBoardRow): boolean {
  const market = rowMarketKey(row).toLowerCase();
  const display = text(row.marketDisplay, "").toLowerCase();
  return row.isAltMarket === true || String(row.isAltMarket).toLowerCase() === "true" || market.includes("_alt") || display.includes("ladder") || display.includes("milestone");
}

function rowIsGameMarket(row: OutlierBoardRow): boolean {
  const market = rowMarketKey(row).toLowerCase();
  return ["game_total_runs", "moneyline", "run_line", "team_total_runs"].includes(market) || market.startsWith("game_");
}

function rowHasModel(row: OutlierBoardRow): boolean {
  return row.predictionMatched === true || numericValue(rowModelProbability(row)) !== null;
}

function rowIsOddsOnly(row: OutlierBoardRow): boolean {
  const confidence = text(row.confidence, "").toLowerCase();
  const readiness = text(row.readinessLabel, "").toLowerCase();
  const capability = text(row.marketCapabilityStatus, "").toLowerCase();
  return confidence.includes("odds only") || readiness.includes("no model") || capability === "research_only" && !rowHasModel(row);
}

function hasSelectedBookQuote(row: OutlierBoardRow): boolean {
  const status = text(row.selectedBookQuoteStatus, "").toLowerCase();
  const odds = rowSelectedOdds(row);
  return !status.includes("no_quote") && odds !== null && odds !== undefined && odds !== "";
}

function numericValue(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(String(value).replace("%", ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function sortRows(rows: OutlierBoardRow[]): OutlierBoardRow[] {
  const sortBy = appState.sortBy;
  const dir = appState.sortDir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = sortValue(a, sortBy);
    const bv = sortValue(b, sortBy);
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * dir;
    return (av - bv) * dir;
  });
}

function sortValue(row: OutlierBoardRow, key: string): number | string | null {
  if (key === "player") return rowPlayer(row).toLowerCase();
  if (key === "market") return marketLabel(rowMarketKey(row)).toLowerCase();
  if (key === "book") return (appState.sportsbook ? rowSelectedBook(row) : rowBestBook(row)).toLowerCase();
  if (key === "readiness") return text(row.readinessLabel, "").toLowerCase();
  if (key === "freshness") return text(row.freshness?.status, "").toLowerCase();
  if (key === "action") return text(row.actionLabel || row.action, "").toLowerCase();
  if (key === "line") return numericValue(rowLine(row));
  if (key === "quoteCount") return rowQuoteCount(row);
  if (key === "americanOdds") return numericValue(appState.sportsbook ? rowSelectedOdds(row) : rowBestOdds(row));
  if (key === "modelProbabilityPercent") return rowHasModel(row) ? numericValue(rowModelProbability(row)) : null;
  if (key === "impliedProbability") return numericValue(row.impliedProbabilityPercent ?? row.impliedProbability);
  if (key === "finalProbabilityPercent") return rowHasModel(row) ? numericValue(row.finalProbabilityPercent) : null;
  if (key === "edgePercent") return rowHasModel(row) ? edgeValue(row) : null;
  return numericValue(row[key]);
}

function setSort(key: string) {
  if (!key) return;
  if (appState.sortBy === key) {
    appState.sortDir = appState.sortDir === "asc" ? "desc" : "asc";
  } else {
    appState.sortBy = key;
    appState.sortDir = key === "player" || key === "market" ? "asc" : "desc";
  }
  applyFilters();
  renderBoard({ resetScroll: true });
}

function toggleFilter(target: HTMLInputElement | HTMLSelectElement, id: string, stateKey: string) {
  if (!(target instanceof HTMLInputElement) || target.id !== id) return;
  (appState as any)[stateKey] = target.checked;
  if (id === "showGameMarketsFilter") {
    const marketSelect = document.getElementById("marketFilter");
    if (marketSelect instanceof HTMLSelectElement) renderMarketOptions(marketSelect, appState.marketRegistry);
  }
  applyFilters();
  renderBoard({ resetScroll: true });
}

function resetFilters() {
  appState.market = "";
  appState.marketGroup = "";
  appState.bookFilter = "";
  appState.query = "";
  appState.side = "";
  appState.actionLabel = "";
  appState.marketCapabilityStatus = "";
  appState.modelProductionEligible = "";
  appState.productionStatus = "";
  appState.calibrationStatus = "";
  appState.backtestStatus = "";
  appState.freshnessStatus = "";
  appState.missingDataOnly = false;
  appState.trustedMarketsOnly = false;
  appState.modeledOnly = false;
  appState.oddsOnly = false;
  appState.hideOddsOnly = false;
  appState.showAltMarkets = true;
  appState.showGameMarkets = false;
  appState.hasSelectedBookQuote = false;
  appState.hasBestBookQuote = false;
  appState.hasModelProbability = false;
  appState.hasEdge = false;
  appState.minQuoteCount = "";
  document.querySelectorAll<HTMLInputElement | HTMLSelectElement>(".ob-filter-grid input, .ob-filter-grid select").forEach((control) => {
    if (control.id === "dateFilter" || control.id === "sportsbookFilter") return;
    if (control instanceof HTMLInputElement && control.type === "checkbox") control.checked = control.id === "showAltMarketsFilter";
    else control.value = "";
  });
  applyFilters();
  renderBoard({ resetScroll: true });
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

function setDensity(value: unknown) {
  appState.density = applyDensity(normalizeDensity(value));
  updateDensityControls();
  renderBoard();
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
      team: text(row.trust?.propIdentity?.team ?? row.team, ""),
      opponent: text(row.trust?.propIdentity?.opponent ?? row.opponent ?? row.home, ""),
      market: text(row.trust?.propIdentity?.market ?? row.market ?? row.baseMarket, "unknown_market"),
      marketDisplay: text(row.marketDisplay || rowMarketKey(row), "Prop"),
      line: row.trust?.propIdentity?.line ?? row.line ?? row.propLine ?? null,
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

function renderTrustSurface(payload: any, requestId: string, extras: { actionnetwork?: any; runtime?: any; workflow?: any; ml?: any } = {}) {
  const severity = freshnessSeverity(payload);
  const rows = Array.isArray(payload?.rows) ? payload.rows : [];
  const firstFreshness = rows.map((row: any) => row?.freshness).find(Boolean) || {};
  const boardSnapshotAt = text(payload?.snapshot?.writtenAt || payload?.snapshotAt || payload?.generatedAt || payload?.updatedAt || payload?.date, "Unavailable");
  const boardSnapshotDate = boardSnapshotAt.includes("T") ? boardSnapshotAt.slice(0, 10) : "";
  const boardDate = text(payload?.snapshot?.date || boardSnapshotDate || payload?.latestBoardDate || payload?.playerboard?.latestAvailableDate || payload?.date, "Unavailable");
  const boardFreshnessLabel = text(firstFreshness.label || payload?.freshness?.label || severity.label, severity.label);
  const boardFreshnessTone = text(firstFreshness.tone || payload?.freshness?.tone || severity.tone, severity.tone);
  const boardFreshnessCopy = text(firstFreshness.status || firstFreshness.source || payload?.freshness?.status || severity.copy, severity.copy);
  const schemaVersion = text(payload?.playerboard?.schemaVersion || payload?.schemaVersion || payload?.contracts?.playerboard || "playerboard.v3", "Unknown");
  const modeledMarkets = modeledMarketCount(payload);
  const productionMarkets = Array.isArray(extras.ml?.productionMarkets) ? extras.ml.productionMarkets.length : Array.isArray(payload?.productionEligibleMarkets) ? payload.productionEligibleMarkets.length : MARKETS.filter((market) => market.modelReady).length;
  const marketsReady = modeledMarkets || productionMarkets;
  const modelMode = modeledMarkets ? "Experimental / Research Mode" : text(payload?.productStateDetail?.label || payload?.productState, "Research Mode");
  const runtimeTone = extras.runtime?.ok ? "fresh" : extras.runtime?.status === "degraded" ? "aging" : "stale";
  const workflowTone = extras.workflow?.status === "success" ? "fresh" : extras.workflow?.status === "warning" ? "aging" : "stale";
  const actionTone = extras.actionnetwork?.ok ? "fresh" : extras.actionnetwork?.status === "degraded" ? "aging" : "stale";
  clear(document.getElementById("freshnessSurface"), [
    trustCard("Board snapshot", boardSnapshotAt, boardFreshnessLabel, boardFreshnessTone),
    trustCard("Playerboard data", boardDate, boardFreshnessCopy, boardFreshnessTone),
    trustCard("Runtime", extras.runtime?.ok ? "Runtime Healthy" : "Runtime Degraded", text(extras.runtime?.status || severity.label), runtimeTone),
    trustCard("Workflow", workflowLabel(extras.workflow), text(extras.workflow?.checkedAt || boardSnapshotAt), workflowTone),
    trustCard("Odds freshness", boardSnapshotAt, boardFreshnessCopy, boardFreshnessTone),
    trustCard("ActionNetwork", actionNetworkLabel(extras.actionnetwork), text(extras.actionnetwork?.labels?.trainableEligibility || extras.actionnetwork?.snapshot?.snapshotFreshness || "not trainable"), actionTone),
    trustCard("Model readiness", `${marketsReady} MLB markets`, modelMode, marketsReady ? "fresh" : "aging"),
    trustCard("Schema version", schemaVersion, requestId ? `Request ${requestId}` : "Contract checked", "fresh"),
  ]);
}

async function loadMarketRegistry() {
  try {
    const params = new URLSearchParams();
    if (appState.date) params.set("date", appState.date);
    const { payload } = await jsonFetch<MarketRegistryPayload>(`/api/mlb/market-registry?${params.toString()}`);
    appState.marketRegistry = payload;
    appState.marketCoverage = payload?.marketCoverage || payload?.coverage || appState.marketCoverage;
  } catch (error) {
    if (!appState.marketRegistry) appState.marketRegistry = { groups: fallbackMarketGroups(), markets: [] };
    appState.marketCoverage = appState.marketCoverage || { warnings: [error instanceof Error ? error.message : String(error)] };
  }
  const select = document.getElementById("marketFilter");
  if (select instanceof HTMLSelectElement) renderMarketOptions(select, appState.marketRegistry);
}

function modeledMarketCount(payload: any): number {
  const summaryCount = Number(payload?.summary?.modeledMarkets);
  if (Number.isFinite(summaryCount) && summaryCount > 0) return summaryCount;
  const sourceMarkets = payload?.source?.predictionJoin?.predictionsByMarket || payload?.meta?.predictionsByMarket;
  if (sourceMarkets && typeof sourceMarkets === "object") {
    const count = Object.values(sourceMarkets).filter((value) => Number(value) > 0).length;
    if (count > 0) return count;
  }
  const rows = Array.isArray(payload?.rows) ? payload.rows : [];
  return new Set(rows.filter((row: any) => row?.predictionMatched === true).map((row: any) => text(row?.market || row?.baseMarket, "")).filter(Boolean)).size;
}

function workflowLabel(payload: any): string {
  if (payload?.status === "success") return "Workflow Fresh";
  if (payload?.status === "warning") return "Workflow Degraded";
  if (payload?.status === "failed") return "Workflow Failed";
  return "Workflow Missing";
}

function actionNetworkLabel(payload: any): string {
  if (payload?.snapshot?.snapshotFreshness === "fresh") return "Snapshot Fresh";
  if (payload?.labels?.eventConfirmed) return "Event Confirmed";
  if (payload?.status === "degraded") return "Not Trainable";
  return "Snapshot Stale";
}

function trustSkeleton(label: string) { return trustCard(label, "Checking", "Loading trust signal…", "aging"); }
function trustCard(label: string, value: unknown, copy: unknown, tone: string) { return h("article", { className: `ob-trust-card is-${tone}` }, [h("span", { text: label }), h("strong", { text: value }), h("em", { text: copy })]); }
function renderDensityToggle() {
  return h("div", { className: "ob-density-toggle", attrs: { role: "group", "aria-label": "Board density" } }, [
    densityButton("compact", "Compact"),
    densityButton("research", "Research"),
  ]);
}
function densityButton(value: "compact" | "research", label: string) {
  const active = appState.density === value;
  return h("button", { className: active ? "is-active" : "", type: "button", text: label, dataset: { density: value }, attrs: { "aria-pressed": active ? "true" : "false" } });
}
function updateDensityControls() {
  document.querySelectorAll<HTMLElement>("[data-density]").forEach((node) => {
    const active = node.dataset.density === appState.density;
    node.classList.toggle("is-active", active);
    node.setAttribute("aria-pressed", active ? "true" : "false");
  });
}
function renderLoading() { clear(document.getElementById("boardHost"), [h("div", { className: "ob-empty" }, [h("strong", { text: "Loading board" }), h("span", { text: "Fetching EdgeBoard rows and trust metadata." })])]); }
function option(value: string, label: string) { const node = h("option", { text: label }); node.value = value; return node; }
function normalizeFilter(value: unknown) { return String(value || "").toLowerCase().trim().replace(/[\s-]+/g, "_"); }
function syncTrustFilters() {
  fillSelect("actionLabelFilter", uniqueTrustValues(appState.rows, (row) => rowTrustSummary(row).actionLabel), "Any action");
  fillSelect("marketCapabilityFilter", uniqueTrustValues(appState.rows, (row) => rowTrustSummary(row).marketCapabilityStatus), "Any capability");
  fillSelect("productionStatusFilter", uniqueTrustValues(appState.rows, (row) => rowTrustSummary(row).productionStatus), "Any model state");
  fillSelect("calibrationStatusFilter", uniqueTrustValues(appState.rows, (row) => rowTrustSummary(row).calibrationStatus), "Any calibration");
  fillSelect("backtestStatusFilter", uniqueTrustValues(appState.rows, (row) => rowTrustSummary(row).backtestStatus), "Any backtest");
  fillSelect("freshnessStatusFilter", uniqueTrustValues(appState.rows, (row) => rowTrustSummary(row).freshnessStatus), "Any freshness");
}
function fillSelect(id: string, values: string[], allLabel: string) {
  const select = document.getElementById(id);
  if (!(select instanceof HTMLSelectElement)) return;
  const current = select.value;
  select.replaceChildren(option("", allLabel), ...values.map((value) => option(value, trustStatusLabel(value))));
  select.value = values.includes(current) ? current : "";
}
function currentEmptyState() {
  if (appState.missingDataOnly) return { title: "No rows with missing data", copy: "Feature matrix and missing-data warnings are clear for the current filter set." };
  if (appState.freshnessStatus === "stale" || appState.freshnessStatus === "missing") return { title: "No stale rows", copy: "Data stale warnings are not present for the current filter set." };
  if (appState.marketCapabilityStatus === "unsupported") return { title: "No unsupported markets", copy: "Unsupported market rows are not present for the current filter set." };
  if (appState.calibrationStatus === "missing") return { title: "No calibration-missing rows", copy: "Model calibration missing rows are not present for the current filter set." };
  if (appState.backtestStatus === "missing") return { title: "No backtest-missing rows", copy: "Backtest missing rows are not present for the current filter set." };
  return { title: "No props match these filters", copy: "Adjust market, side, date, trust status, or search." };
}
function setMeta(copy: string) { const meta = document.getElementById("boardMeta"); if (meta) meta.textContent = copy; }
function exposureCopy() { const units = number(appState.exposure?.totalStakeUnits, 0).toFixed(2); return `0u research pick saved. ${units}u active exposure. Research-only picks stay at 0u.`; }
function updateExposure() { const target = document.getElementById("exposureSummary"); if (target) target.textContent = exposureCopy(); }
function updatePositiveCount() { const total = appState.filteredRows.filter((row: OutlierBoardRow) => edgeValue(row) > 0).length; const target = document.getElementById("positiveEdgeCount"); if (target) target.textContent = String(total); }
function showToast(title: string, copy: string) { const toast = h("div", { className: "ob-toast", attrs: { role: "status" } }, [h("strong", { text: title }), h("span", { text: copy })]); document.body.append(toast); setTimeout(() => toast.remove(), 3200); }
