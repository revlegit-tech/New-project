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
  number,
  todayIso,
} from "/outlier-shared.js";

const SPORT_TABS = ["NBA", "MLB", "Soccer", "NHL", "WNBA", "NCAAFB"];
const CATEGORY_TABS = ["Today", "Tomorrow", "Batter Props", "Pitcher Props", "Team Props", "Saved"];
const HIT_COLUMNS = [["l5", "L5"], ["l10", "L10"], ["l20", "L20"], ["h2h", "H2H"], ["season", "2026"], ["prevSeason", "2025"]];
const PAGE_SIZE = 120;

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
  sortKey: "edge",
  sortDir: "desc",
};

const SORT_LABELS = {
  player: "Player",
  proposition: "Proposition",
  line: "Line",
  odds: "Odds",
  ip: "IP",
  edge: "Edge",
  l5: "L5",
  l10: "L10",
  l20: "L20",
  h2h: "H2H",
  season: "2026",
  prevSeason: "2025",
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
      boardState.market = ""; boardState.side = ""; boardState.game = ""; boardState.query = ""; boardState.categoryTab = "Today"; boardState.sortKey = "edge"; boardState.sortDir = "desc"; redraw(); return;
    }
    if (action?.dataset.action === "toggleRail") { dispatch("outlier:rail-open", {}); return; }
    const sort = event.target.closest("[data-sort-key]");
    if (sort) { setSort(sort.dataset.sortKey); renderTable(); return; }
    const sport = event.target.closest("[data-sport]");
    if (sport) { boardState.sport = sport.dataset.sport === "MLB" ? "MLB" : boardState.sport; redraw(); return; }
    const category = event.target.closest("[data-category-tab]");
    if (category) { boardState.categoryTab = category.dataset.categoryTab || "Today"; applyFilters(); redraw(); return; }
    const rowButton = event.target.closest("[data-row-index]");
    if (rowButton) {
      openAdvancedStats(Number(rowButton.dataset.rowIndex));
    }
  };
  host.onkeydown = (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const rowButton = event.target.closest("[data-row-index]");
    if (!rowButton) return;
    event.preventDefault();
    openAdvancedStats(Number(rowButton.dataset.rowIndex));
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


async function openAdvancedStats(index) {
  const row = boardState.filteredRows[index];
  if (!row) return;

  try {
    const detailModule = await import("/outlier-detail.js");
    await detailModule.mount?.();
    dispatch("outlier:open-detail", { row, index });
  } catch (error) {
    console.error("Could not update Outlier rail", error);
  }

  try {
    await import("/prop-detail.js");
    const launcher = document.createElement("button");
    launcher.type = "button";
    launcher.textContent = "Advanced stats";
    launcher.style.display = "none";
    hydrateDetailDataset(launcher, row);
    document.body.appendChild(launcher);
    if (window.MlbPropDetail?.openFromButton) {
      await window.MlbPropDetail.openFromButton(launcher);
    } else {
      throw new Error("Prop detail module did not expose openFromButton");
    }
    launcher.remove();
  } catch (error) {
    console.error("Could not open advanced prop detail", error);
    dispatch("outlier:open-detail", { row, index });
  }
}

function hydrateDetailDataset(button, row) {
  const fields = {
    propId: row.id,
    date: row.date || boardState.date,
    player: row.player || row.playerName || row.team,
    team: row.team,
    opponent: row.opponent,
    market: row.market || row.baseMarket || row.originalMarket,
    line: row.line || row.propLine,
    odds: row.americanOdds || row.odds,
    book: row.book,
    decision: row.decisionLabel || row.recommendation,
    readiness: row.readinessLabel || row.readiness || row.confidence,
    confidence: row.confidence,
  };
  Object.entries(fields).forEach(([key, value]) => {
    const valueText = text(value, "");
    if (valueText) button.dataset[key] = valueText;
  });
  button.dataset.propDetailOpen = "1";
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
    params.set("limit", "500");
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
  });
  sortRows();
  dispatchBoardStats();
}

function categoryAllows(row) {
  const market = String(row.market || "").toLowerCase();
  if (boardState.nav === "EV+") return Number(edgeValue(row)) > 0;
  if (boardState.categoryTab === "Batter Props") return market.startsWith("batter_");
  if (boardState.categoryTab === "Pitcher Props") return market.startsWith("pitcher_");
  if (boardState.categoryTab === "Team Props") return market.startsWith("team_");
  if (boardState.categoryTab === "Saved") return false;
  return true;
}

