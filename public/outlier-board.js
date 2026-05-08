import {
  MARKETS,
  createElement,
  jsonFetch,
  normalizeRows,
  propLabel,
  replaceChildren,
  signedPercent,
  text,
  percent,
  formatOdds,
  dispatch,
  listen,
} from "/outlier-shared.js";

const SPORT_TABS = ["NBA", "MLB", "Soccer", "NHL", "WNBA", "NCAAFB"];
const CATEGORY_TABS = ["Today", "Tomorrow", "Batter Props", "Pitcher Props", "Team Props", "Saved"];
const HIT_COLUMNS = [["L5", "L5"], ["L10", "L10"], ["L20", "L20"], ["H2H", "H2H"], ["season", "2026"], ["prevSeason", "2025"]];
const PAGE_SIZE = 80;

const boardState = {
  mounted: false,
  rows: [],
  filteredRows: [],
  loading: false,
  error: "",
  market: "",
  side: "",
  game: "",
  query: "",
  categoryTab: "Today",
  date: "",
  nav: "Props",
  sport: "MLB",
  requestId: "",
  cache: null,
};

export async function mount() {
  if (boardState.mounted) return;
  boardState.mounted = true;
  listen("outlier:view", (event) => {
    if (event.detail.module === "board") renderBoardView(event.detail.state || {});
  });
}

async function renderBoardView(shellState = {}) {
  const host = document.getElementById("outlierWorkspace");
  if (!host) return;
  boardState.nav = shellState.nav || boardState.nav || "Props";
  boardState.date = shellState.date || boardState.date || todayIso();
  replaceChildren(host, [layout()]);
  bindLocalEvents(host);
  await loadBoard();
}

function layout() {
  const wrapper = createElement("section", { className: "ob-props-module" });
  wrapper.append(renderHero(), renderBoardShell());
  return wrapper;
}

function renderHero() {
  const headerTitle = boardState.nav === "Games" ? "Games" : boardState.nav === "Popular" ? "Popular Props" : boardState.nav;
  return createElement("header", { className: "ob-hero" }, [
    createElement("div", { className: "ob-topbar" }, [
      createElement("div", {}, [createElement("h1", { className: "ob-title", text: headerTitle || "Props" })]),
      createElement("div", { className: "ob-date-wrap" }, [
        createElement("input", { className: "ob-input ob-date", type: "date", value: boardState.date || todayIso(), dataset: { control: "date" }, attrs: { "aria-label": "Board date" } }),
        createElement("button", { className: "ob-load-button", type: "button", text: "Load Board", dataset: { action: "reload" } }),
      ]),
    ]),
    createElement("div", { className: "ob-sport-row", attrs: { role: "tablist", "aria-label": "Sports" } }, SPORT_TABS.map((tab) => createElement("button", { className: `ob-tab ${boardState.sport === tab ? "is-active" : ""}`, type: "button", text: tab, dataset: { sport: tab } }))),
    renderFilterShell(),
    renderCategoryTabs(),
  ]);
}

function renderFilterShell() {
  const filterCount = activeFilterCount();
  return createElement("div", { className: "ob-filter-shell", attrs: { "aria-label": "Prop filters" } }, [
    createElement("div", { className: "ob-filter-left" }, [
      createElement("button", { className: "ob-filter-button is-primary", type: "button" }, [createElement("span", { className: "ob-filter-count", text: String(filterCount) }), document.createTextNode(" Filters")]),
      createElement("button", { className: `ob-icon-button ob-clear-filter ${filterCount ? "" : "is-hidden"}`, type: "button", text: "x", dataset: { action: "clearFilters" }, attrs: { "aria-label": "Clear filters" } }),
      createElement("button", { className: `ob-filter-button is-saved ${boardState.categoryTab === "Saved" ? "is-active" : ""}`, type: "button", text: "Saved", dataset: { categoryTab: "Saved" } }),
    ]),
    createElement("div", { className: "ob-filter-controls" }, [marketSelect(), createElement("input", { className: "ob-input ob-search", type: "search", value: boardState.query, placeholder: "Players", dataset: { control: "query" }, attrs: { "aria-label": "Players" } }), gameSelect(), sideSelect()]),
    createElement("div", { className: "ob-filter-right" }, [
      createElement("button", { className: "ob-icon-button", type: "button", text: "Cols", dataset: { action: "columnConfig" }, attrs: { "aria-label": "Column settings" } }),
      createElement("button", { className: "ob-icon-button ob-rail-toggle", type: "button", text: "i", dataset: { action: "toggleRail" }, attrs: { "aria-label": "Open matchup info" } }),
      createElement("button", { className: "ob-toggle", type: "button", dataset: { action: "showAllLines" } }, [createElement("span", { text: "Show all lines" }), createElement("span", { className: "ob-toggle-dot", attrs: { "aria-hidden": "true" } })]),
      createElement("span", { id: "obPropCount", className: "ob-rail-note", text: `${boardState.filteredRows.length}/${boardState.rows.length} Props` }),
    ]),
  ]);
}

