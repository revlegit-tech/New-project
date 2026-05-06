(() => {
  const MARKETS = [
    ["", "All"],
    ["batter_total_bases", "Batter Bases"],
    ["batter_hits", "Batter Hits"],
    ["batter_home_runs", "Home Runs"],
    ["pitcher_strikeouts", "Pitcher Ks"],
    ["pitcher_hits_allowed", "Hits Allowed"],
    ["pitcher_earned_runs", "Earned Runs"],
    ["team_total_runs", "Team Runs"],
    ["team_first_to_score", "Team First"],
  ];

  const SPORT_TABS = ["NBA", "MLB", "Soccer", "NHL", "WNBA", "NCAAFB"];
  const NAV_ITEMS = ["Insights", "Popular", "Games", "Props", "EV+", "Boosts", "Arbitrage", "Middle Bets"];
  const CATEGORY_TABS = ["Today", "Tomorrow", "Batter Props", "Pitcher Props", "Team Props", "Saved"];
  const HIT_COLUMNS = [
    ["L5", "L5"],
    ["L10", "L10"],
    ["L20", "L20"],
    ["H2H", "H2H"],
    ["season", "2026"],
    ["prevSeason", "2025"],
  ];
  const PAGE_SIZE = 32;

  const STAT_TABS = [
    { label: "TB", market: "batter_total_bases", col: "totalBases" },
    { label: "H", market: "batter_hits", col: "hits" },
    { label: "H+R+RBI", market: "_computed_hrbi", col: null },
    { label: "HR", market: "batter_home_runs", col: "homeRuns" },
    { label: "RBI", market: "batter_rbis", col: "rbi" },
    { label: "R", market: "batter_runs", col: "runs" },
    { label: "SB", market: "batter_stolen_bases", col: "stolenBases" },
    { label: "1B", market: "_computed_1b", col: null },
    { label: "2B", market: "batter_doubles", col: "doubles" },
    { label: "3B", market: "batter_triples", col: "triples" },
    { label: "BB", market: "batter_walks", col: "baseOnBalls" },
    { label: "SO", market: "batter_strikeouts", col: "strikeOuts" },
    { label: "FS (UD)", market: "team_first_to_score", col: "firstToScore" },
  ];

  const DETAIL_PERIODS = [
    ["L5", "L5"],
    ["L10", "L10"],
    ["L20", "L20"],
    ["H2H", "H2H"],
    ["season", "2026"],
    ["prevSeason", "2025"],
  ];

  const TEAM_COLORS = {
    ARI: "#a71930", ATH: "#003831", ATL: "#ce1141", BAL: "#df4601", BOS: "#bd3039",
    CHC: "#0e3386", CWS: "#c4ced4", CIN: "#c6011f", CLE: "#e31937", COL: "#33006f",
    DET: "#0c2340", HOU: "#eb6e1f", KC: "#004687", LAA: "#ba0021", LAD: "#005a9c",
    MIA: "#00a3e0", MIL: "#ffc52f", MIN: "#002b5c", NYM: "#ff5910", NYY: "#0c2340",
    OAK: "#003831", PHI: "#e81828", PIT: "#fdb827", SD: "#2f241d", SEA: "#0c2c56",
    SF: "#fd5a1e", STL: "#c41e3a", TB: "#8fbce6", TEX: "#003278", TOR: "#134a8e",
    WSH: "#ab0003", MLB: "#18d99c",
  };

  const PITCH_COLORS = {
    FA: "#3b82f6", FF: "#3b82f6", SI: "#eab308", FT: "#eab308",
    SL: "#f97316", ST: "#f97316", CU: "#ef4444", KC: "#ef4444",
    CH: "#6b7280", FC: "#a855f7", CT: "#a855f7", FS: "#14b8a6",
  };

  const FALLBACK_ROWS = [
    {
      player: "Josh Bell",
      team: "MIN",
      opponent: "WSH",
      pitcher: "Miles Mikolas",
      market: "batter_total_bases",
      marketDisplay: "Batter Bases",
      rawLabel: "Under",
      line: "1.5",
      americanOdds: "-119",
      finalProbabilityPercent: "64.0",
      sportsbookImpliedPercent: "54.3",
      finalEdgePercent: "9.7",
      confidence: "Medium-High",
      recommendation: "Positive edge",
      hitRates: {
        L5: { hits: 5, total: 5, pct: 100 },
        L10: { hits: 10, total: 10, pct: 100 },
        L20: { hits: 17, total: 20, pct: 85 },
        H2H: { hits: 4, total: 4, pct: 100 },
        season: { hits: 22, total: 30, pct: 73 },
        prevSeason: { hits: 86, total: 130, pct: 66 },
      },
    },
    {
      player: "Kerry Carpenter",
      team: "BOS",
      opponent: "DET",
      pitcher: "Casey Mize",
      market: "batter_hits",
      marketDisplay: "Batter Hits",
      rawLabel: "Over",
      line: "0.5",
      americanOdds: "-171",
      finalProbabilityPercent: "71.4",
      sportsbookImpliedPercent: "63.1",
      finalEdgePercent: "8.3",
      confidence: "Medium",
      recommendation: "Positive edge",
      hitRates: {
        L5: { hits: 5, total: 5, pct: 100 },
        L10: { hits: 9, total: 10, pct: 90 },
        L20: { hits: 17, total: 20, pct: 85 },
        H2H: { hits: 3, total: 4, pct: 75 },
        season: { hits: 26, total: 32, pct: 81 },
        prevSeason: null,
      },
    },
    {
      player: "Ryan Jeffers",
      team: "MIN",
      opponent: "WSH",
      pitcher: "MacKenzie Gore",
      market: "batter_hits",
      marketDisplay: "Batter Hits",
      rawLabel: "Under",
      line: "0.5",
      americanOdds: "-457",
      finalProbabilityPercent: "81.0",
      sportsbookImpliedPercent: "82.1",
      finalEdgePercent: "-1.1",
      confidence: "Low",
      recommendation: "No clear edge",
      missingData: ["Lineup/injury status should be confirmed"],
      hitRates: {
        L5: { hits: 4, total: 5, pct: 80 },
        L10: { hits: 8, total: 10, pct: 80 },
        L20: { hits: 17, total: 20, pct: 85 },
        H2H: null,
        season: { hits: 25, total: 31, pct: 81 },
        prevSeason: null,
      },
    },
  ];

  const state = {
    rows: [],
    selected: null,
    date: today(),
    nav: "Props",
    sport: "MLB",
    market: "",
    side: "",
    game: "",
    sortKey: "L10",
    sortDir: "desc",
    minEdge: 0,
    query: "",
    showAlt: false,
    savedOnly: false,
    categoryTab: "Today",
    saved: new Set(loadSavedKeys()),
    loading: false,
    source: "loading",
    hitRateSource: "",
    detailStatTab: 0,
    detailPeriod: "L10",
    detailChartMode: "bar",
    activeLine: "",
    activeSide: "",
    activeOdds: "",
    lineDropdownOpen: false,
    activePitchFilter: "All",
    heatmapPitcherHand: "ALL",
    heatmapBatterHand: "ALL",
    detail: {
      key: "",
      loadingCard: false,
      loadingLogs: false,
      loadingGame: false,
      propCard: null,
      gameLogs: [],
      gameContext: null,
      errors: {},
    },
  };

  function $(selector, root = document) {
    return root.querySelector(selector);
  }

  function today() {
    const date = new Date();
    const offset = date.getTimezoneOffset();
    const local = new Date(date.getTime() - offset * 60000);
    return local.toISOString().slice(0, 10);
  }

  function addDays(dateLabel, days) {
    const base = dateLabel ? new Date(`${dateLabel}T12:00:00`) : new Date();
    base.setDate(base.getDate() + days);
    const offset = base.getTimezoneOffset();
    const local = new Date(base.getTime() - offset * 60000);
    return local.toISOString().slice(0, 10);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function clean(value) {
    return String(value ?? "").trim();
  }

  function normalizeMarket(value) {
    return clean(value).toLowerCase().replaceAll("-", "_").replaceAll(" ", "_").replace(/_+/g, "_");
  }

  function baseMarket(value) {
    const market = normalizeMarket(value);
    return market.endsWith("_alt") ? market.slice(0, -4) : market;
  }

  function normalizeName(value) {
    return clean(value)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function loadSavedKeys() {
    try {
      const raw = window.localStorage.getItem("baseballEdgeSavedProps");
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch {
      return [];
    }
  }

  function storeSavedKeys() {
    try {
      window.localStorage.setItem("baseballEdgeSavedProps", JSON.stringify([...state.saved]));
    } catch {
      /* Saving is best effort when localStorage is unavailable. */
    }
  }

  function signed(value, suffix = "%") {
    const n = number(value);
    return `${n >= 0 ? "+" : ""}${n.toFixed(1)}${suffix}`;
  }

  function percent(value) {
    return `${number(value).toFixed(0)}%`;
  }

  function formatOdds(value) {
    const text = clean(value);
    if (!text) return "--";
    const n = Number(text);
    if (!Number.isFinite(n)) return text;
    const rounded = Math.round(n);
    return rounded > 0 ? `+${rounded}` : String(rounded);
  }

  function marketLabel(value) {
    const target = baseMarket(value);
    const found = MARKETS.find(([key]) => key === target);
    return found ? found[1] : clean(value).replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function sideLabel(row) {
    const raw = clean(row.rawLabel);
    if (/under/i.test(raw)) return "Under";
    if (/over/i.test(raw)) return "Over";
    if (/\d+\s*\+/.test(raw)) return "Over";
    const display = clean(row.marketDisplay);
    if (/under/i.test(display)) return "Under";
    if (/over/i.test(display)) return "Over";
    return "Under";
  }

  function canonicalLine(row) {
    const parsed = Number(clean(row.line));
    return Number.isFinite(parsed) ? String(parsed) : clean(row.line);
  }

  function canonicalSide(row) {
    const raw = clean(row.rawLabel);
    return raw ? raw.toLowerCase() : sideLabel(row).toLowerCase();
  }

  function hitRateKey(row) {
    return [
      normalizeName(row.player),
      normalizeMarket(row.market),
      clean(row.team).toUpperCase(),
      clean(row.opponent).toUpperCase(),
      canonicalLine(row),
      canonicalSide(row),
    ].join("|");
  }

  function proposition(row) {
    const side = sideLabel(row);
    const line = clean(row.line) || "--";
    return `${side} ${line} ${marketLabel(row.market || row.marketDisplay)}`;
  }

  function initials(name) {
    const parts = clean(name).split(/\s+/).filter(Boolean);
    if (!parts.length) return "MLB";
    return parts.slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  }

  function selectedKey(row) {
    return [row.player, row.market, row.team, row.opponent, row.line, row.americanOdds].map(clean).join("|");
  }

  function isAltMarket(row) {
    return normalizeMarket(row.market).endsWith("_alt") || /alt|ladder|\+/i.test(`${row.marketDisplay} ${row.rawLabel}`);
  }

  function rowSignals(row) {
    return {
      ip: clamp(Math.round(number(row.sportsbookImpliedPercent, 50)), 1, 99),
      model: clamp(Math.round(number(row.finalProbabilityPercent, 50)), 1, 99),
      edge: number(row.finalEdgePercent, 0),
    };
  }

  function missingText(row) {
    const value = row.missingData;
    if (Array.isArray(value)) return value.map(clean).join(" | ");
    return clean(value);
  }

  function shouldWarn(row) {
    const missing = missingText(row).toLowerCase();
    return missing.includes("injury") || clean(row.confidence).toLowerCase() === "low";
  }

  function warningText(row) {
    if (missingText(row).toLowerCase().includes("injury")) {
      return "Team injuries may impact playing time.";
    }
    return "Low-confidence data may impact this prop.";
  }

  function gameLabel(row) {
    const team = clean(row.team);
    const opponent = clean(row.opponent);
    return team && opponent ? `${team} @ ${opponent}` : "";
  }

  function comparableRow(row) {
    return [
      row.player,
      row.team,
      row.opponent,
      row.pitcher,
      row.marketDisplay,
      row.market,
      row.rawLabel,
      row.recommendation,
      missingText(row),
    ].map(clean).join(" ").toLowerCase();
  }

  function hitWindow(row, key) {
    const rates = row.hitRates || {};
    const value = rates[key];
    return value && Number.isFinite(Number(value.pct)) ? value : null;
  }

  function hitPct(row, key) {
    const value = hitWindow(row, key);
    return value ? number(value.pct, -1) : -1;
  }

  function activeFilterCount() {
    return [
      state.market,
      state.side,
      state.game,
      state.query,
      state.showAlt ? "all-lines" : "",
      state.savedOnly ? "saved" : "",
      state.categoryTab && !["Today", "Tomorrow"].includes(state.categoryTab) ? state.categoryTab : "",
      state.minEdge > 0 ? "edge" : "",
    ].filter(Boolean).length;
  }

  function availableGames() {
    return [...new Set(state.rows.map(gameLabel).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  }

  function categoryMatches(row) {
    const market = normalizeMarket(row.market);
    if (state.categoryTab === "Batter Props") return market.startsWith("batter_");
    if (state.categoryTab === "Pitcher Props") return market.startsWith("pitcher_");
    if (state.categoryTab === "Team Props") return market.startsWith("team_") || ["moneyline", "run_line", "game_total_runs", "team_first_to_score"].includes(market);
    if (state.categoryTab === "Saved") return state.saved.has(selectedKey(row));
    return true;
  }

  function filteredRows() {
    const query = state.query.toLowerCase();
    const targetMarket = state.market;
    let rows = state.rows.filter((row) => {
      if (state.savedOnly && !state.saved.has(selectedKey(row))) return false;
      if (!categoryMatches(row)) return false;
      if (!state.showAlt && isAltMarket(row)) return false;
      if (targetMarket && baseMarket(row.market) !== targetMarket) return false;
      if (state.side && sideLabel(row).toLowerCase() !== state.side) return false;
      if (state.game && gameLabel(row) !== state.game) return false;
      if (number(row.finalEdgePercent) < state.minEdge) return false;
      if (query && !comparableRow(row).includes(query)) return false;
      return true;
    });

    rows = rows.sort(compareRows);
    return rows;
  }

  function sortValue(row, key) {
    if (key === "player") return clean(row.player || row.team).toLowerCase();
    if (key === "proposition") return proposition(row).toLowerCase();
    if (key === "line") return number(row.line, -999);
    if (key === "odds") return number(row.americanOdds, -99999);
    if (key === "ip") return number(row.sportsbookImpliedPercent, -1);
    if (key === "edge") return number(row.finalEdgePercent, -999);
    if (HIT_COLUMNS.some(([hitKey]) => hitKey === key)) return hitPct(row, key);
    return number(row.finalEdgePercent, 0);
  }

  function compareRows(a, b) {
    const av = sortValue(a, state.sortKey);
    const bv = sortValue(b, state.sortKey);
    let result = 0;
    if (typeof av === "string" || typeof bv === "string") {
      result = String(av).localeCompare(String(bv));
    } else {
      result = av - bv;
    }
    if (result === 0) {
      result = number(a.finalEdgePercent) - number(b.finalEdgePercent);
    }
    return state.sortDir === "desc" ? -result : result;
  }

  async function getJson(path, options = {}) {
    const response = await fetch(path, options);
    const text = await response.text();
    let payload = {};
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`Non-JSON response: ${text.slice(0, 120)}`);
    }
    if (!response.ok) throw new Error(payload.error || `Request failed ${response.status}`);
    return payload;
  }

  async function loadBoard() {
    state.loading = true;
    state.source = "loading";
    state.hitRateSource = "";
    renderBoard();

    const params = new URLSearchParams({
      season: "2026",
      date: state.date,
      market: state.market || "",
      limit: "500",
    });

    try {
      const payload = await getJson(`/api/playerboard?${params.toString()}`);
      let rows = Array.isArray(payload.top) ? payload.top : [];
      state.source = rows.length ? (payload.cacheHit ? "saved snapshot" : "live playerboard") : "demo fallback";

      if (rows.length) {
        try {
          const hitPayload = await getJson(`/api/player/hit-rates?${params.toString()}`);
          rows = mergeHitRates(rows, Array.isArray(hitPayload.rows) ? hitPayload.rows : []);
          state.hitRateSource = hitPayload.rowsLoaded ? "hit-rate cache" : "hit-rate pending";
        } catch (error) {
          console.error(error);
          state.hitRateSource = "hit-rate unavailable";
        }
      }

      state.rows = rows.length ? rows : FALLBACK_ROWS;
      state.selected = state.rows[0] || null;
    } catch (error) {
      console.error(error);
      state.rows = FALLBACK_ROWS;
      state.source = "demo fallback";
      state.hitRateSource = "demo hit rates";
      state.selected = state.rows[0] || null;
    } finally {
      state.loading = false;
      render();
    }
  }

  function mergeHitRates(rows, hitRows) {
    const byKey = new Map();
    hitRows.forEach((item) => {
      if (!item || typeof item !== "object") return;
      if (clean(item.key)) byKey.set(clean(item.key), item);
      byKey.set(hitRateKey(item), item);
    });

    return rows.map((row) => {
      const match = byKey.get(hitRateKey(row));
      if (!match) return { ...row, hitRates: row.hitRates || {} };
      return {
        ...row,
        hitRates: {
          L5: match.L5 || null,
          L10: match.L10 || null,
          L20: match.L20 || null,
          H2H: match.H2H || null,
          season: match.season || null,
          prevSeason: match.prevSeason || null,
        },
      };
    });
  }

  function createShell() {
    document.body.classList.add("outlier-mode");
    const main = $("main.app-shell") || $("main") || document.body;
    if ($("#outlierApp")) return;

    const root = document.createElement("section");
    root.id = "outlierApp";
    root.className = "outlier-app";
    main.prepend(root);

    render();
    root.addEventListener("click", onClick);
    root.addEventListener("input", onInput);
    root.addEventListener("change", onChange);
    loadBoard();
  }

  function render() {
    const root = $("#outlierApp");
    if (!root) return;

    const rows = filteredRows();
    const positive = rows.filter((row) => number(row.finalEdgePercent) > 0).length;
    const avgEdge = rows.length
      ? rows.reduce((sum, row) => sum + number(row.finalEdgePercent), 0) / rows.length
      : 0;
    const mainContent = state.nav === "PropDetail" && state.selected
      ? renderPropDetail(state.selected)
      : renderPropsMain(rows);

    root.innerHTML = `
      ${renderSidebar(rows.length, positive, avgEdge)}
      <main class="ob-main">
        ${mainContent}
      </main>
      ${renderRightRail(rows)}
    `;
    afterRender();
  }

  function renderPropsMain(rows) {
    return `
      ${renderHero(rows.length, state.rows.length)}
      <section class="ob-board-wrap">
        <div class="ob-board">
          ${renderBoardMeta(rows.length)}
          ${state.loading ? renderLoading() : renderTable(rows)}
        </div>
      </section>
    `;
  }

  function afterRender() {
    if (state.nav === "PropDetail") {
      window.requestAnimationFrame(drawDetailCanvases);
    }
  }

  function renderSidebar(total, positive, avgEdge) {
    return `
      <aside class="ob-sidebar" aria-label="Application navigation">
        <div class="ob-brand">
          <div class="ob-brand-lockup">
            <div class="ob-mark" aria-hidden="true"></div>
            <div>
              <strong>Baseball Edge</strong>
              <span>MLB props</span>
            </div>
          </div>
          <div class="ob-season-chip">2026</div>
        </div>

        <nav class="ob-nav">
          ${NAV_ITEMS.map((item) => `
            <button type="button" class="${state.nav === item ? "is-active" : ""}" data-nav="${escapeHtml(item)}" aria-label="${escapeHtml(item)}">
              <span class="ob-nav-icon" aria-hidden="true"></span>
              <span>${escapeHtml(item)}</span>
            </button>
          `).join("")}
        </nav>

        <div class="ob-sidebar-footer">
          <div class="ob-mini-metric">
            <span>Positive edges</span>
            <strong>${escapeHtml(String(positive))}</strong>
            <span>${escapeHtml(total ? signed(avgEdge) : "+0.0%")} avg edge</span>
          </div>
        </div>
      </aside>
    `;
  }

  function renderHero(visible, total) {
    const filterCount = activeFilterCount();
    const games = availableGames();
    return `
      <header class="ob-hero">
        <div class="ob-topbar">
          <div>
            <h1 class="ob-title">Props</h1>
          </div>
          <div class="ob-date-wrap">
            <input class="ob-input ob-date" type="date" value="${escapeHtml(state.date)}" data-control="date" aria-label="Board date" />
            <button class="ob-load-button" type="button" data-action="reload">Load Board</button>
          </div>
        </div>

        <div class="ob-sport-row" role="tablist" aria-label="Sports">
          ${SPORT_TABS.map((tab) => `
            <button type="button" class="ob-tab ${state.sport === tab ? "is-active" : ""}" data-sport="${escapeHtml(tab)}">${escapeHtml(tab)}</button>
          `).join("")}
        </div>

        <div class="ob-filter-shell" aria-label="Prop filters">
          <div class="ob-filter-left">
            <button class="ob-filter-button is-primary" type="button" aria-label="Active filters">
              <span class="ob-filter-count">${escapeHtml(String(filterCount))}</span> Filters
            </button>
            <button class="ob-icon-button ob-clear-filter ${filterCount ? "" : "is-hidden"}" type="button" data-action="clearFilters" aria-label="Clear filters">x</button>
            <button class="ob-filter-button is-saved ${state.savedOnly ? "is-active" : ""}" type="button" data-action="toggleSaved">Saved</button>
          </div>

          <div class="ob-filter-controls">
            <select class="ob-select" data-control="market" aria-label="Propositions">
              ${MARKETS.map(([value, label], index) => `<option value="${escapeHtml(value)}" ${state.market === value ? "selected" : ""}>${escapeHtml(index === 0 ? "Propositions" : label)}</option>`).join("")}
            </select>
            <input class="ob-input ob-search" type="search" value="${escapeHtml(state.query)}" placeholder="Players" data-control="query" aria-label="Players" />
            <select class="ob-select" data-control="game" aria-label="Games">
              <option value="" ${state.game === "" ? "selected" : ""}>Games</option>
              ${games.map((game) => `<option value="${escapeHtml(game)}" ${state.game === game ? "selected" : ""}>${escapeHtml(game)}</option>`).join("")}
            </select>
            <select class="ob-select" data-control="side" aria-label="Over under">
              <option value="" ${state.side === "" ? "selected" : ""}>Over / Under</option>
              <option value="over" ${state.side === "over" ? "selected" : ""}>Over</option>
              <option value="under" ${state.side === "under" ? "selected" : ""}>Under</option>
            </select>
          </div>

          <div class="ob-filter-right">
            <button class="ob-icon-button" type="button" data-action="columnConfig" aria-label="Column settings">Cols</button>
            <button class="ob-toggle ${state.showAlt ? "is-on" : ""}" type="button" data-action="toggleAlt" aria-pressed="${state.showAlt}">
              <span>Show all lines</span>
              <span class="ob-toggle-dot" aria-hidden="true"></span>
            </button>
            <span class="ob-rail-note" id="obPropCount">${escapeHtml(String(visible))}/${escapeHtml(String(total))} Props</span>
          </div>
        </div>

        ${renderCategoryTabs()}
      </header>
    `;
  }

  function renderCategoryTabs() {
    return `
      <div class="ob-category-tabs" role="tablist" aria-label="Prop categories">
        ${CATEGORY_TABS.map((tab) => `
          <button type="button" class="${state.categoryTab === tab ? "is-active" : ""}" data-category-tab="${escapeHtml(tab)}">${escapeHtml(tab)}</button>
        `).join("")}
      </div>
    `;
  }

  function renderBoardMeta(visible) {
    const source = [state.source, state.hitRateSource].filter(Boolean).join(" + ");
    return `
      <div class="ob-board-meta">
        <span><strong>${escapeHtml(String(visible))}</strong> MLB props ${source ? `from ${escapeHtml(source)}` : ""}</span>
        <span>${escapeHtml(state.date)} slate</span>
      </div>
    `;
  }

  function renderLoading() {
    const rows = Array.from({ length: 8 }, (_, index) => `
      <tr class="ob-skeleton-row" aria-hidden="true">
        <td><span class="ob-skeleton ob-skel-dot"></span></td>
        <td><span class="ob-skeleton ob-skel-avatar"></span><span class="ob-skeleton ob-skel-text wide"></span><span class="ob-skeleton ob-skel-text small"></span></td>
        <td><span class="ob-skeleton ob-skel-text wide"></span><span class="ob-skeleton ob-skel-text mid"></span></td>
        <td><span class="ob-skeleton ob-skel-pill"></span></td>
        <td><span class="ob-skeleton ob-skel-pill"></span></td>
        <td><span class="ob-skeleton ob-skel-pill"></span></td>
        ${HIT_COLUMNS.map(() => `<td><span class="ob-skeleton ob-skel-pill"></span></td>`).join("")}
      </tr>
    `).join("");
    return `
      <div class="ob-table-scroll">
        <table class="ob-table ob-loading-table">
          <colgroup>
            <col class="ob-col-action" />
            <col class="ob-col-player" />
            <col class="ob-col-prop" />
            <col class="ob-col-line" />
            <col class="ob-col-odds" />
            <col class="ob-col-ip" />
            <col class="ob-col-hit" />
            <col class="ob-col-hit" />
            <col class="ob-col-hit" />
            <col class="ob-col-hit" />
            <col class="ob-col-hit" />
            <col class="ob-col-hit" />
          </colgroup>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="ob-mobile-cards ob-mobile-skeletons">
        ${Array.from({ length: 5 }, () => `
          <article class="ob-mobile-card">
            <span class="ob-skeleton ob-skel-text wide"></span>
            <span class="ob-skeleton ob-skel-text mid"></span>
            <span class="ob-skeleton ob-skel-block"></span>
          </article>
        `).join("")}
      </div>
    `;
  }

  function sortableHeader(label, key) {
    const active = state.sortKey === key;
    const dir = active ? state.sortDir : "";
    return `
      <button class="ob-sort ${active ? "is-active" : ""}" type="button" data-sort-key="${escapeHtml(key)}">
        <span>${escapeHtml(label)}</span>
        <i aria-hidden="true">${dir === "asc" ? "^" : active ? "v" : ""}</i>
      </button>
    `;
  }

  function renderTable(rows) {
    if (!rows.length) {
      return `
        <div class="ob-empty">
          <strong>No props match the current filters.</strong>
          <span>Adjust proposition, player, game, side, or saved status.</span>
        </div>
      `;
    }

    const pageRows = rows.slice(0, PAGE_SIZE);
    return `
      <div class="ob-table-scroll">
        <table class="ob-table">
          <colgroup>
            <col class="ob-col-action" />
            <col class="ob-col-player" />
            <col class="ob-col-prop" />
            <col class="ob-col-line" />
            <col class="ob-col-odds" />
            <col class="ob-col-ip" />
            <col class="ob-col-hit" />
            <col class="ob-col-hit" />
            <col class="ob-col-hit" />
            <col class="ob-col-hit" />
            <col class="ob-col-hit" />
            <col class="ob-col-hit" />
          </colgroup>
          <thead>
            <tr>
              <th><span></span></th>
              <th>${sortableHeader("Player", "player")}</th>
              <th>${sortableHeader("Proposition", "proposition")}</th>
              <th>${sortableHeader("Line", "line")}</th>
              <th>${sortableHeader("Odds", "odds")}</th>
              <th>${sortableHeader("IP", "ip")}</th>
              ${HIT_COLUMNS.map(([key, label]) => `<th>${sortableHeader(label, key)}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${renderTableRows(pageRows)}
          </tbody>
        </table>
      </div>
      <div class="ob-mobile-cards">
        ${pageRows.map(renderMobileCard).join("")}
      </div>
    `;
  }

  function renderTableRows(pageRows) {
    const warned = new Set();
    return pageRows.map((row, index) => {
      const warningKey = [clean(row.player), clean(row.team), clean(row.opponent)].join("|");
      const warning = shouldWarn(row) && !warned.has(warningKey)
        ? (warned.add(warningKey), renderWarningRow(row))
        : "";
      return `${warning}${renderRow(row, index)}`;
    }).join("");
  }

  function renderWarningRow(row) {
    return `
      <tr class="ob-row-warning">
        <td colspan="12"><span class="ob-warn-icon">!</span>${escapeHtml(warningText(row))}</td>
      </tr>
    `;
  }

  function renderRow(row, index) {
    const signals = rowSignals(row);
    const selected = state.selected && selectedKey(state.selected) === selectedKey(row);
    const saved = state.saved.has(selectedKey(row));
    const matchup = gameLabel(row) || "Matchup unavailable";
    const pitcher = clean(row.pitcher) ? `vs ${clean(row.pitcher)}` : "Starter pending";

    return `
      <tr class="${selected ? "is-selected" : ""}" data-row-index="${index}">
        <td><div class="ob-cell"><button class="ob-plus ${saved ? "is-saved" : ""}" type="button" data-save-key="${escapeHtml(selectedKey(row))}" aria-label="${saved ? "Unsave prop" : "Save prop"}">${saved ? "-" : "+"}</button></div></td>
        <td>
          <div class="ob-cell">
            <div class="ob-player">
              <div class="ob-avatar">${escapeHtml(initials(row.player || row.team))}</div>
              <div>
                <div class="ob-player-name">${escapeHtml(clean(row.player) || clean(row.team) || "MLB")}</div>
                <div class="ob-player-sub">${escapeHtml(matchup)}</div>
                <div class="ob-player-sub ob-player-pitcher">${escapeHtml(pitcher)}</div>
              </div>
            </div>
          </div>
        </td>
        <td>
          <div class="ob-cell">
            <div>
              <div class="ob-prop-title">${escapeHtml(proposition(row))}</div>
              <div class="ob-prop-sub">${escapeHtml(clean(row.recommendation) || marketLabel(row.market))}</div>
            </div>
          </div>
        </td>
        <td><div class="ob-cell ob-number">${escapeHtml(clean(row.line) || "--")}</div></td>
        <td><div class="ob-cell ob-odds"><span>${escapeHtml(formatOdds(row.americanOdds))}</span><span class="${edgeClass(signals.edge)}">${escapeHtml(signed(signals.edge))}</span></div></td>
        <td><div class="ob-cell ob-ip">${escapeHtml(percent(signals.ip))}</div></td>
        ${HIT_COLUMNS.map(([key]) => renderHitCell(row, key)).join("")}
      </tr>
    `;
  }

  function edgeClass(edge) {
    if (edge >= 5) return "ob-edge-badge is-good";
    if (edge >= 0) return "ob-edge-badge is-watch";
    return "ob-edge-badge is-bad";
  }

  function renderHitCell(row, key) {
    const value = hitWindow(row, key);
    if (!value) {
      return `<td class="ob-hit-cell is-empty"><span>--</span></td>`;
    }
    const pct = number(value.pct, 0);
    const tone = pct >= 80 ? "ob-pct--high" : pct >= 60 ? "ob-pct--mid" : "ob-pct--low";
    const title = `${value.hits} of ${value.total}`;
    return `<td class="ob-hit-cell ${tone}"><span title="${escapeHtml(title)}">${escapeHtml(percent(pct))}</span></td>`;
  }

  function renderMobileCard(row, index) {
    const signals = rowSignals(row);
    const saved = state.saved.has(selectedKey(row));
    return `
      <article class="ob-mobile-card" data-row-index="${index}">
        <div class="ob-mobile-card-head">
          <div>
            <h3>${escapeHtml(proposition(row))}</h3>
            <p>${escapeHtml(clean(row.player) || clean(row.team))} - ${escapeHtml(gameLabel(row) || "Matchup unavailable")}</p>
          </div>
          <button class="ob-plus ${saved ? "is-saved" : ""}" type="button" data-save-key="${escapeHtml(selectedKey(row))}" aria-label="${saved ? "Unsave prop" : "Save prop"}">${saved ? "-" : "+"}</button>
        </div>
        <div class="ob-mobile-grid">
          <div class="ob-rail-metric"><span>Line</span><strong>${escapeHtml(clean(row.line) || "--")}</strong></div>
          <div class="ob-rail-metric"><span>Odds</span><strong>${escapeHtml(formatOdds(row.americanOdds))}</strong></div>
          <div class="ob-rail-metric"><span>IP</span><strong>${escapeHtml(percent(signals.ip))}</strong></div>
          <div class="ob-rail-metric"><span>L10</span><strong>${escapeHtml(hitWindow(row, "L10") ? percent(hitWindow(row, "L10").pct) : "--")}</strong></div>
          <div class="ob-rail-metric"><span>L20</span><strong>${escapeHtml(hitWindow(row, "L20") ? percent(hitWindow(row, "L20").pct) : "--")}</strong></div>
          <div class="ob-rail-metric"><span>2026</span><strong>${escapeHtml(hitWindow(row, "season") ? percent(hitWindow(row, "season").pct) : "--")}</strong></div>
        </div>
      </article>
    `;
  }



  function detailCacheMatches(row) {
    return state.detail && state.detail.key === detailKey(row);
  }

  function detailKey(row) {
    return selectedKey(row || {});
  }

  function teamColor(team) {
    return TEAM_COLORS[clean(team).toUpperCase()] || TEAM_COLORS.MLB;
  }

  function hexToRgb(hex) {
    const value = clean(hex).replace("#", "");
    if (value.length !== 6) return [24, 217, 156];
    return [parseInt(value.slice(0, 2), 16), parseInt(value.slice(2, 4), 16), parseInt(value.slice(4, 6), 16)];
  }

  function rgba(hex, alpha) {
    const [r, g, b] = hexToRgb(hex);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function cssVar(name, fallback) {
    const root = document.documentElement;
    return getComputedStyle(root).getPropertyValue(name).trim() || fallback;
  }

  function currentDetail() {
    return state.detail || { loadingCard: false, loadingLogs: false, loadingGame: false, propCard: null, gameLogs: [], gameContext: null, errors: {} };
  }

  function detailSeason() {
    return String(state.date || today()).slice(0, 4) || "2026";
  }

  function getRowField(row, names, fallback = "") {
    for (const name of names) {
      if (row && row[name] !== undefined && row[name] !== null && clean(row[name]) !== "") return row[name];
    }
    return fallback;
  }

  function statTabIndexForMarket(market) {
    const target = baseMarket(market);
    const found = STAT_TABS.findIndex((tab) => tab.market === target);
    if (found >= 0) return found;
    if (target === "pitcher_strikeouts") return STAT_TABS.findIndex((tab) => tab.label === "SO");
    return 0;
  }

  function activeStatTab(row) {
    if (!Number.isFinite(Number(state.detailStatTab))) {
      return STAT_TABS[statTabIndexForMarket(row.market)] || STAT_TABS[0];
    }
    return STAT_TABS[state.detailStatTab] || STAT_TABS[0];
  }

  function statValue(log, tab) {
    if (!log) return 0;
    if (tab.market === "_computed_hrbi") {
      return number(log.hits) + number(log.runs) + number(log.rbi);
    }
    if (tab.market === "_computed_1b") {
      return Math.max(0, number(log.hits) - number(log.doubles) - number(log.triples) - number(log.homeRuns));
    }
    if (tab.market === "team_first_to_score") return number(log.firstToScore, 0);
    return number(log[tab.col], 0);
  }

  function statLabel(tab) {
    if (!tab) return "Stat";
    if (tab.label === "TB") return "Bases";
    if (tab.label === "SO") return "Strikeouts";
    return tab.label;
  }

  function gameDateShort(value) {
    const text = clean(value).slice(0, 10);
    if (!text) return "--";
    const parts = text.split("-");
    if (parts.length !== 3) return text;
    return `${Number(parts[1])}/${Number(parts[2])}`;
  }

  function formatGameTime(row) {
    const raw = clean(row.gameTime || row.startTime || row.commenceTime || row.gameDate || row.date);
    if (!raw) return `Today`;
    if (/today/i.test(raw)) return raw;
    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime()) && raw.includes("T")) {
      return `Today ${parsed.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
    }
    return raw === state.date ? "Today" : raw;
  }

  function detailGameLabel(row) {
    const away = clean(row.away || row.team);
    const home = clean(row.home || row.opponent);
    return away && home ? `${away} @ ${home}` : gameLabel(row);
  }

  function currentLine(row) {
    return clean(state.activeLine) || canonicalLine(row);
  }

  function currentSide(row) {
    return clean(state.activeSide) || sideLabel(row);
  }

  function currentOdds(row) {
    return clean(state.activeOdds) || clean(row.americanOdds) || clean(row.odds) || "";
  }

  function samePropFamily(a, b) {
    return normalizeName(a.player || a.team) === normalizeName(b.player || b.team)
      && baseMarket(a.market) === baseMarket(b.market)
      && clean(a.team).toUpperCase() === clean(b.team).toUpperCase()
      && clean(a.opponent).toUpperCase() === clean(b.opponent).toUpperCase();
  }

  function matchingLineRows(row) {
    return state.rows.filter((item) => samePropFamily(item, row));
  }

  function oddsFor(row, side, line) {
    const targetSide = clean(side).toLowerCase();
    const targetLine = String(line);
    const match = matchingLineRows(row).find((item) => sideLabel(item).toLowerCase() === targetSide && canonicalLine(item) === targetLine);
    return match ? clean(match.americanOdds) : clean(row.americanOdds);
  }

  function hitInDirection(value, line, direction) {
    const threshold = number(line, 0);
    const stat = number(value, 0);
    return clean(direction).toLowerCase() === "under" ? stat < threshold : stat > threshold;
  }

  function median(values) {
    const nums = values.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    if (!nums.length) return 0;
    const mid = Math.floor(nums.length / 2);
    return nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
  }

  function sortedLogs(logs) {
    return [...(Array.isArray(logs) ? logs : [])].sort((a, b) => clean(a.date).localeCompare(clean(b.date)) || clean(a.gamePk).localeCompare(clean(b.gamePk)));
  }

  function periodLogs(logs, period, row) {
    let ordered = sortedLogs(logs);
    if (period === "H2H") {
      const opponent = clean(row.opponent).toUpperCase();
      ordered = ordered.filter((log) => clean(log.opponent).toUpperCase() === opponent);
      return ordered.slice(-10);
    }
    if (period === "L5") return ordered.slice(-5);
    if (period === "L10") return ordered.slice(-10);
    if (period === "L20") return ordered.slice(-20);
    if (period === "prevSeason") return ordered.filter((log) => clean(log.season) === String(number(detailSeason(), 2026) - 1)).slice(-20);
    return ordered.filter((log) => !log.season || clean(log.season) === detailSeason());
  }

  function normalizeGameLog(row) {
    const doubles = number(getRowField(row, ["doubles", "twoB", "2B"]));
    const triples = number(getRowField(row, ["triples", "threeB", "3B"]));
    const homeRuns = number(getRowField(row, ["homeRuns", "hr"]));
    const hits = number(getRowField(row, ["hits", "h"]));
    return {
      ...row,
      season: clean(row.season) || detailSeason(),
      date: clean(row.date),
      gamePk: clean(row.gamePk),
      team: clean(row.team).toUpperCase(),
      opponent: clean(row.opponent).toUpperCase(),
      pitcher: clean(row.pitcher || row.opposingPitcher || row.probablePitcher),
      plateAppearances: number(getRowField(row, ["plateAppearances", "pa"])),
      pa: number(getRowField(row, ["plateAppearances", "pa"])),
      atBats: number(getRowField(row, ["atBats", "ab"])),
      runs: number(row.runs),
      hits,
      doubles,
      triples,
      homeRuns,
      rbi: number(getRowField(row, ["rbi", "runsBattedIn"])),
      baseOnBalls: number(getRowField(row, ["baseOnBalls", "walks", "bb"])),
      strikeOuts: number(getRowField(row, ["strikeOuts", "strikeouts", "so"])),
      stolenBases: number(row.stolenBases),
      totalBases: number(row.totalBases, hits + doubles + triples * 2 + homeRuns * 3),
      xbh: doubles + triples + homeRuns,
      firstToScore: number(row.firstToScore),
    };
  }

  function extractGameLogs(payload) {
    if (!payload || typeof payload !== "object") return [];
    const direct = payload.gameLogs || payload.logs || payload.rows;
    if (Array.isArray(direct)) return direct.map(normalizeGameLog);
    const results = Array.isArray(payload.results) ? payload.results : [];
    for (const result of results) {
      if (Array.isArray(result.gameLogs)) return result.gameLogs.map(normalizeGameLog);
      if (Array.isArray(result.logs)) return result.logs.map(normalizeGameLog);
    }
    return [];
  }

  function detailRequestBody(row) {
    return {
      season: detailSeason(),
      date: state.date,
      market: activeStatTab(row).market.startsWith("_") ? row.market : activeStatTab(row).market,
      marketDisplay: row.marketDisplay,
      rawLabel: currentSide(row),
      player: clean(row.player),
      team: clean(row.team),
      opponent: clean(row.opponent),
      pitcher: clean(row.pitcher),
      line: currentLine(row),
      american_odds: currentOdds(row),
      americanOdds: currentOdds(row),
    };
  }

  async function postJson(path, body) {
    return getJson(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  }

  async function fetchPropCard(row) {
    const body = detailRequestBody(row);
    try {
      return await postJson("/api/unified-prop-card/predict", body);
    } catch (error) {
      const params = new URLSearchParams(body);
      return getJson(`/api/unified-prop-card/predict?${params.toString()}`);
    }
  }

  async function fetchDetailLogs(row) {
    const params = new URLSearchParams({
      season: detailSeason(),
      kind: normalizeMarket(row.market).startsWith("pitcher_") ? "pitcher" : "batter",
      type: normalizeMarket(row.market).startsWith("pitcher_") ? "pitcher" : "batter",
      player: clean(row.player),
      q: clean(row.player),
      market: activeStatTab(row).market,
      limit: "80",
    });
    return getJson(`/api/incremental-stats/lookup?${params.toString()}`);
  }

  async function fetchDetailGameContext(row) {
    const params = new URLSearchParams({
      season: detailSeason(),
      date: state.date,
      team: clean(row.team),
      opponent: clean(row.opponent),
      limit: "5",
    });
    return getJson(`/api/game-context?${params.toString()}`);
  }

  function openPropDetail(row) {
    state.selected = row;
    state.nav = "PropDetail";
    state.detailStatTab = statTabIndexForMarket(row.market);
    state.detailPeriod = "L10";
    state.detailChartMode = "bar";
    state.activeLine = canonicalLine(row);
    state.activeSide = sideLabel(row);
    state.activeOdds = clean(row.americanOdds);
    state.lineDropdownOpen = false;
    state.activePitchFilter = "All";
    state.heatmapPitcherHand = "ALL";
    state.heatmapBatterHand = "ALL";
    loadDetailData(row);
  }

  function loadDetailData(row) {
    const key = detailKey(row);
    state.detail = {
      key,
      loadingCard: true,
      loadingLogs: true,
      loadingGame: true,
      propCard: null,
      gameLogs: [],
      gameContext: null,
      errors: {},
    };
    render();

    fetchPropCard(row)
      .then((payload) => {
        if (!detailCacheMatches(row)) return;
        state.detail.propCard = payload;
      })
      .catch((error) => {
        if (!detailCacheMatches(row)) return;
        state.detail.errors.card = error.message || "Prop card failed to load.";
      })
      .finally(() => {
        if (!detailCacheMatches(row)) return;
        state.detail.loadingCard = false;
        render();
      });

    fetchDetailLogs(row)
      .then((payload) => {
        if (!detailCacheMatches(row)) return;
        state.detail.gameLogs = extractGameLogs(payload);
      })
      .catch((error) => {
        if (!detailCacheMatches(row)) return;
        state.detail.errors.logs = error.message || "Game logs failed to load.";
      })
      .finally(() => {
        if (!detailCacheMatches(row)) return;
        state.detail.loadingLogs = false;
        render();
      });

    fetchDetailGameContext(row)
      .then((payload) => {
        if (!detailCacheMatches(row)) return;
        state.detail.gameContext = payload;
      })
      .catch((error) => {
        if (!detailCacheMatches(row)) return;
        state.detail.errors.game = error.message || "Game context failed to load.";
      })
      .finally(() => {
        if (!detailCacheMatches(row)) return;
        state.detail.loadingGame = false;
        render();
      });
  }

  function renderPropDetail(row) {
    const detail = currentDetail();
    const tab = activeStatTab(row);
    const logs = periodLogs(detail.gameLogs || [], state.detailPeriod, row);
    return `
      <section class="ob-detail-shell">
        ${renderDetailHeader(row)}
        <div class="ob-detail-body">
          ${renderLineSelector(row)}
          ${renderStatTabs(row)}
          ${renderPeriodControls()}
          ${renderPerfSummary(row, logs, tab)}
          ${renderPrimaryChart(row, logs, tab)}
          ${renderSupportingStats(detail, logs)}
          ${renderInsightsBlock(detail)}
          ${renderMatchupStats(row, detail)}
          ${renderPitchArsenal(row, detail)}
          ${renderHeatmaps(detail)}
        </div>
      </section>
    `;
  }

  function renderDetailHeader(row) {
    const color = teamColor(row.team);
    const bg = rgba(color, 0.3);
    const hand = clean(row.hand || row.batSide || row.bats || "SH");
    return `
      <header class="ob-detail-header">
        <div class="ob-detail-header-top">
          <button class="ob-detail-back" type="button" data-action="backToProps">← Back to Props</button>
          <div class="ob-detail-game-info">${escapeHtml(detailGameLabel(row))} · ${escapeHtml(formatGameTime(row))}</div>
        </div>
        <div class="ob-detail-player-row">
          <div class="ob-avatar-lg" style="--team-color: ${escapeHtml(color)}; --team-bg: ${escapeHtml(bg)}">${escapeHtml(initials(row.player || row.team))}</div>
          <div class="ob-detail-title-block">
            <h1>${escapeHtml(clean(row.player) || clean(row.team) || "MLB Prop")}</h1>
            <span>${escapeHtml(clean(row.team) || "MLB")}${hand ? ` (${escapeHtml(hand)})` : ""}</span>
          </div>
          <div class="ob-detail-proposition">${escapeHtml(statLabel(activeStatTab(row)))} – ${escapeHtml(currentSide(row))} ${escapeHtml(currentLine(row))}</div>
        </div>
      </header>
    `;
  }

  function renderLineSelector(row) {
    const line = currentLine(row);
    const side = currentSide(row);
    const underOdds = oddsFor(row, "Under", line) || currentOdds(row);
    const overOdds = oddsFor(row, "Over", line) || currentOdds(row);
    const altRows = matchingLineRows(row)
      .filter((item) => canonicalLine(item) && (canonicalLine(item) !== canonicalLine(row) || isAltMarket(item)))
      .sort((a, b) => number(a.line) - number(b.line));
    const unique = [];
    const seen = new Set();
    altRows.forEach((item) => {
      const key = `${sideLabel(item)}|${canonicalLine(item)}|${clean(item.americanOdds)}`;
      if (!seen.has(key)) {
        seen.add(key);
        unique.push(item);
      }
    });
    return `
      <div class="ob-line-selector">
        <div class="ob-line-pills" role="group" aria-label="Line side">
          <button type="button" class="${side === "Under" ? "is-active" : ""}" data-detail-side="Under">Under ${escapeHtml(line)} <strong>${escapeHtml(formatOdds(underOdds))}</strong></button>
          <button type="button" class="${side === "Over" ? "is-active" : ""}" data-detail-side="Over">Over ${escapeHtml(line)} <strong>${escapeHtml(formatOdds(overOdds))}</strong></button>
        </div>
        <div class="ob-alt-lines ${state.lineDropdownOpen ? "is-open" : ""}">
          <button class="ob-alt-trigger" type="button" data-action="toggleAltDropdown">ALT LINES <span>${escapeHtml(String(unique.length))}</span></button>
          ${state.lineDropdownOpen ? `
            <div class="ob-alt-menu" role="menu">
              ${unique.length ? unique.map((item) => `
                <button type="button" data-alt-line="${escapeHtml(canonicalLine(item))}" data-alt-side="${escapeHtml(sideLabel(item))}" data-alt-odds="${escapeHtml(clean(item.americanOdds))}">
                  <span>${escapeHtml(sideLabel(item))} ${escapeHtml(canonicalLine(item))}</span>
                  <strong>${escapeHtml(formatOdds(item.americanOdds))}</strong>
                  <em>${escapeHtml(percent((impliedFromOdds(item.americanOdds) || 0) * 100))}</em>
                </button>
              `).join("") : `<div class="ob-alt-empty">No alternate lines found</div>`}
            </div>
          ` : ""}
        </div>
      </div>
    `;
  }

  function impliedFromOdds(value) {
    const odds = number(value, 0);
    if (!odds) return null;
    return odds > 0 ? 100 / (odds + 100) : Math.abs(odds) / (Math.abs(odds) + 100);
  }

  function renderStatTabs(row) {
    return `
      <div class="ob-stat-tabs" role="tablist" aria-label="Stat type">
        ${STAT_TABS.map((tab, index) => `
          <button type="button" class="${index === state.detailStatTab ? "is-active" : ""}" data-detail-stat="${index}">${escapeHtml(tab.label)}</button>
        `).join("")}
      </div>
    `;
  }

  function renderPeriodControls() {
    return `
      <div class="ob-detail-controls">
        <div class="ob-period-tabs" role="tablist" aria-label="Time period">
          ${DETAIL_PERIODS.map(([key, label]) => `
            <button type="button" class="${state.detailPeriod === key ? "is-active" : ""}" data-detail-period="${escapeHtml(key)}">${escapeHtml(label)}</button>
          `).join("")}
        </div>
        <div class="ob-chart-toggle" role="group" aria-label="Chart mode">
          <button type="button" class="${state.detailChartMode === "bar" ? "is-active" : ""}" data-chart-mode="bar">▥</button>
          <button type="button" class="${state.detailChartMode === "table" ? "is-active" : ""}" data-chart-mode="table">☷</button>
        </div>
      </div>
    `;
  }

  function renderPerfSummary(row, logs, tab) {
    const windowValue = hitWindow(row, state.detailPeriod);
    const values = logs.map((log) => statValue(log, tab));
    const avg = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
    const med = median(values);
    const label = DETAIL_PERIODS.find(([key]) => key === state.detailPeriod)?.[1] || state.detailPeriod;
    const secondary = DETAIL_PERIODS.filter(([key]) => key !== state.detailPeriod).map(([key, text]) => {
      const item = hitWindow(row, key);
      return `<span class="${pctClass(item ? item.pct : -1)}"><b>${escapeHtml(text)}</b> ${item ? escapeHtml(percent(item.pct)) : "--"}</span>`;
    }).join("");
    const primaryPct = windowValue ? percent(windowValue.pct) : "--";
    const countText = windowValue ? `${windowValue.hits} of ${windowValue.total}` : `${logs.filter((log) => hitInDirection(statValue(log, tab), currentLine(row), currentSide(row))).length} of ${logs.length}`;
    return `
      <section class="ob-perf-summary">
        <div class="ob-perf-primary">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(primaryPct)}</strong>
          <em>${escapeHtml(countText)}</em>
        </div>
        <div class="ob-perf-secondary">${secondary}</div>
        <div class="ob-perf-average"><span>Average: <b>${escapeHtml(avg.toFixed(1))}</b></span><span>Median: <b>${escapeHtml((Math.round(med * 10) / 10).toString())}</b></span></div>
      </section>
    `;
  }

  function pctClass(value) {
    const pct = number(value, -1);
    if (pct >= 80) return "ob-pct-text--high";
    if (pct >= 60) return "ob-pct-text--mid";
    return "ob-pct-text--low";
  }

  function renderPrimaryChart(row, logs, tab) {
    const detail = currentDetail();
    if (detail.loadingLogs) return renderSkeletonPanel("Loading recent game logs…", 220);
    if (detail.errors && detail.errors.logs) return renderErrorPanel(detail.errors.logs, "retryDetailLogs");
    if (!logs.length) return `<section class="ob-detail-card"><div class="ob-empty"><strong>No game logs available for this period.</strong><span>Try a different period or refresh the board.</span></div></section>`;
    if (state.detailChartMode === "table") return renderLogTable(row, logs, tab);
    return `
      <section class="ob-detail-card ob-chart-card">
        <div class="ob-card-heading"><h2>${escapeHtml(clean(row.player) || "Player")} – ${escapeHtml(statLabel(tab))}</h2><span>${escapeHtml(currentSide(row))} ${escapeHtml(currentLine(row))}</span></div>
        <div class="ob-chart-wrap">
          <canvas data-detail-canvas="main" height="220" aria-label="Recent game bar chart"></canvas>
        </div>
      </section>
    `;
  }

  function renderLogTable(row, logs, tab) {
    return `
      <section class="ob-detail-card">
        <div class="ob-card-heading"><h2>Game Log</h2><span>${escapeHtml(logs.length)} games</span></div>
        <div class="ob-mini-table-wrap">
          <table class="ob-mini-table">
            <thead><tr><th>Date</th><th>Opp</th><th>${escapeHtml(tab.label)}</th><th>Result</th></tr></thead>
            <tbody>
              ${logs.map((log) => {
                const value = statValue(log, tab);
                const hit = hitInDirection(value, currentLine(row), currentSide(row));
                return `<tr><td>${escapeHtml(gameDateShort(log.date))}</td><td>${escapeHtml(clean(log.opponent) || "--")}</td><td>${escapeHtml(String(value))}</td><td class="${hit ? "is-good" : "is-bad"}">${hit ? "Hit" : "Miss"}</td></tr>`;
              }).join("")}
            </tbody>
          </table>
        </div>
      </section>
    `;
  }

  function renderSupportingStats(detail, logs) {
    if (detail.loadingLogs) return renderSkeletonPanel("Loading supporting stats…", 180);
    return `
      <section class="ob-detail-card">
        <div class="ob-card-heading"><h2>Supporting Stats</h2><span>Average</span></div>
        <div class="ob-support-charts">
          ${renderSupportChart("pa", "Plate Appearances", logs)}
          ${renderSupportChart("hits", "Hits", logs)}
          ${renderSupportChart("xbh", "Extra Base Hits", logs)}
        </div>
      </section>
    `;
  }

  function supportAverage(logs, key) {
    if (!logs.length) return 0;
    return logs.reduce((sum, log) => sum + number(log[key]), 0) / logs.length;
  }

  function renderSupportChart(key, label, logs) {
    const avg = supportAverage(logs, key);
    return `
      <div class="ob-support-card">
        <div><strong>${escapeHtml(label)}</strong><span>${escapeHtml(avg.toFixed(1))}</span></div>
        <canvas data-detail-canvas="support" data-support-key="${escapeHtml(key)}" height="150"></canvas>
      </div>
    `;
  }

  function renderInsightsBlock(detail) {
    if (detail.loadingCard) return renderSkeletonPanel("Loading insights…", 110);
    if (detail.errors && detail.errors.card) return renderErrorPanel(detail.errors.card, "retryDetailCard");
    const items = ((detail.propCard || {}).insights || []).filter((item) => ["insight", "analysis"].includes(clean(item.type)));
    return `
      <section class="ob-detail-card ob-insights-block">
        <div class="ob-card-heading"><h2>Insights</h2><span>${escapeHtml(clean((detail.propCard || {}).confidence) || "Model")}</span></div>
        <div class="ob-insight-copy">
          ${(items.length ? items : [{ text: selectedInsight(state.selected || {}) }]).map((item) => `<p>${escapeHtml(item.text || item.reason || "Insight unavailable.")}</p>`).join("")}
        </div>
      </section>
    `;
  }

  function renderMatchupStats(row, detail) {
    if (detail.loadingCard) return renderSkeletonPanel("Loading matchup stats…", 170);
    const card = detail.propCard || {};
    const contexts = card.cachedContexts || {};
    const batter = contexts.batter || {};
    const pitcher = contexts.pitcher || {};
    const bvp = (card.savant && card.savant.bvp) || card.bvp || null;
    return `
      <section class="ob-detail-card ob-matchup-card">
        <div class="ob-card-heading"><h2>Key Matchup Stats</h2><span>${escapeHtml(clean(row.pitcher) ? `vs. ${clean(row.pitcher)}` : "Matchup")}</span></div>
        ${bvp ? renderBvpRow(bvp) : `<p class="ob-muted-line">Split data unavailable for this matchup. Season context is shown below.</p>`}
        <div class="ob-split-grid">
          <div>${renderContextTable(`${initials(row.player)} Batter`, [
            ["PA", batter.plateAppearances], ["AVG", formatDecimal(batter.avg)], ["H/G", batter.hitsPerGame], ["TB/G", batter.totalBasesPerGame], ["K/G", batter.strikeoutsPerGame]
          ])}</div>
          <div>${renderContextTable(`${initials(row.pitcher)} Pitcher`, [
            ["BF", pitcher.battersFaced], ["K/G", pitcher.strikeoutsPerGame], ["H/G", pitcher.hitsAllowedPerGame], ["ER/G", pitcher.earnedRunsPerGame], ["Pitches", pitcher.pitchesThrown]
          ])}</div>
        </div>
      </section>
    `;
  }

  function formatDecimal(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "--";
    return n < 1 ? n.toFixed(3).replace(/^0/, "") : n.toFixed(1);
  }

  function renderBvpRow(bvp) {
    const cells = [["PA", bvp.pa], ["AVG", bvp.avg], ["OBP", bvp.obp], ["SLG", bvp.slg], ["H", bvp.hits || bvp.h], ["TB", bvp.totalBases || bvp.tb], ["XBH", bvp.xbh]];
    return `<div class="ob-bvp-row">${cells.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(formatDecimal(value))}</strong></div>`).join("")}</div>`;
  }

  function renderContextTable(title, rows) {
    return `
      <table class="ob-context-table">
        <thead><tr><th colspan="2">${escapeHtml(title)}</th></tr></thead>
        <tbody>${rows.map(([label, value]) => `<tr><td>${escapeHtml(label)}</td><td>${escapeHtml(formatDecimal(value))}</td></tr>`).join("")}</tbody>
      </table>
    `;
  }

  function renderPitchArsenal(row, detail) {
    if (detail.loadingCard) return renderSkeletonPanel("Loading pitch arsenal…", 210);
    const card = detail.propCard || {};
    const savant = card.savant || {};
    const pitchMix = (((savant.pitcher || {}).pitchMix) || []).filter((item) => number(item.percentage) > 0);
    const pitchTypes = ["All", ...pitchMix.slice(0, 5).map((item) => clean(item.pitchType || item.code)).filter(Boolean)];
    return `
      <section class="ob-detail-card ob-arsenal-card">
        <div class="ob-card-heading"><h2>Pitch Arsenal</h2><span>${escapeHtml(clean(row.pitcher) || "Pitcher")}</span></div>
        <div class="ob-arsenal-grid">
          <div class="ob-pitch-mix">
            ${pitchMix.length ? `<canvas data-detail-canvas="pitchMix" height="170"></canvas><div class="ob-pitch-legend">${pitchMix.slice(0, 6).map((item) => `
              <div><i style="background:${escapeHtml(PITCH_COLORS[clean(item.pitchType).toUpperCase()] || "#6b7280")}"></i><span>${escapeHtml(item.pitchName || item.pitchType)}</span><strong>${escapeHtml(number(item.percentage).toFixed(1))}%</strong></div>
            `).join("")}</div>` : `<p class="ob-muted-line">No pitch mix data available.</p>`}
          </div>
          <div class="ob-pitch-table-wrap">
            <div class="ob-mini-tabs">${pitchTypes.map((type) => `<button type="button" class="${state.activePitchFilter === type ? "is-active" : ""}" data-pitch-filter="${escapeHtml(type)}">${escapeHtml(type)}</button>`).join("")}</div>
            ${renderPitchArsenalTable(row, card)}
          </div>
        </div>
      </section>
    `;
  }

  function renderPitchArsenalTable(row, card) {
    const batter = ((card.cachedContexts || {}).batter) || {};
    const filter = state.activePitchFilter;
    const vsEach = (((card.savant || {}).batter || {}).vsEachPitch || []).filter((item) => filter === "All" || clean(item.pitchType) === filter);
    if (vsEach.length) {
      return `<table class="ob-mini-table"><thead><tr><th>Team</th><th>PC</th><th>PA</th><th>K%</th><th>wOBA</th></tr></thead><tbody>${vsEach.map((item) => `<tr><td>${escapeHtml(item.team || row.team)}</td><td>${escapeHtml(item.pc || item.pitchCount || "--")}</td><td>${escapeHtml(item.pa || "--")}</td><td>${escapeHtml(formatDecimal(item.kPct))}</td><td>${escapeHtml(formatDecimal(item.woba))}</td></tr>`).join("")}</tbody></table>`;
    }
    return `<table class="ob-mini-table"><thead><tr><th>Team</th><th>PA</th><th>H/G</th><th>TB/G</th><th>K/G</th></tr></thead><tbody><tr><td>${escapeHtml(row.team || "--")}</td><td>${escapeHtml(formatDecimal(batter.plateAppearances))}</td><td>${escapeHtml(formatDecimal(batter.hitsPerGame))}</td><td>${escapeHtml(formatDecimal(batter.totalBasesPerGame))}</td><td>${escapeHtml(formatDecimal(batter.strikeoutsPerGame))}</td></tr></tbody></table><div class="ob-compared"><i></i> compared to season stats</div>`;
  }

  function renderHeatmaps(detail) {
    if (detail.loadingCard) return renderSkeletonPanel("Loading heatmaps…", 240);
    const savant = (detail.propCard || {}).savant || {};
    const pitcherGrid = (((savant.pitcher || {}).zoneFrequency || {})[state.heatmapPitcherHand]) || [];
    const batterGrid = (((savant.batter || {}).zonePerformance || {})[state.heatmapBatterHand]) || [];
    const hasZone = pitcherGrid.length === 16 || batterGrid.length === 16;
    return `
      <section class="ob-detail-card ob-heatmaps-card">
        <div class="ob-card-heading"><h2>Heatmaps</h2><span>4×4 zone</span></div>
        ${hasZone ? `
          <div class="ob-heatmap-grid">
            <div>
              <div class="ob-mini-tabs">${["ALL", "LHB", "RHB"].map((hand) => `<button type="button" class="${state.heatmapPitcherHand === hand ? "is-active" : ""}" data-zone-pitcher="${hand}">${hand}</button>`).join("")}</div>
              <canvas data-detail-canvas="zonePitcher" height="230"></canvas>
            </div>
            <div>
              <div class="ob-mini-tabs">${["ALL", "LHP", "RHP"].map((hand) => `<button type="button" class="${state.heatmapBatterHand === hand ? "is-active" : ""}" data-zone-batter="${hand}">${hand}</button>`).join("")}</div>
              <canvas data-detail-canvas="zoneBatter" height="230"></canvas>
            </div>
          </div>
        ` : `<p class="ob-muted-line">No zone data available for this matchup.</p>`}
      </section>
    `;
  }

  function renderSkeletonPanel(label, height) {
    return `<section class="ob-detail-card"><div class="ob-card-heading"><h2>${escapeHtml(label)}</h2></div><div class="ob-skeleton ob-detail-skeleton" style="height:${escapeHtml(String(height))}px"></div></section>`;
  }

  function renderErrorPanel(message, retryAction) {
    return `<section class="ob-error-panel"><span>⚠</span><p>${escapeHtml(message)}</p><button type="button" data-action="${escapeHtml(retryAction)}">Retry</button></section>`;
  }

  function drawDetailCanvases() {
    const row = state.selected;
    if (!row || state.nav !== "PropDetail") return;
    const detail = currentDetail();
    const tab = activeStatTab(row);
    const logs = periodLogs(detail.gameLogs || [], state.detailPeriod, row);
    const main = $('[data-detail-canvas="main"]');
    if (main) drawBarChart(main, logs, tab, currentLine(row), currentSide(row));
    document.querySelectorAll('[data-detail-canvas="support"]').forEach((canvas) => drawSupportingChart(canvas, logs, canvas.dataset.supportKey));
    const pitchMix = $('[data-detail-canvas="pitchMix"]');
    if (pitchMix) drawPitchMix(pitchMix, ((((detail.propCard || {}).savant || {}).pitcher || {}).pitchMix || []));
    const zonePitcher = $('[data-detail-canvas="zonePitcher"]');
    if (zonePitcher) drawZoneChart(zonePitcher, (((((detail.propCard || {}).savant || {}).pitcher || {}).zoneFrequency || {})[state.heatmapPitcherHand]) || [], "Pitch Location");
    const zoneBatter = $('[data-detail-canvas="zoneBatter"]');
    if (zoneBatter) drawZoneChart(zoneBatter, (((((detail.propCard || {}).savant || {}).batter || {}).zonePerformance || {})[state.heatmapBatterHand]) || [], "Batter Performance");
  }

  function setCanvasSize(canvas, height) {
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(280, rect.width || canvas.parentElement?.clientWidth || 600);
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    return { ctx, width, height };
  }

  function drawBarChart(canvas, logs, tab, line, direction) {
    const { ctx, width, height } = setCanvasSize(canvas, 220);
    ctx.clearRect(0, 0, width, height);
    const leftPad = 34;
    const rightPad = 14;
    const topPad = 14;
    const bottomPad = 42;
    const values = logs.map((log) => statValue(log, tab));
    const threshold = number(line, 0);
    const maxValue = Math.max(threshold, ...values, 1) + 0.5;
    const chartW = width - leftPad - rightPad;
    const chartH = height - topPad - bottomPad;
    const gap = 4;
    const barW = Math.max(7, chartW / Math.max(logs.length, 1) - gap);
    const green = cssVar("--ob-green", "#18d99c");
    const miss = cssVar("--ob-panel-2", "#171919");
    const text = cssVar("--ob-muted", "#98a4a0");

    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 3; i += 1) {
      const y = topPad + (chartH / 3) * i;
      ctx.beginPath(); ctx.moveTo(leftPad, y); ctx.lineTo(width - rightPad, y); ctx.stroke();
    }

    const lineY = topPad + chartH - (threshold / maxValue) * chartH;
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "rgba(255, 107, 107, 0.55)";
    ctx.beginPath(); ctx.moveTo(leftPad, lineY); ctx.lineTo(width - rightPad, lineY); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(255,255,255,0.72)";
    ctx.font = "700 11px Inter, sans-serif";
    ctx.fillText(String(threshold), 6, lineY + 4);

    const bars = [];
    logs.forEach((log, index) => {
      const value = values[index];
      const x = leftPad + index * (barW + gap) + gap / 2;
      const barH = Math.max(2, (value / maxValue) * chartH);
      const y = topPad + chartH - barH;
      const hit = hitInDirection(value, line, direction);
      ctx.fillStyle = hit ? green : miss;
      ctx.fillRect(x, y, barW, barH);
      ctx.fillStyle = hit ? green : text;
      ctx.font = "800 10px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(String(value), x + barW / 2, Math.max(topPad + 10, y - 5));
      ctx.fillStyle = text;
      ctx.font = "700 10px Inter, sans-serif";
      ctx.fillText(gameDateShort(log.date), x + barW / 2, height - 24);
      ctx.fillText(clean(log.opponent) ? `vs ${clean(log.opponent)}` : "--", x + barW / 2, height - 11);
      bars.push({ x, y, width: barW, height: barH, log, value, hit });
    });
    ctx.textAlign = "left";
    attachChartTooltip(canvas, bars);
  }

  function attachChartTooltip(canvas, bars) {
    canvas.onmousemove = (event) => {
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const item = bars.find((bar) => x >= bar.x && x <= bar.x + bar.width);
      let tip = $("#ob-chart-tooltip", document.body);
      if (!item) {
        if (tip) tip.remove();
        return;
      }
      if (!tip) {
        tip = document.createElement("div");
        tip.id = "ob-chart-tooltip";
        document.body.appendChild(tip);
      }
      tip.innerHTML = `<strong>${escapeHtml(gameDateShort(item.log.date))} ${escapeHtml(clean(item.log.opponent) || "")}</strong><span>${escapeHtml(String(item.value))} · ${item.hit ? "Hit" : "Miss"}</span>`;
      tip.style.left = `${event.clientX + 12}px`;
      tip.style.top = `${event.clientY + 12}px`;
    };
    canvas.onmouseleave = () => {
      const tip = $("#ob-chart-tooltip", document.body);
      if (tip) tip.remove();
    };
  }

  function drawSupportingChart(canvas, logs, key) {
    const { ctx, width, height } = setCanvasSize(canvas, 150);
    ctx.clearRect(0, 0, width, height);
    const values = logs.map((log) => number(log[key]));
    const maxValue = Math.max(...values, 1);
    const leftPad = 8;
    const chartW = width - 16;
    const chartH = height - 24;
    const barW = Math.max(7, chartW / Math.max(values.length, 1) - 4);
    ctx.fillStyle = cssVar("--ob-panel-2", "#171919");
    values.forEach((value, index) => {
      const h = Math.max(2, (value / maxValue) * chartH);
      const x = leftPad + index * (barW + 4);
      const y = chartH - h + 6;
      ctx.fillRect(x, y, barW, h);
    });
  }

  function drawPitchMix(canvas, pitchMix) {
    const { ctx, width, height } = setCanvasSize(canvas, 170);
    ctx.clearRect(0, 0, width, height);
    const items = (pitchMix || []).filter((item) => number(item.percentage) > 0).slice(0, 7);
    if (!items.length) return;
    const cx = Math.min(width * 0.38, 90);
    const cy = height / 2;
    const radius = Math.min(68, height / 2 - 12);
    let angle = -Math.PI / 2;
    items.forEach((item) => {
      const pct = number(item.percentage) / 100;
      const next = angle + pct * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, radius, angle, next);
      ctx.closePath();
      ctx.fillStyle = PITCH_COLORS[clean(item.pitchType).toUpperCase()] || "#6b7280";
      ctx.fill();
      angle = next;
    });
    ctx.globalCompositeOperation = "destination-out";
    ctx.beginPath(); ctx.arc(cx, cy, radius * 0.58, 0, Math.PI * 2); ctx.fill();
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = cssVar("--ob-text", "#f4f7f6");
    ctx.font = "900 13px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(detailSeason(), cx, cy + 4);
    ctx.textAlign = "left";
  }

  function interpolateColor(a, b, t) {
    const ar = hexToRgb(a); const br = hexToRgb(b);
    return `rgb(${Math.round(ar[0] + (br[0] - ar[0]) * t)}, ${Math.round(ar[1] + (br[1] - ar[1]) * t)}, ${Math.round(ar[2] + (br[2] - ar[2]) * t)})`;
  }

  function drawZoneChart(canvas, grid, title) {
    const { ctx, width, height } = setCanvasSize(canvas, 230);
    ctx.clearRect(0, 0, width, height);
    const values = Array.isArray(grid) ? grid.map(Number).filter(Number.isFinite) : [];
    if (values.length !== 16) return;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const size = Math.min(width - 24, height - 46) / 4;
    const startX = (width - size * 4) / 2;
    const startY = 28;
    ctx.fillStyle = cssVar("--ob-muted", "#98a4a0");
    ctx.font = "800 12px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(title, width / 2, 14);
    values.forEach((value, index) => {
      const t = max === min ? 0.5 : (value - min) / (max - min);
      const row = Math.floor(index / 4);
      const col = index % 4;
      const x = startX + col * size;
      const y = startY + row * size;
      ctx.fillStyle = interpolateColor("#3b4cc0", "#c62f2f", t);
      ctx.fillRect(x, y, size - 2, size - 2);
      ctx.fillStyle = "rgba(255,255,255,0.9)";
      ctx.font = "800 10px Inter, sans-serif";
      ctx.fillText(String(value), x + size / 2, y + size / 2 + 4);
    });
    ctx.textAlign = "left";
  }

  function renderRightRail(rows) {
    const selected = state.selected || rows[0] || FALLBACK_ROWS[0];
    const signals = rowSignals(selected);
    const top = rows.slice(0, 6);

    return `
      <aside class="ob-right-rail" aria-label="Prop context">
        <div class="ob-rail-tabs">
          <button class="is-active" type="button">Matchup</button>
          <button type="button">Injuries</button>
          <button type="button">Insights</button>
        </div>

        <section class="ob-rail-card">
          <div class="ob-rail-card-header">
            <h3>${escapeHtml(clean(selected.player) || "Selected prop")}</h3>
            <span>${escapeHtml(gameLabel(selected) || "MLB")}</span>
          </div>
          <div class="ob-rail-body">
            <p class="ob-pick-title">${escapeHtml(proposition(selected))}</p>
            <p class="ob-pick-copy">${escapeHtml(selectedInsight(selected))}</p>
            <div class="ob-rail-metrics">
              <div class="ob-rail-metric"><span>IP</span><strong>${escapeHtml(percent(signals.ip))}</strong></div>
              <div class="ob-rail-metric"><span>L10</span><strong>${escapeHtml(hitWindow(selected, "L10") ? percent(hitWindow(selected, "L10").pct) : "--")}</strong></div>
              <div class="ob-rail-metric"><span>Odds</span><strong>${escapeHtml(formatOdds(selected.americanOdds))}</strong></div>
            </div>
          </div>
        </section>

        <section class="ob-rail-card">
          <div class="ob-rail-card-header">
            <h3>Hit-Rate Profile</h3>
            <span>${escapeHtml(state.date)}</span>
          </div>
          <div class="ob-rail-body ob-bar-list">
            ${HIT_COLUMNS.map(([key, label]) => signalBar(label, hitPct(selected, key))).join("")}
          </div>
        </section>

        <section class="ob-rail-card">
          <div class="ob-rail-card-header">
            <h3>Best On Board</h3>
            <span>${escapeHtml(String(top.length))} props</span>
          </div>
          <div class="ob-rail-body ob-insight-list">
            ${top.map((row) => `
              <div class="ob-insight-item">
                <strong>${escapeHtml(clean(row.player) || clean(row.team))} ${escapeHtml(proposition(row))}</strong>
                <span>${escapeHtml(gameLabel(row) || "MLB")} - ${escapeHtml(hitWindow(row, "L10") ? percent(hitWindow(row, "L10").pct) : "hit rate pending")}</span>
              </div>
            `).join("")}
          </div>
        </section>
      </aside>
    `;
  }

  function selectedInsight(row) {
    const rate = hitWindow(row, "L10");
    const side = sideLabel(row).toLowerCase();
    const name = clean(row.player) || clean(row.team) || "This prop";
    const market = marketLabel(row.market);
    if (rate) {
      return `${name} has cleared the ${side} ${market} profile in ${rate.hits} of the last ${rate.total} logged games.`;
    }
    return `${name} has model context loaded, but historical hit-rate windows are still pending for this market.`;
  }

  function signalBar(label, pct) {
    if (pct < 0) {
      return `
        <div class="ob-signal-row">
          <div class="ob-signal-label"><span>${escapeHtml(label)}</span><strong>--</strong></div>
          <div class="ob-meter"><span style="width: 0%"></span></div>
        </div>
      `;
    }
    const width = clamp(pct, 0, 100);
    return `
      <div class="ob-signal-row">
        <div class="ob-signal-label"><span>${escapeHtml(label)}</span><strong>${escapeHtml(percent(width))}</strong></div>
        <div class="ob-meter"><span style="width: ${escapeHtml(String(width))}%"></span></div>
      </div>
    `;
  }

  function onClick(event) {
    const saveButton = event.target.closest("[data-save-key]");
    if (saveButton) {
      const key = saveButton.dataset.saveKey;
      if (state.saved.has(key)) {
        state.saved.delete(key);
      } else {
        state.saved.add(key);
      }
      storeSavedKeys();
      render();
      return;
    }

    const sortButton = event.target.closest("[data-sort-key]");
    if (sortButton) {
      const key = sortButton.dataset.sortKey;
      if (state.sortKey === key) {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
      } else {
        state.sortKey = key;
        state.sortDir = ["player", "proposition", "line"].includes(key) ? "asc" : "desc";
      }
      render();
      return;
    }

    const navButton = event.target.closest("[data-nav]");
    if (navButton) {
      applyNav(navButton.dataset.nav);
      return;
    }

    const sportButton = event.target.closest("[data-sport]");
    if (sportButton) {
      const sport = sportButton.dataset.sport;
      if (sport !== "MLB") {
        showToast(`This build is MLB-only. ${sport} coming soon.`, "info");
        return;
      }
      state.sport = sport;
      render();
      return;
    }

    const categoryButton = event.target.closest("[data-category-tab]");
    if (categoryButton) {
      const tab = categoryButton.dataset.categoryTab;
      state.categoryTab = tab;
      state.savedOnly = tab === "Saved";
      if (tab === "Tomorrow") {
        const nextDate = addDays(today(), 1);
        if (state.date !== nextDate) {
          state.date = nextDate;
          loadBoard();
          return;
        }
      } else if (tab === "Today") {
        const current = today();
        if (state.date !== current) {
          state.date = current;
          loadBoard();
          return;
        }
      }
      render();
      return;
    }

    const sideButton = event.target.closest("[data-detail-side]");
    if (sideButton && state.selected) {
      state.activeSide = sideButton.dataset.detailSide;
      state.activeOdds = oddsFor(state.selected, state.activeSide, currentLine(state.selected));
      state.lineDropdownOpen = false;
      render();
      return;
    }

    const altButton = event.target.closest("[data-alt-line]");
    if (altButton && state.selected) {
      state.activeLine = altButton.dataset.altLine;
      state.activeSide = altButton.dataset.altSide || state.activeSide;
      state.activeOdds = altButton.dataset.altOdds || oddsFor(state.selected, state.activeSide, state.activeLine);
      state.lineDropdownOpen = false;
      render();
      return;
    }

    const statButton = event.target.closest("[data-detail-stat]");
    if (statButton && state.selected) {
      state.detailStatTab = number(statButton.dataset.detailStat, 0);
      state.lineDropdownOpen = false;
      render();
      return;
    }

    const periodButton = event.target.closest("[data-detail-period]");
    if (periodButton) {
      state.detailPeriod = periodButton.dataset.detailPeriod;
      render();
      return;
    }

    const chartModeButton = event.target.closest("[data-chart-mode]");
    if (chartModeButton) {
      state.detailChartMode = chartModeButton.dataset.chartMode;
      render();
      return;
    }

    const pitchButton = event.target.closest("[data-pitch-filter]");
    if (pitchButton) {
      state.activePitchFilter = pitchButton.dataset.pitchFilter;
      render();
      return;
    }

    const zonePitcherButton = event.target.closest("[data-zone-pitcher]");
    if (zonePitcherButton) {
      state.heatmapPitcherHand = zonePitcherButton.dataset.zonePitcher;
      render();
      return;
    }

    const zoneBatterButton = event.target.closest("[data-zone-batter]");
    if (zoneBatterButton) {
      state.heatmapBatterHand = zoneBatterButton.dataset.zoneBatter;
      render();
      return;
    }

    const row = event.target.closest("[data-row-index]");
    if (row) {
      const rows = filteredRows().slice(0, PAGE_SIZE);
      const next = rows[number(row.dataset.rowIndex, -1)];
      if (next) {
        openPropDetail(next);
      }
      return;
    }

    const action = event.target.closest("[data-action]");
    if (!action) return;
    if (action.dataset.action === "reload") loadBoard();
    if (action.dataset.action === "backToProps") {
      state.nav = "Props";
      state.lineDropdownOpen = false;
      render();
    }
    if (action.dataset.action === "toggleAltDropdown") {
      state.lineDropdownOpen = !state.lineDropdownOpen;
      render();
    }
    if (action.dataset.action === "retryDetailCard" && state.selected) {
      const key = detailKey(state.selected);
      state.detail.key = key;
      state.detail.loadingCard = true;
      delete state.detail.errors.card;
      render();
      fetchPropCard(state.selected).then((payload) => {
        if (state.detail.key !== key) return;
        state.detail.propCard = payload;
      }).catch((error) => {
        if (state.detail.key !== key) return;
        state.detail.errors.card = error.message || "Prop card failed to load.";
      }).finally(() => {
        if (state.detail.key !== key) return;
        state.detail.loadingCard = false;
        render();
      });
    }
    if (action.dataset.action === "retryDetailLogs" && state.selected) {
      const key = detailKey(state.selected);
      state.detail.key = key;
      state.detail.loadingLogs = true;
      delete state.detail.errors.logs;
      render();
      fetchDetailLogs(state.selected).then((payload) => {
        if (state.detail.key !== key) return;
        state.detail.gameLogs = extractGameLogs(payload);
      }).catch((error) => {
        if (state.detail.key !== key) return;
        state.detail.errors.logs = error.message || "Game logs failed to load.";
      }).finally(() => {
        if (state.detail.key !== key) return;
        state.detail.loadingLogs = false;
        render();
      });
    }
    if (action.dataset.action === "toggleAlt") {
      state.showAlt = !state.showAlt;
      render();
    }
    if (action.dataset.action === "toggleSaved") {
      state.savedOnly = !state.savedOnly;
      state.nav = state.savedOnly ? "Saved" : "Props";
      render();
    }
    if (action.dataset.action === "clearFilters") {
      state.market = "";
      state.side = "";
      state.game = "";
      state.query = "";
      state.showAlt = false;
      state.savedOnly = false;
      state.categoryTab = "Today";
      state.minEdge = 0;
      state.nav = "Props";
      render();
    }
    if (action.dataset.action === "columnConfig") {
      showToast("Column controls are queued for the next table pass.", "info");
    }
  }

  function applyNav(item) {
    state.nav = item;
    if (item === "Props") {
      state.savedOnly = false;
      state.minEdge = 0;
    } else if (item === "EV+" || item === "Boosts") {
      state.savedOnly = false;
      state.minEdge = 5;
      state.sortKey = "edge";
      state.sortDir = "desc";
    } else if (item === "Popular") {
      state.savedOnly = false;
      state.sortKey = "L10";
      state.sortDir = "desc";
    } else if (item === "Saved") {
      state.savedOnly = true;
    } else if (item === "Games") {
      showToast("Games view begins in Stage 8.", "info");
    } else if (item === "Insights") {
      showToast("Insights feed begins in Stage 9.", "info");
    }
    render();
  }

  function onInput(event) {
    const control = event.target.dataset.control;
    if (control === "query") {
      state.query = event.target.value;
      renderBoardOnly();
    }
  }

  function onChange(event) {
    const control = event.target.dataset.control;
    if (!control) return;
    if (control === "date") {
      state.date = event.target.value || today();
      loadBoard();
    }
    if (control === "market") {
      state.market = event.target.value;
      loadBoard();
    }
    if (control === "side") {
      state.side = event.target.value;
      render();
    }
    if (control === "game") {
      state.game = event.target.value;
      render();
    }
  }

  function renderBoardOnly() {
    const rows = filteredRows();
    const board = $(".ob-board");
    if (board) {
      board.innerHTML = `
        ${renderBoardMeta(rows.length)}
        ${state.loading ? renderLoading() : renderTable(rows)}
      `;
      updateFilterChrome(rows.length);
    } else {
      render();
    }
  }

  function updateFilterChrome(visible) {
    const count = activeFilterCount();
    const badge = $(".ob-filter-count");
    if (badge) badge.textContent = String(count);
    const clearButton = $(".ob-clear-filter");
    if (clearButton) clearButton.classList.toggle("is-hidden", count === 0);
    const propCount = $("#obPropCount");
    if (propCount) propCount.textContent = `${visible}/${state.rows.length} Props`;
  }

  function renderBoard() {
    render();
  }

  function showToast(message, type = "info") {
    let stack = $("#obToastStack", document.body);
    if (!stack) {
      stack = document.createElement("div");
      stack.id = "obToastStack";
      stack.className = "ob-toast-stack";
      document.body.appendChild(stack);
    }

    const toast = document.createElement("div");
    const safeType = ["success", "error", "info"].includes(type) ? type : "info";
    toast.className = `ob-toast ob-toast--${safeType}`;
    toast.setAttribute("role", safeType === "error" ? "alert" : "status");
    toast.textContent = message;
    stack.appendChild(toast);

    window.requestAnimationFrame(() => toast.classList.add("is-visible"));
    window.setTimeout(() => {
      toast.classList.remove("is-visible");
      window.setTimeout(() => toast.remove(), 220);
    }, 3000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createShell);
  } else {
    createShell();
  }
})();