function setSort(key) {
  if (!key) return;
  if (boardState.sortKey === key) {
    boardState.sortDir = boardState.sortDir === "asc" ? "desc" : "asc";
  } else {
    boardState.sortKey = key;
    boardState.sortDir = ["player", "proposition"].includes(key) ? "asc" : "desc";
  }
  sortRows();
}

function sortRows() {
  const key = boardState.sortKey || "edge";
  const dir = boardState.sortDir === "asc" ? 1 : -1;
  boardState.filteredRows.sort((a, b) => compareSortValues(sortValue(a, key), sortValue(b, key)) * dir);
}

function compareSortValues(a, b) {
  if (typeof a === "string" || typeof b === "string") return String(a || "").localeCompare(String(b || ""));
  const av = Number.isFinite(a) ? a : -Infinity;
  const bv = Number.isFinite(b) ? b : -Infinity;
  return av === bv ? 0 : av > bv ? 1 : -1;
}

function sortValue(row, key) {
  if (key === "player") return text(row.player || row.playerName || row.team, "").toLowerCase();
  if (key === "proposition") return propLabel(row).toLowerCase();
  if (key === "line") return numericValue(row.line ?? row.propLine);
  if (key === "odds") return numericValue(row.americanOdds ?? row.odds);
  if (key === "ip") return impliedValue(row);
  if (key === "edge") return edgeValue(row);
  if (["l5", "l10", "l20", "h2h", "season", "prevSeason"].includes(key)) return hitPercent(row, key);
  return 0;
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
    const sortText = `${SORT_LABELS[boardState.sortKey] || "Edge"} ${boardState.sortDir === "asc" ? "↑" : "↓"}`;
    meta.textContent = `${boardState.filteredRows.length} MLB props from EdgeBoard · sorted ${sortText} · ${cache}${boardState.requestId ? ` · ${boardState.requestId}` : ""}`;
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
  [["", ""], ["player", "Player"], ["proposition", "Proposition"], ["line", "Line"], ["odds", "Odds"], ["ip", "IP"], ...HIT_COLUMNS.map(([key, label]) => [key, label])].forEach(([key, label]) => {
    const th = document.createElement("th");
    th.append(key ? sortButton(key, label) : createElement("span", { text: label }));
    row.append(th);
  });
  head.append(row); return head;
}

function sortButton(key, label) {
  const active = boardState.sortKey === key;
  const arrow = !active ? "↕" : boardState.sortDir === "asc" ? "↑" : "↓";
  return createElement("button", { className: `ob-sort ${active ? "is-active" : ""}`, type: "button", dataset: { sortKey: key }, attrs: { "aria-label": `Sort by ${label}` } }, [
    createElement("span", { text: label }),
    createElement("i", { text: arrow, attrs: { "aria-hidden": "true" } }),
  ]);
}

function tbody(rows) {
  const body = document.createElement("tbody");
  rows.forEach((row, index) => body.append(dataRow(row, index)));
  return body;
}

function dataRow(row, index) {
  const tr = createElement("tr", { dataset: { rowIndex: index }, attrs: { tabindex: "0", title: "Open advanced prop statistics" } });
  tr.append(
    td(createElement("button", { className: "ob-plus", type: "button", text: "+", attrs: { "aria-label": "Save prop" } })),
    playerCell(row), propCell(row),
    td(createElement("div", { className: "ob-cell ob-number", text: text(row.line ?? row.propLine) })),
    oddsCell(row),
    td(createElement("div", { className: "ob-cell ob-ip", text: percent(impliedValue(row)) })),
    ...HIT_COLUMNS.map(([key]) => hitCell(row, key))
  );
  return tr;
}

function td(child, className = "") { const node = createElement("td", { className }); if (child) node.append(child); return node; }

function playerCell(row) {
  const player = text(row.player || row.playerName || row.team, "MLB");
  const matchup = gameLabel(row) || "Matchup unavailable";
  const pitcher = text(row.pitcher || row.probablePitcher, "Starter pending");
  return td(createElement("div", { className: "ob-cell" }, [createElement("div", { className: "ob-player" }, [createElement("div", { className: "ob-avatar", text: initials(player) }), createElement("div", {}, [createElement("div", { className: "ob-player-name", text: player }), createElement("div", { className: "ob-player-sub", text: matchup }), createElement("div", { className: "ob-player-sub ob-player-pitcher", text: `vs ${pitcher}` })])])]));
}

function propCell(row) {
  return td(createElement("div", { className: "ob-cell" }, [createElement("div", {}, [createElement("div", { className: "ob-prop-title", text: propLabel(row) }), createElement("div", { className: "ob-prop-sub", text: text(row.recommendation || row.marketDisplay || row.market, "Research only") })])]));
}