function marketSelect() {
  const select = createElement("select", { className: "ob-select", dataset: { control: "market" }, attrs: { "aria-label": "Propositions" } });
  MARKETS.forEach(([value, label], index) => select.append(optionNode(value, index === 0 ? "Propositions" : label, boardState.market === value)));
  return select;
}

function gameSelect() {
  const select = createElement("select", { className: "ob-select", dataset: { control: "game" }, attrs: { "aria-label": "Games" } });
  select.append(optionNode("", "Games", boardState.game === ""));
  availableGames().forEach((game) => select.append(optionNode(game, game, boardState.game === game)));
  return select;
}

function sideSelect() {
  const select = createElement("select", { className: "ob-select", dataset: { control: "side" }, attrs: { "aria-label": "Over under" } });
  select.append(optionNode("", "Over / Under", boardState.side === ""));
  select.append(optionNode("over", "Over", boardState.side === "over"));
  select.append(optionNode("under", "Under", boardState.side === "under"));
  return select;
}

function optionNode(value, label, selected) {
  const option = createElement("option", { text: label });
  option.value = value;
  option.selected = selected;
  return option;
}

function renderCategoryTabs() {
  return createElement("div", { className: "ob-category-tabs", attrs: { role: "tablist", "aria-label": "Prop categories" } }, CATEGORY_TABS.map((tab) => createElement("button", { className: boardState.categoryTab === tab ? "is-active" : "", type: "button", text: tab, dataset: { categoryTab: tab } })));
}

function renderBoardShell() {
  return createElement("section", { className: "ob-board-wrap" }, [createElement("div", { className: "ob-board" }, [createElement("div", { id: "outlierBoardMeta", className: "ob-board-meta", text: "Loading board" }), createElement("div", { id: "outlierBoardTable" })])]);
}

function bindLocalEvents(host) {
  host.onclick = (event) => {
    const action = event.target.closest("[data-action]");
    if (action?.dataset.action === "reload") return loadBoard();
    if (action?.dataset.action === "clearFilters") {
      boardState.market = ""; boardState.side = ""; boardState.game = ""; boardState.query = ""; boardState.categoryTab = "Today"; redraw(); return;
    }
    if (action?.dataset.action === "toggleRail") { dispatch("outlier:rail-open", {}); return; }
    const sport = event.target.closest("[data-sport]");
    if (sport) { boardState.sport = sport.dataset.sport === "MLB" ? "MLB" : boardState.sport; redraw(); return; }
    const category = event.target.closest("[data-category-tab]");
    if (category) { boardState.categoryTab = category.dataset.categoryTab || "Today"; applyFilters(); redraw(); return; }
    const rowButton = event.target.closest("[data-row-index]");
    if (rowButton) {
      const row = boardState.filteredRows[Number(rowButton.dataset.rowIndex)];
      if (row) import("/outlier-detail.js").then((module) => module.mount?.()).then(() => dispatch("outlier:open-detail", { row, index: Number(rowButton.dataset.rowIndex) }));
    }
  };

  host.oninput = (event) => {
    if (event.target.dataset?.control === "query") { boardState.query = event.target.value; applyFilters(); renderTable(); }
  };

  host.onchange = (event) => {
    const control = event.target.dataset?.control;
    if (control === "date") { boardState.date = event.target.value || todayIso(); loadBoard(); }
    if (control === "market") { boardState.market = event.target.value; loadBoard(); }
    if (control === "game") { boardState.game = event.target.value; applyFilters(); renderTable(); }
    if (control === "side") { boardState.side = event.target.value; applyFilters(); renderTable(); }
  };
}

async function loadBoard() {
  const meta = document.getElementById("outlierBoardMeta");
  const table = document.getElementById("outlierBoardTable");
  boardState.loading = true; boardState.error = "";
  if (meta) meta.textContent = "Loading board";
  replaceChildren(table, [renderLoading()]);
  try {
    const params = new URLSearchParams();
    if (boardState.date) params.set("date", boardState.date);
    if (boardState.market) params.set("market", boardState.market);
    const { payload, requestId } = await jsonFetch(`/api/edge-board${params.toString() ? `?${params}` : ""}`);
    boardState.rows = normalizeRows(payload);
    boardState.requestId = requestId || payload?.meta?.requestId || "";
    boardState.cache = payload?.boardCache || { hit: Boolean(payload?.cacheHit) };
    applyFilters();
    renderTable();
  } catch (error) {
    boardState.error = text(error?.message, "Failed to load EdgeBoard.");
    replaceChildren(table, [renderEmpty("Missing Data", boardState.error)]);
    if (meta) meta.textContent = "Missing Data";
  } finally { boardState.loading = false; }
}

