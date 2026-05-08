(() => {
  const ACTION_HEADER = "X-Baseball-Prop-Action";
  const $ = (selector, root = document) => root.querySelector(selector);

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function api(path, options = {}) {
    const next = { ...options };
    const headers = new Headers(next.headers || {});
    if (String(next.method || "GET").toUpperCase() === "POST") {
      headers.set(ACTION_HEADER, "1");
      headers.set("Content-Type", "application/json");
    }
    next.headers = headers;
    const response = await fetch(path, next);
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (!response.ok) throw new Error(payload.error || `Request failed ${response.status}`);
    return payload;
  }

  function pickFromButton(button) {
    return {
      date: $("#edgeBoardDate")?.value || $("#simpleDate")?.value || new Date().toISOString().slice(0, 10),
      player: button.dataset.player || "",
      team: button.dataset.team || "",
      opponent: button.dataset.opponent || "",
      market: button.dataset.market || "",
      marketDisplay: button.dataset.marketDisplay || "",
      side: button.dataset.side || "Over",
      line: button.dataset.line || "",
      americanOdds: button.dataset.odds || "",
      book: button.dataset.book || "Best available",
      decisionLabel: button.dataset.decision || "Watchlist",
      readinessLabel: button.dataset.readiness || "Research only",
      confidence: button.dataset.confidence || "Research",
      modelProbabilityPercent: button.dataset.probability || "",
      impliedProbabilityPercent: button.dataset.implied || "",
      edgePercent: button.dataset.edge || "",
      latestGradedDate: button.dataset.latestGraded || "",
      suggestedStake: button.dataset.suggestedStake || "Research only",
      source: "edge_board",
      status: "Watching",
      stakeUnits: 0,
    };
  }

  async function createPickFromButton(button) {
    const oldText = button.textContent;
    button.disabled = true;
    button.textContent = "Tracking...";
    try {
      const payload = await api("/api/my-picks", { method: "POST", body: JSON.stringify(pickFromButton(button)) });
      button.textContent = "Tracked";
      button.classList.add("is-tracked");
      document.dispatchEvent(new CustomEvent("my-picks:changed", { detail: payload }));
      return payload;
    } catch (error) {
      button.textContent = oldText;
      button.disabled = false;
      throw error;
    }
  }

  function exposureList(items, emptyText) {
    if (!items || !items.length) return `<p class="my-picks-muted">${escapeHtml(emptyText)}</p>`;
    return `<ul class="my-picks-exposure-list">${items.slice(0, 6).map((item) => `<li><span>${escapeHtml(item.key)}</span><strong>${escapeHtml(Number(item.units || 0).toFixed(2))}u</strong></li>`).join("")}</ul>`;
  }

  function renderSettings(settings) {
    const methods = ["flat", "half_kelly", "quarter_kelly", "capped_kelly"];
    return `<form id="bankrollSettingsForm" class="bankroll-settings-form">
      <label>Bankroll <input name="bankroll" type="number" min="0" step="1" value="${escapeHtml(settings.bankroll)}" /></label>
      <label>Unit size <input name="defaultUnitSize" type="number" min="0.01" step="0.5" value="${escapeHtml(settings.defaultUnitSize)}" /></label>
      <label>Max units / bet <input name="maxUnitsPerBet" type="number" min="0" step="0.05" value="${escapeHtml(settings.maxUnitsPerBet)}" /></label>
      <label>Max bets / slate <input name="maxBetsPerSlate" type="number" min="1" step="1" value="${escapeHtml(settings.maxBetsPerSlate)}" /></label>
      <label>Max game exposure <input name="maxExposurePerGameUnits" type="number" min="0" step="0.05" value="${escapeHtml(settings.maxExposurePerGameUnits)}" /></label>
      <label>Max player exposure <input name="maxExposurePerPlayerUnits" type="number" min="0" step="0.05" value="${escapeHtml(settings.maxExposurePerPlayerUnits)}" /></label>
      <label>Stake method <select name="stakingMethod">${methods.map((method) => `<option value="${method}" ${settings.stakingMethod === method ? "selected" : ""}>${method.replaceAll("_", " ")}</option>`).join("")}</select></label>
      <button type="submit">Save Risk Settings</button>
    </form>`;
  }

  function renderPickRows(picks) {
    if (!picks.length) return `<div class="my-picks-empty"><h3>No tracked picks yet</h3><p>Use Track from Today’s Edge Board to save a watchlist item without mixing it into model backtests.</p></div>`;
    return `<div class="my-picks-list">${picks.map((pick) => `<article class="my-pick-card" data-pick-id="${escapeHtml(pick.id)}">
      <div>
        <div class="my-pick-title-row"><span class="edge-decision-badge decision-watch">${escapeHtml(pick.status)}</span><span class="edge-readiness-badge">${escapeHtml(pick.readinessLabel || "Research only")}</span></div>
        <h3>${escapeHtml(pick.player || pick.marketDisplay || pick.market)}</h3>
        <p>${escapeHtml([pick.team, pick.opponent].filter(Boolean).join(" vs ") || "Game unavailable")} · ${escapeHtml(pick.marketDisplay || pick.market)} · Line ${escapeHtml(pick.line || "--")} · ${escapeHtml(pick.americanOdds || "--")}</p>
        <p class="my-picks-muted">${escapeHtml(pick.decisionLabel || "Watchlist")} · ${escapeHtml(pick.confidence || "Research")} · Latest graded ${escapeHtml(pick.latestGradedDate || "not available")}</p>
        ${(pick.warnings || []).length ? `<div class="edge-warning-line">${escapeHtml(pick.warnings[0])}</div>` : ""}
      </div>
      <div class="my-pick-controls">
        <label>Status <select data-pick-status>${["Watching", "Placed", "Void", "Won", "Lost", "Pushed", "Cashout"].map((status) => `<option value="${status}" ${pick.status === status ? "selected" : ""}>${status}</option>`).join("")}</select></label>
        <label>Stake units <input data-pick-stake type="number" step="0.05" min="0" value="${escapeHtml(pick.stakeUnits || 0)}" /></label>
        <label>Profit units <input data-pick-profit type="number" step="0.05" value="${escapeHtml(pick.profitUnits || 0)}" /></label>
        <button type="button" data-update-pick>Update</button>
      </div>
    </article>`).join("")}</div>`;
  }

  function render(payload) {
    const root = $("#myPicksApp");
    if (!root) return;
    const settings = payload.settings || {};
    const exposure = payload.exposure || {};
    root.innerHTML = `<section class="my-picks-hero"><div><p class="eyebrow">Risk controls</p><h2>My Picks & Slate Exposure</h2><p>Saved picks are user tracking records. They stay separate from model suggestions, model cards, and backtest performance.</p></div><button type="button" id="myPicksRefresh">Refresh</button></section>
      <section class="my-picks-exposure-grid"><div><span>Active picks</span><strong>${escapeHtml(exposure.activePickCount || 0)}</strong></div><div><span>Stake exposure</span><strong>${escapeHtml(Number(exposure.totalStakeUnits || 0).toFixed(2))}u</strong></div><div><span>Exposure amount</span><strong>$${escapeHtml(Number(exposure.totalStakeAmount || 0).toFixed(2))}</strong></div><div><span>Tracked P/L</span><strong>${escapeHtml(Number(exposure.profitUnits || 0).toFixed(2))}u</strong></div></section>
      <section class="my-picks-two-column"><div class="my-picks-panel"><h3>Bankroll settings</h3>${renderSettings(settings)}</div><div class="my-picks-panel"><h3>Exposure warnings</h3>${exposure.warnings && exposure.warnings.length ? `<ul class="muse-warning-list">${exposure.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>` : `<p class="my-picks-muted">No exposure cap warnings.</p>`}<h3>By game</h3>${exposureList(exposure.byGameUnits, "No game exposure yet.")}<h3>By player</h3>${exposureList(exposure.byPlayerUnits, "No player exposure yet.")}</div></section>
      <section class="my-picks-panel"><h3>Tracked picks</h3>${renderPickRows(payload.picks || [])}</section>`;
  }

  async function load() {
    const root = $("#myPicksApp");
    if (!root) return;
    root.innerHTML = `<div class="my-picks-empty">Loading picks and exposure…</div>`;
    try { render(await api("/api/my-picks")); }
    catch (error) { root.innerHTML = `<div class="my-picks-empty error">Could not load My Picks: ${escapeHtml(error.message)}</div>`; }
  }

  async function saveSettings(form) {
    const data = Object.fromEntries(new FormData(form).entries());
    data.conservativeMode = true;
    await api("/api/bankroll/settings", { method: "POST", body: JSON.stringify(data) });
    await load();
  }

  async function updatePick(card) {
    await api("/api/my-picks/update", { method: "POST", body: JSON.stringify({ id: card.dataset.pickId, status: $("[data-pick-status]", card)?.value || "Watching", stakeUnits: $("[data-pick-stake]", card)?.value || 0, profitUnits: $("[data-pick-profit]", card)?.value || 0 }) });
    await load();
  }

  function ensureMount() {
    if ($("#myPicksApp")) return true;
    const page = $("#appPage-my-picks");
    if (!page) return false;
    const mount = document.createElement("section");
    mount.id = "myPicksApp";
    mount.className = "my-picks-app";
    page.prepend(mount);
    return true;
  }

  function init() {
    if (!ensureMount()) return;
    load();
    document.addEventListener("my-picks:changed", load);
    document.addEventListener("click", async (event) => {
      if (event.target.closest("#myPicksRefresh")) load();
      const update = event.target.closest("[data-update-pick]");
      if (update) updatePick(update.closest(".my-pick-card"));
    });
    document.addEventListener("submit", (event) => {
      const form = event.target.closest("#bankrollSettingsForm");
      if (!form) return;
      event.preventDefault();
      saveSettings(form).catch((error) => console.error(error));
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
  window.MlbMyPicks = { load, createPickFromButton };
})();
