
const MARKETS = [
  {
    "key": "batter_hits",
    "label": "Batter Hits",
    "sport": "MLB",
    "scope": "player",
    "defaultLineDisplay": "0.5+ hits",
    "modelReady": true,
    "enabled": true,
    "productionUi": true,
    "description": "Batter hit props with model and recent-form context."
  },
  {
    "key": "batter_total_bases",
    "label": "Batter Total Bases",
    "sport": "MLB",
    "scope": "player",
    "defaultLineDisplay": "1.5+ bases",
    "modelReady": true,
    "enabled": true,
    "productionUi": true,
    "description": "Total bases research for hitters."
  },
  {
    "key": "batter_home_runs",
    "label": "Batter Home Runs",
    "sport": "MLB",
    "scope": "player",
    "defaultLineDisplay": "0.5 HR",
    "modelReady": false,
    "enabled": true,
    "productionUi": true,
    "description": "Research-only HR surface until model readiness is promoted."
  },
  {
    "key": "pitcher_strikeouts",
    "label": "Pitcher Strikeouts",
    "sport": "MLB",
    "scope": "player",
    "defaultLineDisplay": "4.5 Ks",
    "modelReady": true,
    "enabled": true,
    "productionUi": true,
    "description": "Pitcher strikeout props with workload and opponent context."
  },
  {
    "key": "pitcher_hits_allowed",
    "label": "Pitcher Hits Allowed",
    "sport": "MLB",
    "scope": "player",
    "defaultLineDisplay": "5.5 hits",
    "modelReady": false,
    "enabled": true,
    "productionUi": true,
    "description": "Research-only pitcher contact prevention market."
  },
  {
    "key": "pitcher_earned_runs",
    "label": "Pitcher Earned Runs",
    "sport": "MLB",
    "scope": "player",
    "defaultLineDisplay": "2.5 ER",
    "modelReady": false,
    "enabled": true,
    "productionUi": true,
    "description": "Research-only run prevention market."
  },
  {
    "key": "team_total_runs",
    "label": "Team Total Runs",
    "sport": "MLB",
    "scope": "team",
    "defaultLineDisplay": "4.5 runs",
    "modelReady": false,
    "enabled": true,
    "productionUi": true,
    "description": "Team run total market; visible as research-only until backed by model cards."
  },
  {
    "key": "team_first_to_score",
    "label": "Team First To Score",
    "sport": "MLB",
    "scope": "team",
    "defaultLineDisplay": "first score",
    "modelReady": false,
    "enabled": true,
    "productionUi": true,
    "description": "Team first-score market; research-only trust state."
  }
];
const PRODUCTION_MARKETS = MARKETS.filter((market) => market.enabled && market.productionUi);
const MARKET_SELECT_OPTIONS = [{ key: "", label: "All MLB markets", modelReady: false }, ...PRODUCTION_MARKETS.map((market) => ({ key: market.key, label: market.label, modelReady: market.modelReady }))];
const appState = { rows: [], filteredRows: [], selectedIndex: -1, market: "", query: "", side: "", date: todayIso(), loading: false, status: null, exposure: null, requestId: "" };
const disabledSports = ["NBA", "NHL", "Soccer", "WNBA", "NCAAFB"];

document.addEventListener("DOMContentLoaded", () => { boot(); });

async function boot() {
  document.body.classList.add("outlier-production");
  renderShell();
  bindEvents();
  await Promise.allSettled([loadStatus(), loadExposure()]);
  await loadBoard();
}

async function jsonFetch(path, init = {}) {
  const response = await fetch(path, { cache: "no-store", headers: { Accept: "application/json", ...(init.headers || {}) }, ...init });
  const requestId = response.headers.get("X-Request-Id") || response.headers.get("x-request-id") || "";
  let payload = null;
  try { payload = await response.json(); } catch (error) { if (response.ok) throw error; }
  if (!response.ok) {
    const message = payload && typeof payload === "object" && "error" in payload ? String(payload.error) : `HTTP ${response.status}`;
    throw new Error(requestId ? `${message} (${requestId})` : message);
  }
  return { payload, requestId };
}