function redraw() {
  const host = document.getElementById("outlierWorkspace");
  if (!host) return;
  replaceChildren(host, [layout()]); bindLocalEvents(host); applyFilters(); renderTable();
}

function applyFilters() {
  const query = String(boardState.query || "").toLowerCase().trim();
  const selectedSide = String(boardState.side || "").toLowerCase();
  boardState.filteredRows = boardState.rows.filter((row) => {
    const marketMatch = !boardState.market || row.market === boardState.market || row.marketDisplay === boardState.market;
    const side = String(row.rawLabel || row.side || row.pickSide || "").toLowerCase();
    const sideMatch = !selectedSide || side.includes(selectedSide);
    const game = gameLabel(row);
    const gameMatch = !boardState.game || game === boardState.game;
    const haystack = [row.player, row.playerName, row.team, row.opponent, row.market, row.marketDisplay, game].join(" ").toLowerCase();
    const searchMatch = !query || haystack.includes(query);
    return marketMatch && sideMatch && gameMatch && searchMatch && categoryAllows(row);
  }).sort((a, b) => Number(b.finalEdgePercent || b.edge || 0) - Number(a.finalEdgePercent || a.edge || 0));
  dispatchBoardStats();
}

function categoryAllows(row) {
  const market = String(row.market || "").toLowerCase();
  if (boardState.categoryTab === "Batter Props") return market.startsWith("batter_");
  if (boardState.categoryTab === "Pitcher Props") return market.startsWith("pitcher_");
  if (boardState.categoryTab === "Team Props") return market.startsWith("team_");
  if (boardState.categoryTab === "Saved") return false;
  return true;
}

function renderTable() {
  const table = document.getElementById("outlierBoardTable");
  const meta = document.getElementById("outlierBoardMeta");
  if (!table) return;
  if (!boardState.filteredRows.length) {
    replaceChildren(table, [renderEmpty("No props match the current filters.", "Adjust proposition, player, game, side, or saved status. This is Missing Data, not a fallback board.")]);
    if (meta) meta.textContent = "0 MLB props";
    updatePropCount(); return;
  }
  const rows = boardState.filteredRows.slice(0, PAGE_SIZE);
  replaceChildren(table, [tableNode(rows)]);
  if (meta) {
    const cache = boardState.cache?.hit ? "cache hit" : "cache miss";
    meta.textContent = `${boardState.filteredRows.length} MLB props from EdgeBoard · ${cache}${boardState.requestId ? ` · ${boardState.requestId}` : ""}`;
  }
  updatePropCount();
}

function tableNode(rows) {
  const wrap = createElement("div", { className: "ob-table-scroll" });
  const table = createElement("table", { className: "ob-table", attrs: { "aria-label": "Outlier edge board" } });
  table.append(colgroup(), thead(), tbody(rows)); wrap.append(table); return wrap;
}

function colgroup() {
  const group = document.createElement("colgroup");
  ["ob-col-action", "ob-col-player", "ob-col-prop", "ob-col-line", "ob-col-odds", "ob-col-ip", "ob-col-hit", "ob-col-hit", "ob-col-hit", "ob-col-hit", "ob-col-hit", "ob-col-hit"].forEach((className) => group.append(createElement("col", { className })));
  return group;
}

function thead() {
  const head = document.createElement("thead");
  const row = document.createElement("tr");
  ["", "Player", "Proposition", "Line", "Odds", "IP", ...HIT_COLUMNS.map(([, label]) => label)].forEach((label) => { const th = document.createElement("th"); th.append(createElement("span", { text: label })); row.append(th); });
  head.append(row); return head;
}

function tbody(rows) {
  const body = document.createElement("tbody");
  rows.forEach((row, index) => body.append(dataRow(row, index)));
  return body;
}

function dataRow(row, index) {
  const tr = createElement("tr", { dataset: { rowIndex: index }, attrs: { tabindex: "0" } });
  tr.append(td(createElement("button", { className: "ob-plus", type: "button", text: "+", attrs: { "aria-label": "Save prop" } })), playerCell(row), propCell(row), td(createElement("div", { className: "ob-cell ob-number", text: text(row.line || row.propLine) })), oddsCell(row), td(createElement("div", { className: "ob-cell ob-ip", text: percent(row.finalProbabilityPercent || row.modelProbability || row.probability) })), ...HIT_COLUMNS.map(([key]) => hitCell(row, key)));
  return tr;
}

