(() => {
  const STORAGE_KEYS = {
    bankroll: "baseballPropPredictor.stage3.bankroll",
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function number(value, fallback = 0) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function pct(value) {
    return `${number(value).toFixed(2)}%`;
  }

  function signedPct(value) {
    const n = number(value);
    return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
  }

  function american(value) {
    const n = number(value);
    if (!n) return "--";
    return `${n > 0 ? "+" : ""}${Math.round(n)}`;
  }

  function money(value) {
    const n = number(value);
    return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
  }

  function marketLabel(value = "") {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (m) => m.toUpperCase());
  }

  function decimalOdds(odds) {
    const n = number(odds);
    if (!n) return 0;
    return n > 0 ? 1 + n / 100 : 1 + 100 / Math.abs(n);
  }

  function kellyFraction(probabilityPercent, odds) {
    const p = Math.max(0, Math.min(1, number(probabilityPercent) / 100));
    const b = decimalOdds(odds) - 1;
    if (b <= 0) return 0;
    return Math.max(0, (b * p - (1 - p)) / b);
  }

  function getBankroll() {
    return number(localStorage.getItem(STORAGE_KEYS.bankroll), 1000) || 1000;
  }

  function setBankroll(value) {
    localStorage.setItem(STORAGE_KEYS.bankroll, String(Math.max(0, number(value, 1000))));
  }

  async function getJson(path) {
    const response = await fetch(path);
    const text = await response.text();
    let payload;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`Endpoint returned non-JSON. Status ${response.status}. First text: ${text.slice(0, 120)}`);
    }
    if (!response.ok) throw new Error(payload.error || `Request failed ${response.status}`);
    return payload;
  }

  function payloadFromPre(pre) {
    const text = pre?.textContent || "";
    const start = text.indexOf("{");
    if (start < 0) return null;
    try {
      return JSON.parse(text.slice(start));
    } catch {
      return null;
    }
  }

  function isPredictionPayload(payload) {
    return payload && (
      payload.finalProbabilityPercent != null ||
      payload.probabilityPercent != null ||
      payload.allDataProbabilityPercent != null
    ) && (payload.americanOdds != null || payload.sportsbookImpliedPercent != null || payload.impliedProbabilityPercent != null);
  }

  function probability(payload) {
    return number(payload.finalProbabilityPercent ?? payload.probabilityPercent ?? payload.allDataProbabilityPercent ?? payload.mlProbabilityPercent);
  }

  function odds(payload) {
    return number(payload.americanOdds ?? payload.odds ?? payload.latestAmericanOdds ?? -110, -110);
  }

  function updateKellyValues(container, payload) {
    const bankroll = getBankroll();
    const fullKelly = kellyFraction(probability(payload), odds(payload));
    const maxFull = bankroll * fullKelly;
    const maxHalf = maxFull / 2;
    const maxQuarter = maxFull / 4;
    const isPlayable = fullKelly > 0;

    const note = container.querySelector("[data-kelly-note]");
    if (note) {
      note.textContent = isPlayable
        ? "Positive model edge detected. Use fractional Kelly to reduce volatility."
        : "No positive Kelly stake. Treat this as a pass unless your inputs change.";
    }

    const values = [
      ["[data-kelly-full]", money(maxFull), pct(fullKelly * 100)],
      ["[data-kelly-half]", money(maxHalf), pct(fullKelly * 50)],
      ["[data-kelly-quarter]", money(maxQuarter), pct(fullKelly * 25)],
    ];

    values.forEach(([selector, amount, fraction]) => {
      const cell = container.querySelector(selector);
      if (!cell) return;
      const strong = cell.querySelector("strong");
      const small = cell.querySelector("small");
      if (strong) strong.textContent = amount;
      if (small) small.textContent = `${fraction} of bankroll`;
    });
  }

  function renderKelly(panel, payload) {
    const container = panel.querySelector("[data-stage3-kelly]");
    if (!container) return;

    if (!container.dataset.kellyMounted) {
      container.dataset.kellyMounted = "1";
      container.innerHTML = `
        <div class="stage3-card-header">
          <div>
            <p class="eyebrow">Bankroll sizing</p>
            <h3>Kelly bet size</h3>
            <p data-kelly-note></p>
          </div>
          <label class="stage3-bankroll-input">Bankroll <input type="number" min="0" step="25" value="${escapeHtml(getBankroll())}" data-stage3-bankroll /></label>
        </div>
        <div class="stage3-kelly-grid">
          <div data-kelly-full><span>Full Kelly</span><strong></strong><small></small></div>
          <div data-kelly-half><span>Half Kelly</span><strong></strong><small></small></div>
          <div data-kelly-quarter><span>Quarter Kelly</span><strong></strong><small></small></div>
        </div>
      `;

      container.querySelector("[data-stage3-bankroll]")?.addEventListener("input", (event) => {
        setBankroll(event.target.value);
        updateKellyValues(container, payload);
      });
    }

    const input = container.querySelector("[data-stage3-bankroll]");
    if (input && document.activeElement !== input) input.value = getBankroll();
    updateKellyValues(container, payload);
  }

  function lineParams(payload) {
    const active = window.BaseballPropState?.getActiveBet?.() || {};
    const query = new URLSearchParams();
    query.set("season", payload.season || active.season || "2026");
    query.set("date", payload.date || active.date || "");
    query.set("market", payload.market || active.market || "");
    query.set("player", payload.player || active.player || "");
    query.set("team", payload.team || active.team || "");
    query.set("opponent", payload.opponent || active.opponent || "");
    query.set("pitcher", payload.pitcher || active.pitcher || "");
    query.set("model_probability_percent", String(probability(payload)));
    return query;
  }

  function renderLineComparison(panel, payload) {
    const target = panel.querySelector("[data-stage3-lines]");
    target.innerHTML = `<div class="stage3-loading">Checking available books…</div>`;
    getJson(`/api/stage3/line-comparison?${lineParams(payload).toString()}`)
      .then((data) => {
        const rows = data.books || [];
        if (!rows.length) {
          target.innerHTML = `
            <div class="stage3-empty-state">
              <strong>No alternate books found for this exact prop.</strong>
              <p>Run Odds Movement Sync after pulling props, or loosen player/team filters by checking the raw snapshot file.</p>
            </div>
          `;
          return;
        }
        const singleBookNote = rows.length === 1
          ? `<p class="model-note stage3-single-book-note">Only 1 book found. Add more sportsbooks to your Odds Movement Sync to unlock cross-book line shopping.</p>`
          : "";
        target.innerHTML = `
          <div class="stage3-card-header compact">
            <div>
              <p class="eyebrow">Line shopping</p>
              <h3>Best available book</h3>
              <p>${escapeHtml(data.best?.sportsbook || "--")} currently grades best at ${american(data.best?.americanOdds)} with ${signedPct(data.best?.edgePercent)} edge.</p>
            </div>
          </div>
          ${singleBookNote}
          <div class="stage3-table-wrap">
            <table class="stage3-table">
              <thead><tr><th>Book</th><th>Line</th><th>Odds</th><th>Implied</th><th>Edge</th><th>EV/unit</th><th>Kelly</th></tr></thead>
              <tbody>
                ${rows.map((row) => `
                  <tr class="${row.isBest ? "is-best" : ""}">
                    <td>${row.isBest ? "★ " : ""}${escapeHtml(row.sportsbook)}</td>
                    <td>${escapeHtml(row.line)}</td>
                    <td>${american(row.americanOdds)}</td>
                    <td>${pct(row.impliedProbabilityPercent)}</td>
                    <td class="${number(row.edgePercent) >= 0 ? "positive" : "negative"}">${signedPct(row.edgePercent)}</td>
                    <td class="${number(row.evPerUnit) >= 0 ? "positive" : "negative"}">${number(row.evPerUnit).toFixed(3)}</td>
                    <td>${pct(row.kellyFractionPercent)}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        `;
      })
      .catch((error) => {
        target.innerHTML = `<div class="stage3-empty-state"><strong>Line comparison failed.</strong><p>${escapeHtml(error.message)}</p></div>`;
      });
  }

  function ensurePredictionAddOns(pre, payload) {
    if (!pre?.id || !isPredictionPayload(payload)) return;
    const id = `stage3Addons-${pre.id}`;
    let panel = document.getElementById(id);
    if (!panel) {
      panel = document.createElement("section");
      panel.id = id;
      panel.className = "stage3-addons";
      panel.innerHTML = `<div class="stage3-card" data-stage3-kelly></div><div class="stage3-card" data-stage3-lines></div>`;
      const resultCard = pre.parentElement?.querySelector(`[data-result-card-for="${pre.id}"]`);
      (resultCard || pre).insertAdjacentElement(resultCard ? "afterend" : "beforebegin", panel);
    }
    renderKelly(panel, payload);
    renderLineComparison(panel, payload);
  }

  function observePredictionOutputs() {
    $$("pre.json-output").forEach((pre) => {
      if (pre.dataset.stage3Observed) return;
      pre.dataset.stage3Observed = "1";
      const run = () => {
        const payload = payloadFromPre(pre);
        if (payload) ensurePredictionAddOns(pre, payload);
      };
      new MutationObserver(run).observe(pre, { childList: true, characterData: true, subtree: true });
      run();
    });
  }

  function renderSteamAlert(alert) {
    const tone = alert.tone === "steam" ? "steam" : "drift";
    return `
      <article class="stage3-steam-alert ${tone}">
        <div>
          <strong>${escapeHtml(alert.player || "Unknown prop")}</strong>
          <span>${escapeHtml(marketLabel(alert.market))}${alert.team || alert.opponent ? ` · ${escapeHtml(alert.team || "--")} vs ${escapeHtml(alert.opponent || "--")}` : ""}</span>
        </div>
        <div class="stage3-steam-move">
          <span>Line ${escapeHtml(alert.firstLine)} → ${escapeHtml(alert.latestLine)}</span>
          <strong>${american(alert.firstAmericanOdds)} → ${american(alert.latestAmericanOdds)}</strong>
          <small>${signedPct(alert.impliedProbabilityMovePercent)} implied</small>
        </div>
        <p>${escapeHtml(alert.movementSummary || "Meaningful market move detected.")}</p>
      </article>
    `;
  }

  function ensureSteamFeed() {
    const page = document.getElementById("appPage-today-board");
    if (!page || document.getElementById("stage3SteamFeed")) return;
    const section = document.createElement("details");
    section.id = "stage3SteamFeed";
    section.className = "app-page-section stage3-steam-section stage3-collapsible-section";
    section.innerHTML = `
      <summary class="app-page-section-header stage3-collapsible-summary">
        <span class="eyebrow">Market movement</span>
        <span class="stage3-summary-title">Line Movement Alerts ↓</span>
        <span>Props with a 0.5+ line move or 15+ cent odds move since the first saved snapshot.</span>
      </summary>
      <div class="app-page-section-body">
        <div class="stage3-steam-toolbar">
          <label>Date <input type="date" data-stage3-steam-date /></label>
          <label>Market
            <select data-stage3-steam-market>
              <option value="">All markets</option>
              <option value="batter_hits">Batter hits</option>
              <option value="batter_total_bases">Batter total bases</option>
              <option value="batter_home_runs">Batter home runs</option>
              <option value="pitcher_strikeouts">Pitcher strikeouts</option>
              <option value="pitcher_hits_allowed">Pitcher hits allowed</option>
              <option value="pitcher_earned_runs">Pitcher earned runs</option>
            </select>
          </label>
          <button type="button" data-stage3-load-steam>Refresh alerts</button>
        </div>
        <div class="stage3-steam-list" data-stage3-steam-list><div class="stage3-empty-state"><strong>Alerts are collapsed by default.</strong><p>Open this section and refresh when you want to inspect market movement.</p></div></div>
      </div>
    `;
    const onboarding = document.getElementById("firstRunOnboarding");
    (onboarding || page.firstChild)?.insertAdjacentElement(onboarding ? "afterend" : "beforebegin", section);

    const dateInput = section.querySelector("[data-stage3-steam-date]");
    const activeDate = window.BaseballPropState?.getActiveBet?.().date || new Date().toISOString().slice(0, 10);
    if (dateInput) dateInput.value = activeDate;
    section.querySelector("[data-stage3-load-steam]")?.addEventListener("click", () => loadSteamFeed(section));
    section.querySelector("[data-stage3-steam-market]")?.addEventListener("change", () => {
      if (section.open) loadSteamFeed(section);
    });
    section.addEventListener("toggle", () => {
      if (section.open && !section.dataset.stage3Loaded) loadSteamFeed(section);
    });
  }

  function loadSteamFeed(section = document.getElementById("stage3SteamFeed")) {
    if (!section) return;
    const list = section.querySelector("[data-stage3-steam-list]");
    const query = new URLSearchParams({
      season: "2026",
      date: section.querySelector("[data-stage3-steam-date]")?.value || "",
      market: section.querySelector("[data-stage3-steam-market]")?.value || "",
      limit: "12",
    });
    list.innerHTML = `<div class="stage3-loading">Loading steam alerts…</div>`;
    getJson(`/api/stage3/steam-alerts?${query.toString()}`)
      .then((payload) => {
        section.dataset.stage3Loaded = "1";
        const alerts = payload.alerts || [];
        list.innerHTML = alerts.length
          ? alerts.map(renderSteamAlert).join("")
          : `<div class="stage3-empty-state"><strong>No steam alerts for this filter.</strong><p>Try all markets or run Odds Movement Sync to create fresh snapshots.</p></div>`;
      })
      .catch((error) => {
        list.innerHTML = `<div class="stage3-empty-state"><strong>Steam feed failed.</strong><p>${escapeHtml(error.message)}</p></div>`;
      });
  }

  function ensurePnlAnalytics() {
    const page = document.getElementById("appPage-my-picks");
    if (!page || document.getElementById("stage3PnlAnalytics")) return;
    const section = document.createElement("section");
    section.id = "stage3PnlAnalytics";
    section.className = "app-page-section stage3-pnl-section";
    section.innerHTML = `
      <div class="app-page-section-header">
        <p class="eyebrow">Performance</p>
        <h1>Bet Tracker Analytics</h1>
        <p>Backtested P&L, market splits, streaks, and model-health warnings from existing graded results.</p>
      </div>
      <div class="app-page-section-body">
        <div class="stage3-steam-toolbar">
          <label>Season <select data-stage3-pnl-season><option value="2026">2026</option><option value="2025">2025</option><option value="2024">2024</option></select></label>
          <label>Market <select data-stage3-pnl-market><option value="">All markets</option><option value="batter_hits">Batter hits</option><option value="batter_total_bases">Batter total bases</option><option value="batter_home_runs">Batter home runs</option><option value="pitcher_strikeouts">Pitcher strikeouts</option><option value="pitcher_hits_allowed">Pitcher hits allowed</option><option value="pitcher_earned_runs">Pitcher earned runs</option></select></label>
          <button type="button" data-stage3-load-pnl>Load analytics</button>
        </div>
        <div data-stage3-pnl-body>
          <div class="stage3-empty-state stage3-load-card">
            <strong>Load analytics when you need them.</strong>
            <p>This avoids parsing the backtest CSV every time you open My Picks.</p>
            <button type="button" data-stage3-load-pnl-inline>Load analytics</button>
          </div>
        </div>
      </div>
    `;
    page.insertBefore(section, page.firstChild);
    section.querySelector("[data-stage3-load-pnl]")?.addEventListener("click", () => loadPnlAnalytics(section));
    section.querySelector("[data-stage3-load-pnl-inline]")?.addEventListener("click", () => loadPnlAnalytics(section));
    ["[data-stage3-pnl-season]", "[data-stage3-pnl-market]"].forEach((selector) => {
      section.querySelector(selector)?.addEventListener("change", () => {
        if (section.dataset.pnlLoaded === "1") loadPnlAnalytics(section);
      });
    });
  }

  function sparkline(points = []) {
    if (!points.length) return "";
    const vals = points.map((p) => number(p.cumulativeUnits));
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const span = max - min || 1;
    return vals.map((v, i) => {
      const x = points.length === 1 ? 0 : (i / (points.length - 1)) * 100;
      const y = 100 - ((v - min) / span) * 100;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
  }

  function pnlCacheKey(section) {
    const season = section.querySelector("[data-stage3-pnl-season]")?.value || "2026";
    const market = section.querySelector("[data-stage3-pnl-market]")?.value || "";
    return `baseballPropPredictor.stage3.pnl.${season}.${market || "all"}`;
  }

  function loadPnlAnalytics(section = document.getElementById("stage3PnlAnalytics")) {
    if (!section) return;
    const body = section.querySelector("[data-stage3-pnl-body]");
    const query = new URLSearchParams({
      season: section.querySelector("[data-stage3-pnl-season]")?.value || "2026",
      market: section.querySelector("[data-stage3-pnl-market]")?.value || "",
    });
    const cacheKey = pnlCacheKey(section);
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        if (Date.now() - parsed.savedAt < 60 * 60 * 1000) {
          section.dataset.pnlLoaded = "1";
          renderPnlAnalytics(body, parsed.payload);
          return;
        }
      } catch {
        sessionStorage.removeItem(cacheKey);
      }
    }
    body.innerHTML = `<div class="stage3-loading">Loading P&L analytics…</div>`;
    getJson(`/api/stage3/pnl-analytics?${query.toString()}`)
      .then((payload) => {
        section.dataset.pnlLoaded = "1";
        sessionStorage.setItem(cacheKey, JSON.stringify({ savedAt: Date.now(), payload }));
        renderPnlAnalytics(body, payload);
      })
      .catch((error) => {
        body.innerHTML = `<div class="stage3-empty-state"><strong>P&L analytics failed.</strong><p>${escapeHtml(error.message)}</p></div>`;
      });
  }

  function renderPnlAnalytics(body, payload) {
        const summary = payload.summary || {};
        const byMarket = payload.byMarket || [];
        const byDay = payload.byDay || [];
        const audit = payload.modelAudit || {};
        body.innerHTML = `
          <div class="stage3-pnl-grid">
            <div><span>Units</span><strong class="${number(summary.profitUnits) >= 0 ? "positive" : "negative"}">${number(summary.profitUnits).toFixed(2)}u</strong><small>ROI ${pct(summary.roiPercent)}</small></div>
            <div><span>Record</span><strong>${summary.wins || 0}-${summary.losses || 0}-${summary.pushes || 0}</strong><small>${pct(summary.winRate)} win rate</small></div>
            <div><span>Longest W/L streak</span><strong>${summary.longestWinStreak || 0}/${summary.longestLossStreak || 0}</strong><small>Current: ${escapeHtml(summary.currentStreak?.count || 0)} ${escapeHtml(summary.currentStreak?.type || "")}</small></div>
            <div><span>Model warnings</span><strong>${escapeHtml(audit.warningRows ?? "--")}</strong><small>Audit ROI ${escapeHtml(audit.roiPercent ?? "--")}%</small></div>
          </div>
          <div class="stage3-chart-card">
            <div class="stage3-card-header compact"><div><p class="eyebrow">ROI curve</p><h3>Cumulative units by day</h3></div></div>
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="stage3-sparkline"><polyline points="${sparkline(byDay)}"></polyline></svg>
          </div>
          <div class="stage3-split-grid">
            <div class="stage3-card">
              <div class="stage3-card-header compact"><div><p class="eyebrow">Markets</p><h3>Win rate by market</h3></div></div>
              <div class="stage3-table-wrap"><table class="stage3-table"><thead><tr><th>Market</th><th>Picks</th><th>Win Rate</th><th>Units</th></tr></thead><tbody>
                ${byMarket.slice(0, 8).map((row) => `<tr><td>${escapeHtml(marketLabel(row.market))}</td><td>${escapeHtml(row.picks)}</td><td>${pct(row.winRate)}</td><td class="${number(row.profitUnits) >= 0 ? "positive" : "negative"}">${number(row.profitUnits).toFixed(2)}u</td></tr>`).join("")}
              </tbody></table></div>
            </div>
            <div class="stage3-card">
              <div class="stage3-card-header compact"><div><p class="eyebrow">Model health</p><h3>Top audit warnings</h3></div></div>
              <div class="stage3-warning-list">
                ${(audit.topWarnings || []).length ? (audit.topWarnings || []).map((w) => `<article><strong>${escapeHtml(w.player || w.market || "Warning")}</strong><span>${escapeHtml(marketLabel(w.market))} · ${escapeHtml(w.warnings || "math warning")}</span></article>`).join("") : `<div class="stage3-empty-state"><strong>No audit warnings found.</strong></div>`}
              </div>
            </div>
          </div>
        `;
  }

  function init() {
    observePredictionOutputs();
    ensureSteamFeed();
    ensurePnlAnalytics();
    window.setTimeout(() => {
      observePredictionOutputs();
      ensureSteamFeed();
      ensurePnlAnalytics();
    }, 50);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