function h(tagName, options = {}, children = []) {
  const element = document.createElement(tagName);
  if (typeof options.className === "string") element.className = options.className;
  if (typeof options.id === "string") element.id = options.id;
  if (options.text !== undefined) element.textContent = String(options.text);
  if (typeof options.type === "string" && "type" in element) element.type = options.type;
  if (options.value !== undefined && "value" in element) element.value = String(options.value);
  if (options.dataset && typeof options.dataset === "object") Object.entries(options.dataset).forEach(([key, value]) => { element.dataset[key] = String(value); });
  if (options.attrs && typeof options.attrs === "object") Object.entries(options.attrs).forEach(([key, value]) => { if (value !== false && value !== null && value !== undefined) element.setAttribute(key, String(value)); });
  children.filter(Boolean).forEach((child) => element.append(child instanceof Node ? child : document.createTextNode(String(child))));
  return element;
}
function clear(target, children = []) { if (target) target.replaceChildren(...children); }
function text(value, fallback = "--") { const raw = value === null || value === undefined ? "" : String(value).trim(); return raw || fallback; }
function number(value, fallback = 0) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : fallback; }
function percent(value, fallback = "--") { const parsed = number(value, NaN); if (!Number.isFinite(parsed)) return fallback; const scaled = Math.abs(parsed) <= 1 ? parsed * 100 : parsed; return `${scaled.toFixed(Math.abs(scaled) % 1 ? 1 : 0)}%`; }
function signedPercent(value) { const parsed = number(value, NaN); if (!Number.isFinite(parsed)) return "--"; const scaled = Math.abs(parsed) <= 1 ? parsed * 100 : parsed; return `${scaled >= 0 ? "+" : ""}${scaled.toFixed(1)}%`; }
function formatOdds(value) { const raw = text(value, ""); if (!raw) return "--"; const parsed = Number(raw); if (!Number.isFinite(parsed)) return raw; return parsed > 0 ? `+${parsed}` : String(parsed); }
function todayIso() { const now = new Date(); const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000); return local.toISOString().slice(0, 10); }
function marketLabel(key) { if (!key) return "Prop"; return MARKETS.find((market) => market.key === key)?.label || String(key).replace(/_/g, " "); }