function td(child, className = "") { const node = createElement("td", { className }); if (child) node.append(child); return node; }

function playerCell(row) {
  const player = text(row.player || row.playerName || row.team, "MLB");
  const matchup = gameLabel(row) || "Matchup unavailable";
  const pitcher = text(row.pitcher || row.probablePitcher, "Starter pending");
  return td(createElement("div", { className: "ob-cell" }, [createElement("div", { className: "ob-player" }, [createElement("div", { className: "ob-avatar", text: initials(player) }), createElement("div", {}, [createElement("div", { className: "ob-player-name", text: player }), createElement("div", { className: "ob-player-sub", text: matchup }), createElement("div", { className: "ob-player-sub ob-player-pitcher", text: `vs ${pitcher}` })])])])) ;
}

function propCell(row) {
  return td(createElement("div", { className: "ob-cell" }, [createElement("div", {}, [createElement("div", { className: "ob-prop-title", text: propLabel(row) }), createElement("div", { className: "ob-prop-sub", text: text(row.recommendation || row.marketDisplay || row.market, "Research only") })])])) ;
}

function oddsCell(row) {
  const edge = row.finalEdgePercent || row.edge;
  const className = Number(edge) >= 5 ? "ob-edge-badge is-good" : Number(edge) >= 0 ? "ob-edge-badge is-watch" : "ob-edge-badge is-bad";
  return td(createElement("div", { className: "ob-cell ob-odds" }, [createElement("span", { text: formatOdds(row.americanOdds || row.odds) }), createElement("span", { className, text: signedPercent(edge) })]));
}

function hitCell(row, key) {
  const value = hitWindow(row, key);
  if (!value) return td(createElement("span", { text: "--" }), "ob-hit-cell is-empty");
  const pct = Number(value.pct ?? value.percent ?? value.rate ?? NaN);
  const tone = pct >= 80 ? "ob-pct--high" : pct >= 60 ? "ob-pct--mid" : "ob-pct--low";
  return td(createElement("span", { text: percent(pct), title: `${text(value.hits, "?")} of ${text(value.total, "?")}` }), `ob-hit-cell ${tone}`);
}

function renderLoading() { return createElement("div", { className: "ob-empty" }, [createElement("strong", { text: "Loading board" }), createElement("span", { text: "Fetching cached EdgeBoard payload." })]); }
function renderEmpty(title, copy) { return createElement("div", { className: "ob-empty" }, [createElement("strong", { text: title }), createElement("span", { text: copy })]); }
function activeFilterCount() { return [boardState.market, boardState.side, boardState.game, boardState.query, boardState.categoryTab !== "Today" ? boardState.categoryTab : ""].filter(Boolean).length; }
function availableGames() { return Array.from(new Set(boardState.rows.map(gameLabel).filter(Boolean))).sort(); }
function gameLabel(row) { const away = text(row.away || row.team, ""); const home = text(row.home || row.opponent, ""); return away && home ? `${away} @ ${home}` : text(row.game || row.matchup, ""); }
function hitWindow(row, key) { const hitRates = row.hitRates || row.hit_rate || row.hitRate || {}; return hitRates[key] || row[key] || null; }
function initials(value) { return text(value, "MLB").split(/\s+/).slice(0, 2).map((part) => part[0] || "").join("").toUpperCase() || "MLB"; }
function updatePropCount() { const count = document.getElementById("obPropCount"); if (count) count.textContent = `${boardState.filteredRows.length}/${boardState.rows.length} Props`; const badge = document.querySelector(".ob-filter-count"); if (badge) badge.textContent = String(activeFilterCount()); const clear = document.querySelector(".ob-clear-filter"); if (clear) clear.classList.toggle("is-hidden", activeFilterCount() === 0); }
function dispatchBoardStats() { const positive = boardState.filteredRows.filter((row) => Number(row.finalEdgePercent || row.edge || 0) > 0).length; const avgEdge = boardState.filteredRows.length ? boardState.filteredRows.reduce((sum, row) => sum + Number(row.finalEdgePercent || row.edge || 0), 0) / boardState.filteredRows.length : 0; dispatch("outlier:board-stats", { total: boardState.filteredRows.length, positive, avgEdge }); }
function todayIso() { const now = new Date(); const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000); return local.toISOString().slice(0, 10); }

export const __testHooks = { boardState, applyFilters, renderTable };
export const OUTLIER_MODULE_VERSION = "phase8-classic-visual-v1";
