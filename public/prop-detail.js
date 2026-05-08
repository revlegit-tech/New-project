(() => {
  const ACTION_HEADER = "X-Baseball-Prop-Action";

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

  function pct(value) {
    const text = clean(value);
    return text ? `${text}%` : "Not available";
  }

  function queryFromButton(button) {
    const params = new URLSearchParams();
    const map = {
      id: button.dataset.propId,
      date: button.dataset.date || document.querySelector("#simpleDate")?.value,
      player: button.dataset.player,
      team: button.dataset.team,
      opponent: button.dataset.opponent,
      market: button.dataset.market,
      line: button.dataset.line,
      americanOdds: button.dataset.odds,
      book: button.dataset.book,
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
    modal.className = "prop-detail-modal";
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

  function renderStat(label, value) {
    return `<div class="prop-detail-stat"><span>${escapeHtml(label)}</span><strong>${escapeHtml(display(value))}</strong></div>`;
  }

  function renderList(items, empty = "None reported") {
    const values = Array.isArray(items) ? items.filter((item) => clean(item)) : [];
    if (!values.length) return `<p class="prop-detail-muted">${escapeHtml(empty)}</p>`;
    return `<ul>${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  }

  function renderBooks(books) {
    const rows = Array.isArray(books) ? books : [];
    if (!rows.length) return `<p class="prop-detail-muted">No book comparison is available yet.</p>`;
    return `
      <div class="prop-detail-price-table">
        ${rows.map((book) => `
          <div>
            <span>${escapeHtml(display(book.book, "Book"))}</span>
            <strong>${escapeHtml(display(book.americanOdds))}</strong>
            <em>${escapeHtml(pct(book.impliedProbabilityPercent))} implied</em>
          </div>
        `).join("")}
      </div>
    `;
  }



  function normalizeWindow(value) {
    if (!value) return null;
    if (typeof value === "number") return { pct: value, hits: null, total: null };
    if (typeof value === "string") {
      const parsed = Number(value.replace("%", ""));
      return Number.isFinite(parsed) ? { pct: parsed, hits: null, total: null } : null;
    }
    const pct = Number(value.pct ?? value.percent ?? value.rate ?? value.value);
    if (!Number.isFinite(pct)) return null;
    return {
      pct: pct <= 1 && pct >= -1 ? pct * 100 : pct,
      hits: value.hits ?? value.successes ?? null,
      total: value.total ?? value.attempts ?? value.n ?? null,
    };
  }

  function renderTrendProfile(profile) {
    const windows = profile?.windows || {};
    const recent = Array.isArray(profile?.recentGames) ? profile.recentGames : [];
    const keys = [["L5", "L5"], ["L10", "L10"], ["L20", "L20"], ["H2H", "H2H"], ["season", "2026"], ["prevSeason", "2025"]];
    const bars = keys.map(([key, label]) => {
      const item = normalizeWindow(windows[key] ?? windows[key.toLowerCase()]);
      const width = item ? Math.max(0, Math.min(100, item.pct)) : 0;
      const sample = item && item.hits !== null && item.total !== null ? `${item.hits}/${item.total}` : "--";
      return `
        <div class="prop-detail-trend-row">
          <span>${escapeHtml(label)}</span>
          <div class="prop-detail-trend-track"><i style="width:${width}%"></i></div>
          <strong>${escapeHtml(item ? `${Math.round(item.pct)}%` : "--")}</strong>
          <em>${escapeHtml(sample)}</em>
        </div>
      `;
    }).join("");

    const gameBars = recent.slice(-20).map((game) => {
      const value = Number(game.value);
      const height = Number.isFinite(value) ? Math.max(6, Math.min(100, value * 18)) : 6;
      const hitClass = game.hit ? "is-hit" : "is-miss";
      const label = `${display(game.date, "date")} ${display(game.opponent, "")}`.trim();
      return `
        <div class="prop-detail-game-bar ${hitClass}" title="${escapeHtml(label)} · ${escapeHtml(display(game.value, "--"))}">
          <i style="height:${height}%"></i>
          <span>${escapeHtml(display(game.value, "--"))}</span>
        </div>
      `;
    }).join("");

    const sourceStatus = display(windows.sourceStatus || profile?.sourceStatus, recent.length ? "cached game logs" : "Missing game-log series");
    return `
      <section class="prop-detail-panel price-panel">
        <h3>Hit-Rate Profile</h3>
        <p class="prop-detail-muted">Percentages are generated by the backend from cached StatsAPI game logs for this player, line, market, and side.</p>
        <div class="prop-detail-trend-grid">${bars}</div>
        <h4>Recent game graph</h4>
        ${recent.length ? `<div class="prop-detail-game-chart">${gameBars}</div>` : `<p class="prop-detail-muted">No recent game-log series is available for this player/market yet.</p>`}
        <p class="prop-detail-muted">Source: ${escapeHtml(sourceStatus)}</p>
      </section>
    `;
  }


  function renderDetail(detail) {
    const overview = detail.overview || {};
    const price = detail.priceComparison || {};
    const model = detail.modelExplanation || {};
    const player = detail.playerContext || {};
    const game = detail.gameContext || {};
    const risk = detail.riskContext || {};
    const tracking = detail.tracking || {};
    const trend = detail.trendProfile || {};
    const trackingPayload = encodeURIComponent(JSON.stringify(tracking.payload || {}));
    const backtest = model.backtest || {};

    return `
      <header class="prop-detail-hero">
        <div>
          <p class="prop-detail-eyebrow">Prop Detail</p>
          <h2 id="propDetailTitle">${escapeHtml(display(overview.player, "Unknown player"))}</h2>
          <p>${escapeHtml(display(overview.matchup))} · ${escapeHtml(display(overview.marketDisplay))} · Line ${escapeHtml(display(overview.line, "--"))}</p>
        </div>
        <div class="prop-detail-badges">
          <span>${escapeHtml(display(overview.decisionLabel, "No bet"))}</span>
          <span>${escapeHtml(display(overview.readinessLabel, "Research only"))}</span>
          <span>${escapeHtml(display(overview.dataConfidence, "Missing"))}</span>
        </div>
      </header>

      <div class="prop-detail-grid">
        <section class="prop-detail-panel price-panel">
          <h3>Price Comparison</h3>
          <div class="prop-detail-metric-row">
            ${renderStat("Best book", price.bestAvailable?.book)}
            ${renderStat("Best odds", price.bestAvailable?.americanOdds)}
            ${renderStat("Book implied", pct(price.bestAvailable?.impliedProbabilityPercent))}
            ${renderStat("Fair odds", price.noVigFairEstimate?.fairAmericanOdds)}
            ${renderStat("Model probability", pct(price.noVigFairEstimate?.modelProbabilityPercent))}
            ${renderStat("Estimated edge", pct(price.noVigFairEstimate?.edgePercent))}
          </div>
          ${renderBooks(price.books)}
          <p class="prop-detail-muted">${escapeHtml(display(price.noVigFairEstimate?.note, "Fair estimate unavailable."))}</p>
        </section>

        ${renderTrendProfile(trend)}

        <section class="prop-detail-panel">
          <h3>Model Explanation</h3>
          <div class="prop-detail-metric-row compact">
            ${renderStat("Status", model.productionStatus)}
            ${renderStat("Training rows", model.trainingRows)}
            ${renderStat("Class split", `${display(model.positiveRows, "0")} / ${display(model.negativeRows, "0")}`)}
            ${renderStat("Latest graded", model.latestGradedDate)}
            ${renderStat("Calibration", model.calibrationStatus)}
            ${renderStat("Backtest ROI", pct(backtest.roiPercent))}
          </div>
          ${renderList(model.reasons, "No model reasons are available.")}
        </section>

        <section class="prop-detail-panel">
          <h3>Player Context</h3>
          <div class="prop-detail-metric-row compact">
            ${renderStat("Season", player.seasonAverage)}
            ${renderStat("Last 5", player.last5)}
            ${renderStat("Last 10", player.last10)}
            ${renderStat("Last 20", player.last20)}
            ${renderStat("Home/Away", player.homeAwaySplit)}
            ${renderStat("Opponent/BvP", player.opponentSplit)}
          </div>
          <p class="prop-detail-muted">${escapeHtml(display(player.note))}</p>
        </section>

        <section class="prop-detail-panel">
          <h3>Game Context</h3>
          <div class="prop-detail-metric-row compact">
            ${renderStat("Park", game.park)}
            ${renderStat("Weather", game.weather)}
            ${renderStat("Lineup", game.lineupStatus)}
            ${renderStat("Pitcher", game.probablePitcher)}
            ${renderStat("Team total", game.teamTotal)}
            ${renderStat("Start", game.startTime)}
          </div>
        </section>

        <section class="prop-detail-panel risk-panel">
          <h3>Risk Context</h3>
          <div class="prop-detail-metric-row compact">
            ${renderStat("Sample size", risk.sampleSize)}
            ${renderStat("Suggested stake", risk.suggestedStake)}
            ${renderStat("Active picks", risk.exposure?.activePickCount)}
            ${renderStat("Slate exposure", `${display(risk.exposure?.totalStakeUnits, "0")}u`)}
          </div>
          <h4>Trust warnings</h4>
          ${renderList(risk.trustWarnings, "No trust warnings reported.")}
          <h4>Missing data</h4>
          ${renderList(risk.missingData, "No required fields are missing.")}
          <h4>Correlation checks</h4>
          ${renderList(risk.correlationWarnings, "No correlation warnings reported.")}
        </section>
      </div>

      <footer class="prop-detail-actions">
        <button type="button" class="muse-track-prop primary" data-prop-detail-save="${trackingPayload}">Save to My Picks</button>
        <button type="button" class="ghost-button" data-model-card-open="${escapeHtml(overview.market)}">Open Model Card</button>
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