function renderShell() {
  const root = h("section", { id: "outlierApp", className: "outlier-app" }, [renderSidebar(), renderMain(), renderDetailRail()]);
  clear(document.body, [root]);
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
  MARKET_SELECT_OPTIONS.forEach((opt) => { const node = h("option", { text: opt.label }); node.value = opt.key; market.append(node); });
  return h("div", { className: "ob-filter-grid" }, [market, h("input", { id: "playerFilter", className: "ob-input", value: "", attrs: { type: "search", placeholder: "Search player, team, opponent", "aria-label": "Search board" } }), h("select", { id: "sideFilter", className: "ob-select", attrs: { "aria-label": "Side filter" } }, [option("", "Over / Under"), option("over", "Over"), option("under", "Under")]), h("input", { id: "dateFilter", className: "ob-input", value: appState.date, attrs: { type: "date", "aria-label": "Slate date" } })]);
}
function renderDetailRail() { return h("aside", { id: "detailRail", className: "ob-detail", attrs: { "aria-label": "Prop detail rail", "aria-live": "polite" } }, [emptyRail()]); }
function bindEvents() {
  document.body.addEventListener("click", async (event) => {
    const target = event.target; if (!(target instanceof Element)) return;
    const row = target.closest("[data-row-index]"); if (row) { selectRow(Number(row.getAttribute("data-row-index"))); return; }
    const action = target.closest("[data-action]"); if (!action) return;
    const name = action.getAttribute("data-action");
    if (name === "reload") await loadBoard();
    if (name === "save-pick") await saveSelectedPick();
    if (name === "focus-picks") document.getElementById("detailRail")?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (name === "focus-trust") document.getElementById("freshnessSurface")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.body.addEventListener("input", (event) => { const target = event.target; if (target instanceof HTMLInputElement && target.id === "playerFilter") { appState.query = target.value; applyFilters(); renderBoard(); } });
  document.body.addEventListener("change", async (event) => {
    const target = event.target; if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;
    if (target.id === "marketFilter") { appState.market = target.value; applyFilters(); renderBoard(); }
    if (target.id === "sideFilter") { appState.side = target.value; applyFilters(); renderBoard(); }
    if (target.id === "dateFilter") { appState.date = target.value || todayIso(); await loadBoard(); }
  });
}
async function loadStatus() {
  try { const { payload, requestId } = await jsonFetch("/api/app/status"); appState.status = payload; appState.requestId = requestId || payload?.meta?.requestId || ""; renderTrustSurface(payload, appState.requestId); }
  catch (error) { clear(document.getElementById("freshnessSurface"), [trustCard("Status", "Unavailable", error?.message || "App status could not be loaded.", "unavailable")]); }
}
async function loadExposure() {
  try { const { payload } = await jsonFetch("/api/exposure/summary"); appState.exposure = payload?.exposure || payload; updateExposure(); }
  catch (error) { appState.exposure = { totalStakeUnits: 0, warnings: [String(error?.message || error)] }; updateExposure(); }
}
async function loadBoard() {
  appState.loading = true; renderLoading();
  try { const params = new URLSearchParams({ limit: "500" }); if (appState.date) params.set("date", appState.date); const { payload, requestId } = await jsonFetch(`/api/edge-board?${params.toString()}`); appState.rows = normalizeRows(payload); appState.requestId = requestId || payload?.meta?.requestId || appState.requestId; appState.selectedIndex = -1; applyFilters(); renderBoard(payload); renderRail(null); }
  catch (error) { clear(document.getElementById("boardHost"), [h("div", { className: "ob-empty" }, [h("strong", { text: "Board unavailable" }), h("span", { text: error?.message || "The EdgeBoard API did not return a usable payload." })])]); setMeta("0 props · board unavailable"); }
  finally { appState.loading = false; }
}
function normalizeRows(payload) { if (Array.isArray(payload)) return payload; if (Array.isArray(payload?.rows)) return payload.rows; if (Array.isArray(payload?.data?.rows)) return payload.data.rows; return []; }
function applyFilters() { const q = appState.query.trim().toLowerCase(); appState.filteredRows = appState.rows.filter((row) => { const marketOk = !appState.market || row.market === appState.market || row.baseMarket === appState.market; const sideText = String(row.side || row.rawLabel || "").toLowerCase(); const sideOk = !appState.side || sideText.includes(appState.side) || (!sideText && appState.side === "over"); const haystack = [row.player, row.playerName, row.team, row.opponent, row.marketDisplay, row.market].map((part) => String(part || "").toLowerCase()).join(" "); return marketOk && sideOk && (!q || haystack.includes(q)); }); }
function renderBoard(payload = null) {
  const rows = appState.filteredRows.slice(0, 200);
  const table = h("table", { className: "ob-table", attrs: { "aria-label": "Outlier board" } }, [h("thead", {}, [h("tr", {}, ["Player", "Market", "Line", "Odds", "Model", "Implied", "Edge", "Readiness"].map((label) => h("th", { text: label })))]), h("tbody", {}, rows.map((row, index) => renderRow(row, index)))]);
  clear(document.getElementById("boardHost"), rows.length ? [table] : [h("div", { className: "ob-empty" }, [h("strong", { text: "No props match these filters" }), h("span", { text: "Adjust market, side, date, or search." })])]);
  const source = payload?.source?.label || payload?.source?.path || "EdgeBoard"; setMeta(`${appState.filteredRows.length}/${appState.rows.length} MLB props · ${source}${appState.requestId ? ` · ${appState.requestId}` : ""}`); updatePositiveCount();
}
function renderRow(row, index) { const edge = edgeValue(row); const tone = edge >= 5 ? "is-good" : edge >= 0 ? "is-watch" : "is-risk"; return h("tr", { className: index === appState.selectedIndex ? "is-selected" : "", dataset: { rowIndex: String(index) }, attrs: { tabindex: "0" } }, [h("td", {}, [h("div", { className: "ob-player" }, [h("strong", { text: text(row.player || row.playerName || row.team, "MLB") }), h("span", { text: matchup(row) })])]), h("td", { text: marketLabel(String(row.market || row.baseMarket || "")) }), h("td", { text: text(row.line ?? row.propLine) }), h("td", { text: formatOdds(row.americanOdds ?? row.odds) }), h("td", { text: percent(row.modelProbability ?? row.probability ?? row.prob) }), h("td", { text: percent(row.impliedProbability ?? row.sportsbookImpliedPercent ?? row.impliedPercent) }), h("td", {}, [h("span", { className: `ob-pill ${tone}`, text: signedPercent(edge) })]), h("td", {}, [h("span", { className: `ob-pill ${readinessTone(row)}`, text: readiness(row) })])]); }
function selectRow(index) { appState.selectedIndex = index; renderBoard(); renderRail(appState.filteredRows[index]); }
function renderRail(row) { const rail = document.getElementById("detailRail"); if (!row) { clear(rail, [emptyRail()]); return; } clear(rail, [h("article", { className: "ob-rail-card" }, [h("p", { className: "ob-kicker", text: "Detail rail" }), h("h2", { text: text(row.player || row.playerName || row.team, "Selected prop") }), h("p", { text: `${marketLabel(String(row.market || row.baseMarket || ""))} · ${matchup(row)} · ${text(row.rawLabel || row.side, "Over")}` }), h("div", { className: "ob-stat-grid" }, [stat("Line", text(row.line ?? row.propLine)), stat("Odds", formatOdds(row.americanOdds ?? row.odds)), stat("Model", percent(row.modelProbability ?? row.probability ?? row.prob)), stat("Edge", signedPercent(edgeValue(row)))])]), h("article", { className: "ob-rail-card" }, [h("h3", { text: "Trust context" }), h("p", { text: trustCopy(row) }), h("div", { className: "ob-stat-grid" }, [stat("Readiness", readiness(row)), stat("Freshness", freshnessSeverity(appState.status).label)])]), h("article", { className: "ob-rail-card" }, [h("h3", { text: "Picks & exposure" }), h("p", { text: "Research-only saves default to 0 units and do not alter model backtests." }), h("button", { className: "ob-button is-primary", type: "button", text: "Add research pick", dataset: { action: "save-pick" } }), h("p", { id: "savePickStatus", className: "ob-muted", text: exposureCopy() })])]); }
async function saveSelectedPick() { const row = appState.filteredRows[appState.selectedIndex]; const status = document.getElementById("savePickStatus"); if (!row || !status) return; status.textContent = "Saving research-only pick…"; try { const body = { date: appState.date, player: text(row.player || row.playerName || row.team, "MLB"), team: text(row.team, ""), opponent: text(row.opponent || row.home, ""), market: text(row.market || row.baseMarket, "unknown_market"), marketDisplay: marketLabel(String(row.market || row.baseMarket || "")), line: row.line ?? row.propLine ?? null, americanOdds: row.americanOdds ?? row.odds ?? null, decisionLabel: "Watchlist", readinessLabel: "Research only", suggestedStake: "Research only", stakeUnits: 0, source: "outlier-ui" }; const { payload } = await jsonFetch("/api/my-picks", { method: "POST", headers: { "Content-Type": "application/json", "X-Baseball-Prop-Action": "1" }, body: JSON.stringify(body) }); appState.exposure = payload?.exposure || appState.exposure; status.textContent = `Saved ${text(payload?.pick?.player || body.player)} as 0u research pick.`; updateExposure(); showToast("Pick saved", "Research-only pick saved with 0.00u exposure."); } catch (error) { status.textContent = error?.message || "Save failed."; } }
function renderTrustSurface(payload, requestId) { const severity = freshnessSeverity(payload); const boardDate = text(payload?.latestBoardDate || payload?.playerboard?.latestAvailableDate || payload?.date, "Unavailable"); const schemaVersion = text(payload?.playerboard?.schemaVersion || payload?.schemaVersion || payload?.contracts?.playerboard || "playerboard.v3", "Unknown"); const marketsReady = Array.isArray(payload?.productionEligibleMarkets) ? payload.productionEligibleMarkets.length : MARKETS.filter((market) => market.modelReady).length; clear(document.getElementById("freshnessSurface"), [trustCard("Last collector run", text(payload?.workflows?.lastCompletedAt || payload?.collector?.finishedAt || boardDate), severity.label, severity.tone), trustCard("Playerboard data", boardDate, text(payload?.dataConfidence || payload?.playerboard?.dataConfidence, "Missing"), severity.tone), trustCard("Odds freshness", text(payload?.odds?.latestSnapshotAt || payload?.oddsFreshness || boardDate), severity.copy, severity.tone), trustCard("Model readiness", `${marketsReady} MLB markets`, text(payload?.productStateDetail?.label || payload?.productState, "Research Mode"), marketsReady ? "fresh" : "aging"), trustCard("Schema version", schemaVersion, requestId ? `Request ${requestId}` : "Contract checked", "fresh")]); }
function trustSkeleton(label) { return trustCard(label, "Checking", "Loading trust signal…", "aging"); }
function trustCard(label, value, copy, tone) { return h("article", { className: `ob-trust-card is-${tone}` }, [h("span", { text: label }), h("strong", { text: value }), h("em", { text: copy })]); }
function freshnessSeverity(payload) { const raw = String(payload?.staleDataSeverity || payload?.dataFreshness?.severity || payload?.dataConfidence || "").toLowerCase(); if (raw.includes("stale") || raw.includes("red") || raw.includes("missing")) return { tone: "stale", label: "Stale", copy: "Do not trust for live betting." }; if (raw.includes("aging") || raw.includes("partial") || raw.includes("warn") || raw.includes("amber")) return { tone: "aging", label: "Aging", copy: "Usable for research; verify lines." }; if (raw.includes("good") || raw.includes("fresh") || raw.includes("green")) return { tone: "fresh", label: "Fresh", copy: "Within configured freshness window." }; return { tone: "unavailable", label: "Unavailable", copy: "Source freshness is not available." }; }
function renderLoading() { clear(document.getElementById("boardHost"), [h("div", { className: "ob-empty" }, [h("strong", { text: "Loading board" }), h("span", { text: "Fetching EdgeBoard rows and trust metadata." })])]); }
function emptyRail() { return h("article", { className: "ob-rail-card" }, [h("p", { className: "ob-kicker", text: "Research rail" }), h("h2", { text: "Select a prop" }), h("p", { text: "Open a board row to inspect price, model, freshness, and pick exposure without leaving the board." })]); }
function option(value, label) { const node = h("option", { text: label }); node.value = value; return node; }
function stat(label, value) { return h("div", { className: "ob-stat" }, [h("span", { text: label }), h("strong", { text: value })]); }
function setMeta(copy) { const meta = document.getElementById("boardMeta"); if (meta) meta.textContent = copy; }
function matchup(row) { const away = text(row.away || row.team, ""); const home = text(row.home || row.opponent, ""); return away && home ? `${away} @ ${home}` : text(row.game || row.matchup, "Matchup pending"); }
function edgeValue(row) { return number(row.finalEdgePercent ?? row.edge ?? row.edgePercent, 0); }
function readiness(row) { return text(row.modelCard?.status || row.readinessLabel || row.readiness || row.confidence, "Research only"); }
function readinessTone(row) { const raw = readiness(row).toLowerCase(); if (raw.includes("ready") || raw.includes("production")) return "is-good"; if (raw.includes("missing") || raw.includes("stale")) return "is-risk"; return "is-watch"; }
function trustCopy(row) { return readinessTone(row) === "is-good" ? "This prop has model-readiness context. Still verify sportsbook lines before acting." : "This prop is visible for research but should stay 0u until data and model gates are satisfied."; }
function exposureCopy() { const units = number(appState.exposure?.totalStakeUnits, 0).toFixed(2); return `${units}u active exposure. Research-only picks stay at 0u.`; }
function updateExposure() { const target = document.getElementById("exposureSummary"); if (target) target.textContent = exposureCopy(); }
function updatePositiveCount() { const total = appState.filteredRows.filter((row) => edgeValue(row) > 0).length; const target = document.getElementById("positiveEdgeCount"); if (target) target.textContent = String(total); }
function showToast(title, copy) { const toast = h("div", { className: "ob-toast", attrs: { role: "status" } }, [h("strong", { text: title }), h("span", { text: copy })]); document.body.append(toast); setTimeout(() => toast.remove(), 3200); }
