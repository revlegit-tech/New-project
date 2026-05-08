(() => {
  const ACTION_HEADER = "X-Baseball-Prop-Action";
  const WINDOW_ORDER = [["L5", "L5"], ["L10", "L10"], ["L20", "L20"], ["H2H", "H2H"], ["season", "2026"], ["prevSeason", "2025"]];

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

  function display(value, fallback = "Not available") {
    const text = clean(value);
    return text ? text : fallback;
  }

  function asNumber(value, fallback = NaN) {
    if (value === null || value === undefined || value === "") return fallback;
    const parsed = Number(String(value).replace("%", "").replace("+", "").trim());
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function pct(value) {
    const num = asNumber(value, NaN);
    if (!Number.isFinite(num)) return "Not available";
    return `${num.toFixed(Math.abs(num) >= 10 ? 0 : 1)}%`;
  }

  function signedPct(value) {
    const num = asNumber(value, NaN);
    if (!Number.isFinite(num)) return "Not available";
    const sign = num > 0 ? "+" : "";
    return `${sign}${num.toFixed(Math.abs(num) >= 10 ? 0 : 1)}%`;
  }

  function formatOdds(value) {
    const text = clean(value);
    if (!text) return "Not available";
    const num = Number(text);
    if (!Number.isFinite(num)) return text;
    return num > 0 ? `+${Math.round(num)}` : `${Math.round(num)}`;
  }

  function queryFromButton(button) {
    const params = new URLSearchParams();
    const map = {
      id: button.dataset.propId,
      date: button.dataset.date || document.querySelector("#simpleDate")?.value,
      season: button.dataset.season,
      player: button.dataset.player,
      team: button.dataset.team,
      opponent: button.dataset.opponent,
      market: button.dataset.market,
      marketDisplay: button.dataset.marketDisplay,
      line: button.dataset.line,
      americanOdds: button.dataset.odds,
      book: button.dataset.book,
      rawLabel: button.dataset.rawLabel,
      decisionLabel: button.dataset.decision,
      readinessLabel: button.dataset.readiness,
      confidence: button.dataset.confidence,
      buildIfMissing: "1",
      limit: "500",
    };
    Object.entries(map).forEach(([key, value]) => {
      const text = clean(value);
      if (text) params.set(key, text);
    });
    return params;
  }

  async function getJson(path, options = {}) {
    const response = await fetch(path, options);
    const text = await response.text();
    let payload;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`Endpoint returned non-JSON: ${text.slice(0, 120)}`);
    }
    if (!response.ok) throw new Error(payload.error || `Request failed ${response.status}`);
    return payload;
  }

  async function postJson(path, body) {
    return getJson(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", [ACTION_HEADER]: "1" },
      body: JSON.stringify(body || {}),
    });
  }

  function ensureModal() {
    let modal = document.getElementById("propDetailModal");
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "propDetailModal";
    modal.className = "prop-detail-modal outlier-prop-detail-v2";
    modal.setAttribute("aria-hidden", "true");
    modal.innerHTML = `
      <div class="prop-detail-backdrop" data-prop-detail-close></div>
      <section class="prop-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="propDetailTitle">
        <button type="button" class="prop-detail-close" data-prop-detail-close aria-label="Close prop detail">×</button>
        <div id="propDetailBody" class="prop-detail-body">Loading…</div>
      </section>
    `;
    document.body.appendChild(modal);
    modal.addEventListener("click", (event) => {
      if (event.target.closest("[data-prop-detail-close]")) closeModal();
      const saveButton = event.target.closest("[data-prop-detail-save]");
      if (saveButton) saveCurrentPick(saveButton);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && modal.classList.contains("open")) closeModal();
    });
    return modal;
  }

  function openModal(html) {
    const modal = ensureModal();
    const body = modal.querySelector("#propDetailBody");
    if (body) body.innerHTML = html;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    modal.querySelector(".prop-detail-close")?.focus();
  }

  function closeModal() {
    const modal = document.getElementById("propDetailModal");
    if (!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  }

  function normalizeWindow(value) {
    if (value === null || value === undefined || value === "") return null;
    if (typeof value === "number") return { pct: normalizePct(value), hits: null, total: null };
    if (typeof value === "string") {
      const parsed = asNumber(value, NaN);
      return Number.isFinite(parsed) ? { pct: normalizePct(parsed), hits: null, total: null } : null;
    }
    const rawPct = asNumber(value.pct ?? value.percent ?? value.rate ?? value.value, NaN);
    if (!Number.isFinite(rawPct)) return null;
    return {
      pct: normalizePct(rawPct),
      hits: value.hits ?? value.successes ?? null,
      total: value.total ?? value.attempts ?? value.n ?? null,
    };
  }

  function normalizePct(value) {
    const parsed = asNumber(value, NaN);
    if (!Number.isFinite(parsed)) return NaN;
    return parsed <= 1 && parsed >= -1 ? parsed * 100 : parsed;
  }

  function windowsFromProfile(profile) {
    const windows = profile?.windows || {};
    return WINDOW_ORDER.map(([key, label]) => ({
      key,
      label,
      item: normalizeWindow(windows[key] ?? windows[key.toLowerCase()]),
    }));
  }

  function bestWindow(profile) {
    return windowsFromProfile(profile)
      .filter((row) => row.item && Number.isFinite(row.item.pct))
      .sort((a, b) => b.item.pct - a.item.pct)[0] || null;
  }

  function directionLabel(profile, overview) {
    const direct = clean(profile?.direction || profile?.windows?.direction || overview.rawLabel);
    if (direct) return direct.slice(0, 1).toUpperCase() + direct.slice(1).toLowerCase();
    return "Over";
  }

  function sampleText(item) {
    if (!item) return "--";
    if (item.hits !== null && item.hits !== undefined && item.total !== null && item.total !== undefined) return `${item.hits}/${item.total}`;
    return "sample pending";
  }

  function renderStat(label, value, className = "") {
    return `<div class="prop-detail-stat ${escapeHtml(className)}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(display(value))}</strong></div>`;
  }

  function renderList(items, empty = "None reported") {
    const values = Array.isArray(items) ? items.filter((item) => clean(item)) : [];
    if (!values.length) return `<p class="prop-detail-muted">${escapeHtml(empty)}</p>`;
    return `<ul>${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  }

  function renderHero(detail) {
    const overview = detail.overview || {};
    const price = detail.priceComparison || {};
    const trend = detail.trendProfile || {};
    const model = detail.modelExplanation || {};
    const best = bestWindow(trend);
    const line = display(overview.line, "--");
    const side = directionLabel(trend, overview);
    const bookCount = Array.isArray(price.books) ? price.books.length : 0;
    return `
      <header class="prop-detail-hero prop-detail-premium-hero">
        <div class="prop-detail-hero-main">
          <p class="prop-detail-eyebrow">Advanced Prop Detail · ${escapeHtml(display(overview.date, "Slate"))}</p>
          <h2 id="propDetailTitle">${escapeHtml(display(overview.player, "Unknown player"))}</h2>
          <p>${escapeHtml(display(overview.matchup))} · ${escapeHtml(display(overview.marketDisplay))} · ${escapeHtml(side)} ${escapeHtml(line)}</p>
        </div>
        <div class="prop-detail-badges">
          <span>${escapeHtml(display(overview.decisionLabel, "No bet"))}</span>
          <span>${escapeHtml(display(overview.readinessLabel, "Research only"))}</span>
          <span>${escapeHtml(display(overview.dataConfidence, "Missing"))}</span>
        </div>
        <div class="prop-detail-hero-kpis">
          ${renderStat(best ? `${best.label} hit rate` : "Hit rate", best ? pct(best.item.pct) : "Not available", "featured")}
          ${renderStat("Model", pct(price.noVigFairEstimate?.modelProbabilityPercent))}
          ${renderStat("Book IP", pct(price.bestAvailable?.impliedProbabilityPercent))}
          ${renderStat("Edge", signedPct(price.noVigFairEstimate?.edgePercent), asNumber(price.noVigFairEstimate?.edgePercent, 0) >= 0 ? "positive" : "negative")}
          ${renderStat("Best odds", formatOdds(price.bestAvailable?.americanOdds))}
          ${renderStat("Books", bookCount ? `Best of ${bookCount}` : "1")}
          ${renderStat("Model gate", model.productionStatus || model.modelStatus || "research_only")}
        </div>
      </header>
    `;
  }

  function renderTabNav() {
    const tabs = ["Overview", "Hit Rates", "Sportsbooks", "Model", "Risk"];
    return `<nav class="prop-detail-tabbar" aria-label="Advanced prop sections">${tabs.map((tab, index) => `<a href="#propDetail${escapeHtml(tab.replace(/\s+/g, ""))}" class="${index === 0 ? "is-active" : ""}">${escapeHtml(tab)}</a>`).join("")}</nav>`;
  }

  function renderHitRateCards(profile, overview) {
    const side = directionLabel(profile, overview);
    const line = display(profile?.line ?? overview.line, "--");
    const cards = windowsFromProfile(profile).map(({ label, item }) => {
      const pctText = item ? pct(item.pct) : "--";
      const width = item ? Math.max(0, Math.min(100, item.pct)) : 0;
      const tier = !item ? "missing" : item.pct >= 70 ? "high" : item.pct >= 55 ? "mid" : "low";
      return `
        <div class="prop-detail-hit-card is-${tier}">
          <div><span>${escapeHtml(label)}</span><strong>${escapeHtml(pctText)}</strong></div>
          <div class="prop-detail-hit-track"><i style="width:${width}%"></i></div>
          <em>${escapeHtml(sampleText(item))}</em>
        </div>
      `;
    }).join("");
    return `
      <section id="propDetailHitRates" class="prop-detail-panel prop-detail-hit-panel">
        <div class="prop-detail-section-heading">
          <div><h3>Hit-rate profile</h3><p>Backend-computed from cached game logs for ${escapeHtml(side)} ${escapeHtml(line)}.</p></div>
          <span>${escapeHtml(display(profile?.sourceStatus, "source pending"))}</span>
        </div>
        <div class="prop-detail-hit-grid">${cards}</div>
        ${renderRecentGameGraph(profile, overview)}
        ${renderRecentGamesTable(profile, overview)}
      </section>
    `;
  }

  function renderRecentGameGraph(profile, overview) {
    const recent = Array.isArray(profile?.recentGames) ? profile.recentGames : [];
    const line = asNumber(profile?.line ?? overview.line, NaN);
    const maxValue = Math.max(1, line || 1, ...recent.map((game) => asNumber(game.value, 0)));
    if (!recent.length) return `<p class="prop-detail-muted">No recent game-log graph is available for this player/market yet.</p>`;
    const bars = recent.slice(-10).map((game) => {
      const value = asNumber(game.value, 0);
      const height = Math.max(7, Math.min(100, (value / maxValue) * 88));
      const label = `${display(game.date, "date")} ${display(game.opponent, "")}`.trim();
      return `
        <div class="prop-detail-game-bar ${game.hit ? "is-hit" : "is-miss"}" title="${escapeHtml(label)} · ${escapeHtml(display(game.value, "--"))}">
          <i style="height:${height}%"></i>
          <span>${escapeHtml(display(game.value, "--"))}</span>
        </div>
      `;
    }).join("");
    return `
      <div class="prop-detail-chart-shell">
        <div class="prop-detail-chart-heading"><h4>Recent game graph</h4><span>line ${escapeHtml(display(line, "--"))}</span></div>
        <div class="prop-detail-game-chart">${bars}</div>
      </div>
    `;
  }

  function renderRecentGamesTable(profile, overview) {
    const recent = Array.isArray(profile?.recentGames) ? profile.recentGames : [];
    if (!recent.length) return "";
    const stat = display(profile?.statKey || recent[0]?.statKey || overview.marketDisplay, "Stat");
    return `
      <div class="prop-detail-recent-table">
        <div class="prop-detail-table-head"><span>Date</span><span>Opp</span><span>${escapeHtml(stat)}</span><span>Result</span></div>
        ${recent.slice(-10).reverse().map((game) => `
          <div class="prop-detail-table-row ${game.hit ? "is-hit" : "is-miss"}">
            <span>${escapeHtml(display(game.date, "--"))}</span>
            <span>${escapeHtml(display(game.opponent, "--"))}</span>
            <strong>${escapeHtml(display(game.value, "--"))}</strong>
            <em>${escapeHtml(game.hit ? "Hit" : "Miss")}</em>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderBooks(price) {
    const rows = Array.isArray(price?.books) ? [...price.books] : [];
    rows.sort((a, b) => asNumber(b.americanOdds, -999999) - asNumber(a.americanOdds, -999999));
    if (!rows.length) return `<p class="prop-detail-muted">No sportsbook ladder is available yet.</p>`;
    return `
      <section id="propDetailSportsbooks" class="prop-detail-panel price-panel">
        <div class="prop-detail-section-heading">
          <div><h3>Sportsbook ladder</h3><p>One prop card, multiple books. Best available price is highlighted.</p></div>
          <span>Best of ${rows.length}</span>
        </div>
        <div class="prop-detail-price-table advanced">
          ${rows.map((book, index) => `
            <div class="${index === 0 ? "is-best" : ""}">
              <span>${escapeHtml(display(book.book, "Book"))}</span>
              <strong>${escapeHtml(formatOdds(book.americanOdds))}</strong>
              <em>${escapeHtml(pct(book.impliedProbabilityPercent))} implied</em>
              ${index === 0 ? `<b>Best</b>` : ""}
            </div>
          `).join("")}
        </div>
        <p class="prop-detail-muted">${escapeHtml(display(price?.noVigFairEstimate?.note, "Fair estimate unavailable."))}</p>
      </section>
    `;
  }

  function renderOverview(detail) {
    const overview = detail.overview || {};
    const price = detail.priceComparison || {};
    const player = detail.playerContext || {};
    const game = detail.gameContext || {};
    return `
      <section id="propDetailOverview" class="prop-detail-panel prop-detail-overview-panel">
        <div class="prop-detail-section-heading"><div><h3>Prop overview</h3><p>Pricing, matchup, and context in one inspection surface.</p></div></div>
        <div class="prop-detail-metric-row">
          ${renderStat("Best book", price.bestAvailable?.book)}
          ${renderStat("Best odds", formatOdds(price.bestAvailable?.americanOdds))}
          ${renderStat("Book implied", pct(price.bestAvailable?.impliedProbabilityPercent))}
          ${renderStat("Fair odds", price.noVigFairEstimate?.fairAmericanOdds)}
          ${renderStat("Model probability", pct(price.noVigFairEstimate?.modelProbabilityPercent))}
          ${renderStat("Estimated edge", signedPct(price.noVigFairEstimate?.edgePercent))}
        </div>
        <div class="prop-detail-context-grid">
          <div><h4>Player context</h4><div class="prop-detail-metric-row compact">
            ${renderStat("Season", player.seasonAverage)}
            ${renderStat("Last 5", player.last5)}
            ${renderStat("Last 10", player.last10)}
            ${renderStat("Last 20", player.last20)}
            ${renderStat("Home/Away", player.homeAwaySplit)}
            ${renderStat("Opponent/BvP", player.opponentSplit)}
          </div></div>
          <div><h4>Game context</h4><div class="prop-detail-metric-row compact">
            ${renderStat("Park", game.park)}
            ${renderStat("Weather", game.weather)}
            ${renderStat("Lineup", game.lineupStatus)}
            ${renderStat("Pitcher", game.probablePitcher)}
            ${renderStat("Team total", game.teamTotal)}
            ${renderStat("Start", game.startTime)}
          </div></div>
        </div>
        <p class="prop-detail-muted">${escapeHtml(display(player.note))}</p>
      </section>
    `;
  }

  function renderModel(model) {
    const backtest = model?.backtest || {};
    return `
      <section id="propDetailModel" class="prop-detail-panel">
        <div class="prop-detail-section-heading"><div><h3>Model explanation</h3><p>Readiness and calibration stay explicit.</p></div><span>${escapeHtml(display(model?.productionStatus || model?.modelStatus, "research_only"))}</span></div>
        <div class="prop-detail-metric-row compact">
          ${renderStat("Status", model?.productionStatus)}
          ${renderStat("Training rows", model?.trainingRows)}
          ${renderStat("Class split", `${display(model?.positiveRows, "0")} / ${display(model?.negativeRows, "0")}`)}
          ${renderStat("Latest graded", model?.latestGradedDate)}
          ${renderStat("Calibration", model?.calibrationStatus)}
          ${renderStat("Backtest ROI", pct(backtest.roiPercent))}
        </div>
        ${renderList(model?.reasons, "No model reasons are available.")}
      </section>
    `;
  }

  function renderRisk(risk) {
    return `
      <section id="propDetailRisk" class="prop-detail-panel risk-panel">
        <div class="prop-detail-section-heading"><div><h3>Risk and trust context</h3><p>Missing inputs are never silently hidden.</p></div></div>
        <div class="prop-detail-metric-row compact">
          ${renderStat("Sample size", risk?.sampleSize)}
          ${renderStat("Suggested stake", risk?.suggestedStake)}
          ${renderStat("Active picks", risk?.exposure?.activePickCount)}
          ${renderStat("Slate exposure", `${display(risk?.exposure?.totalStakeUnits, "0")}u`)}
        </div>
        <div class="prop-detail-warning-grid">
          <div><h4>Trust warnings</h4>${renderList(risk?.trustWarnings, "No trust warnings reported.")}</div>
          <div><h4>Missing data</h4>${renderList(risk?.missingData, "No required fields are missing.")}</div>
          <div><h4>Correlation checks</h4>${renderList(risk?.correlationWarnings, "No correlation warnings reported.")}</div>
        </div>
      </section>
    `;
  }

  function renderDetail(detail) {
    const tracking = detail.tracking || {};
    const trackingPayload = encodeURIComponent(JSON.stringify(tracking.payload || {}));
    return `
      ${renderHero(detail)}
      ${renderTabNav()}
      <div class="prop-detail-grid prop-detail-grid-v2">
        ${renderOverview(detail)}
        ${renderHitRateCards(detail.trendProfile || {}, detail.overview || {})}
        ${renderBooks(detail.priceComparison || {})}
        ${renderModel(detail.modelExplanation || {})}
        ${renderRisk(detail.riskContext || {})}
      </div>
      <footer class="prop-detail-actions">
        <button type="button" class="muse-track-prop primary" data-prop-detail-save="${trackingPayload}">Save to My Picks</button>
        <button type="button" class="ghost-button" data-model-card-open="${escapeHtml(detail.overview?.market || "")}">Open Model Card</button>
        <button type="button" class="ghost-button" data-prop-detail-close>Close</button>
        <span id="propDetailSaveStatus" class="prop-detail-muted" aria-live="polite"></span>
      </footer>
    `;
  }

  async function openFromButton(button) {
    const oldText = button.textContent;
    button.disabled = true;
    button.textContent = "Loading...";
    try {
      const params = queryFromButton(button);
      const payload = await getJson(`/api/prop-detail?${params.toString()}`);
      openModal(renderDetail(payload.detail || {}));
    } catch (error) {
      console.error(error);
      openModal(`<div class="prop-detail-error"><h2>Could not load prop detail</h2><p>${escapeHtml(error.message)}</p></div>`);
    } finally {
      button.disabled = false;
      button.textContent = oldText;
    }
  }

  async function saveCurrentPick(button) {
    const status = document.getElementById("propDetailSaveStatus");
    let payload = {};
    try {
      payload = JSON.parse(decodeURIComponent(button.dataset.propDetailSave || "%7B%7D"));
    } catch {
      payload = {};
    }
    button.disabled = true;
    if (status) status.textContent = "Saving watchlist pick...";
    try {
      const response = await postJson("/api/my-picks", payload);
      if (status) status.textContent = `Saved ${display(response.pick?.player, "pick")} to My Picks.`;
      document.dispatchEvent(new CustomEvent("my-picks:changed", { detail: response }));
      button.textContent = "Saved";
    } catch (error) {
      console.error(error);
      if (status) status.textContent = `Save failed: ${error.message}`;
      button.disabled = false;
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-prop-detail-open]");
    if (!button) return;
    event.preventDefault();
    openFromButton(button);
  });

  window.MlbPropDetail = { openFromButton };
})();