function oddsCell(row) {
  const edge = edgeValue(row);
  const className = edge >= 5 ? "ob-edge-badge is-good" : edge >= 0 ? "ob-edge-badge is-watch" : "ob-edge-badge is-bad";
  return td(createElement("div", { className: "ob-cell ob-odds" }, [createElement("span", { text: formatOdds(row.americanOdds ?? row.odds) }), createElement("span", { className, text: signedPercent(edge) })]));
}

function hitCell(row, key) {
  const pct = hitPercent(row, key);
  if (!Number.isFinite(pct)) return td(createElement("span", { text: "--" }), "ob-hit-cell is-empty");
  const tone = pct >= 80 ? "ob-pct--high" : pct >= 60 ? "ob-pct--mid" : "ob-pct--low";
  const title = hitTitle(row, key, pct);
  return td(createElement("span", { text: percent(pct), title }), `ob-hit-cell ${tone}`);
}

function hitTitle(row, key, pct) {
  const value = hitWindow(row, key);
  if (value && typeof value === "object") {
    const hits = value.hits ?? value.successes ?? value.made ?? value.count;
    const total = value.total ?? value.attempts ?? value.samples ?? value.n;
    if (hits !== undefined && total !== undefined) return `${hits} of ${total}`;
  }
  return `${SORT_LABELS[key] || key}: ${percent(pct)}`;
}

function renderLoading() { return createElement("div", { className: "ob-empty" }, [createElement("strong", { text: "Loading board" }), createElement("span", { text: "Fetching cached EdgeBoard payload." })]); }
function renderEmpty(title, copy) { return createElement("div", { className: "ob-empty" }, [createElement("strong", { text: title }), createElement("span", { text: copy })]); }
function activeFilterCount() { return [boardState.market, boardState.side, boardState.game, boardState.query, boardState.categoryTab !== "Today" ? boardState.categoryTab : ""].filter(Boolean).length; }
function availableGames() { return Array.from(new Set(boardState.rows.map(gameLabel).filter(Boolean))).sort(); }
function gameLabel(row) { const away = text(row.away || row.team, ""); const home = text(row.home || row.opponent, ""); return away && home ? `${away} @ ${home}` : text(row.game || row.matchup, ""); }

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

function hitPercent(row, key) { return normalizePercent(hitWindow(row, key)); }
function normalizePercent(value) {
  if (value === null || value === undefined || value === "") return NaN;
  if (typeof value === "object") return normalizePercent(value.pct ?? value.percent ?? value.rate ?? value.value);
  if (typeof value === "string") {
    const parsed = Number(value.replace("%", "").trim());
    if (!Number.isFinite(parsed)) return NaN;
    return parsed <= 1 && parsed >= -1 ? parsed * 100 : parsed;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return NaN;
  return parsed <= 1 && parsed >= -1 ? parsed * 100 : parsed;
}
function numericValue(value) { const parsed = number(value, NaN); return Number.isFinite(parsed) ? parsed : -Infinity; }
function edgeValue(row) { return numericValue(row.finalEdgePercent ?? row.edge ?? row.edgePercent); }
function impliedValue(row) { return numericValue(row.sportsbookImpliedPercent ?? row.impliedProbability ?? row.impliedPercent ?? row.ip); }
function initials(value) { return text(value, "MLB").split(/\s+/).slice(0, 2).map((part) => part[0] || "").join("").toUpperCase() || "MLB"; }
function updatePropCount() { const count = document.getElementById("obPropCount"); if (count) count.textContent = `${boardState.filteredRows.length}/${boardState.rows.length} Props`; const badge = document.querySelector(".ob-filter-count"); if (badge) badge.textContent = String(activeFilterCount()); const clear = document.querySelector(".ob-clear-filter"); if (clear) clear.classList.toggle("is-hidden", activeFilterCount() === 0); }
function dispatchBoardStats() { const positive = boardState.filteredRows.filter((row) => Number(edgeValue(row)) > 0).length; const avgEdge = boardState.filteredRows.length ? boardState.filteredRows.reduce((sum, row) => sum + Number(edgeValue(row) || 0), 0) / boardState.filteredRows.length : 0; dispatch("outlier:board-stats", { total: boardState.filteredRows.length, positive, avgEdge }); }

export const __testHooks = { boardState, applyFilters, renderTable, sortValue, hitPercent };
export const OUTLIER_MODULE_VERSION = "post-phase10-advanced-board-v1";
