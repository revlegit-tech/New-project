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
  const HIT_COLUMNS = [
    ["L5", "L5"],
    ["L10", "L10"],
    ["L20", "L20"],
    ["H2H", "H2H"],
    ["season", "2026"],
    ["prevSeason", "2025"],
  ];
  const PAGE_SIZE = 32;

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
    saved: new Set(loadSavedKeys()),
    loading: false,
    source: "loading",
    hitRateSource: "",
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
      state.minEdge > 0 ? "edge" : "",
    ].filter(Boolean).length;
  }

  function availableGames() {
    return [...new Set(state.rows.map(gameLabel).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  }

  function filteredRows() {
    const query = state.query.toLowerCase();
    const targetMarket = state.market;
    let rows = state.rows.filter((row) => {
      if (state.savedOnly && !state.saved.has(selectedKey(row))) return false;
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

    root.innerHTML = `
      ${renderSidebar(rows.length, positive, avgEdge)}
      <main class="ob-main">
        ${renderHero(rows.length, state.rows.length)}
        <section class="ob-board-wrap">
          <div class="ob-board">
            ${renderBoardMeta(rows.length)}
            ${state.loading ? renderLoading() : renderTable(rows)}
          </div>
        </section>
      </main>
      ${renderRightRail(rows)}
    `;
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
      </header>
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
    return `
      <div class="ob-empty">
        <strong>Loading board</strong>
        <span>Pulling props, model odds, and historical hit-rate windows.</span>
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
    const tone = pct >= 80 ? "is-hot" : pct >= 60 ? "is-mid" : "is-cold";
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
        showToast(`${sport} is parked for the MLB build.`);
        return;
      }
      state.sport = sport;
      render();
      return;
    }

    const row = event.target.closest("[data-row-index]");
    if (row) {
      const rows = filteredRows().slice(0, PAGE_SIZE);
      const next = rows[number(row.dataset.rowIndex, -1)];
      if (next) {
        state.selected = next;
        render();
      }
      return;
    }

    const action = event.target.closest("[data-action]");
    if (!action) return;
    if (action.dataset.action === "reload") loadBoard();
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
      state.minEdge = 0;
      state.nav = "Props";
      render();
    }
    if (action.dataset.action === "columnConfig") {
      showToast("Column controls are queued for the next table pass.");
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
      state.sortKey = "ip";
      state.sortDir = "desc";
    } else if (item === "Saved") {
      state.savedOnly = true;
    } else if (item === "Games") {
      showToast("Games view begins in Stage 8.");
    } else if (item === "Insights") {
      showToast("Insights feed begins in Stage 9.");
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

  function showToast(message) {
    let toast = $("#obToast", document.body);
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "obToast";
      toast.className = "ob-toast";
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
      toast.classList.remove("is-visible");
    }, 2400);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createShell);
  } else {
    createShell();
  }
})();
