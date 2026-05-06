(() => {
  const MARKET_DEFAULT_LINES = {
    batter_hits: "0.5",
    batter_hits_alt: "1.5",
    batter_total_bases: "1.5",
    batter_total_bases_alt: "2.5",
    batter_home_runs: "0.5",
    batter_home_runs_alt: "0.5",
    pitcher_strikeouts: "4.5",
    pitcher_strikeouts_alt: "5.5",
    pitcher_hits_allowed: "4.5",
    pitcher_hits_allowed_alt: "5.5",
    pitcher_earned_runs: "2.5",
    pitcher_earned_runs_alt: "3.5",
  };

  const FIELD_GROUPS = {
    date: ["simpleDate", "unifiedDate", "allDataDate", "dailyWorkflowDate", "pipelineDate"],
    market: ["simpleMarket", "unifiedMarket", "allDataMarket", "propMlMarket", "predictionDashboardMarket"],
    player: ["simplePlayer", "unifiedPlayer", "allDataPlayer", "propMlPlayer", "playerSearch"],
    team: ["simpleTeam", "unifiedTeam", "allDataTeam", "propMlTeam", "moneylineTeam"],
    opponent: ["simpleOpponent", "unifiedOpponent", "allDataOpponent", "propMlOpponent", "moneylineOpponent"],
    pitcher: ["simplePitcher", "unifiedPitcher", "allDataPitcher", "propMlPitcher", "pitcherSearch"],
    line: ["simpleLine", "unifiedLine", "allDataLine", "propMlLine", "propLine"],
    american_odds: ["simpleOdds", "unifiedOdds", "allDataOdds", "propMlOdds", "americanOdds"],
  };

  const DEFAULT_CONTEXT = {
    date: new Date().toISOString().slice(0, 10),
    market: "batter_total_bases",
    player: "",
    team: "",
    opponent: "",
    pitcher: "",
    line: "1.5",
    american_odds: "-110",
  };

  const STRIP_FIELDS = [
    ["player", "Player", "simplePlayer"],
    ["market", "Market", "simpleMarket"],
    ["date", "Date", "simpleDate"],
    ["line", "Line", "simpleLine"],
    ["american_odds", "Odds", "simpleOdds"],
  ];

  const state = (window.BaseballPropState = window.BaseballPropState || {});
  state.activeBet = { ...DEFAULT_CONTEXT, ...(state.activeBet || {}) };

  let syncing = false;

  function byId(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function marketLabel(value = "") {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function displayValue(field, value) {
    if (!value) return "--";
    if (field === "market") return marketLabel(value);
    if (field === "american_odds") {
      const n = Number(value);
      return Number.isFinite(n) && n > 0 ? `+${Math.round(n)}` : String(value);
    }
    return String(value);
  }

  function focusContextField(field) {
    const candidates = FIELD_GROUPS[field] || [];
    const target = candidates.map(byId).find((el) => el && !el.disabled);
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    window.setTimeout(() => target.focus({ preventScroll: true }), 250);
  }

  function createActiveBetStrip() {
    if (byId("activeBetStrip")) return byId("activeBetStrip");
    const nav = byId("appPageNav");
    if (!nav) return null;

    const strip = document.createElement("section");
    strip.id = "activeBetStrip";
    strip.className = "active-bet-strip";
    strip.setAttribute("aria-label", "Active bet context");
    strip.innerHTML = `
      <span class="active-bet-strip-label">Active bet</span>
      ${STRIP_FIELDS.map(([field, label]) => `
        <button type="button" data-active-bet-field="${field}">
          <span>${escapeHtml(label)}</span>
          <strong data-active-bet-value="${field}">--</strong>
        </button>
      `).join("")}
    `;
    nav.insertAdjacentElement("afterend", strip);
    strip.querySelectorAll("[data-active-bet-field]").forEach((button) => {
      button.addEventListener("click", () => focusContextField(button.dataset.activeBetField));
    });
    return strip;
  }

  function updateActiveBetStrip() {
    const strip = createActiveBetStrip();
    if (!strip) return;
    STRIP_FIELDS.forEach(([field]) => {
      const target = strip.querySelector(`[data-active-bet-value="${field}"]`);
      if (target) target.textContent = displayValue(field, state.activeBet[field]);
    });
  }

  function scheduleStripMount() {
    updateActiveBetStrip();
    if (!byId("activeBetStrip")) window.setTimeout(updateActiveBetStrip, 75);
  }

  function updateContext(field, value, sourceId) {
    if (!field || syncing) return;

    state.activeBet[field] = value;

    if (field === "market" && !state.activeBet.line) {
      state.activeBet.line = MARKET_DEFAULT_LINES[value] || DEFAULT_CONTEXT.line;
    }

    syncFields(sourceId);
    updateActiveBetStrip();
    window.dispatchEvent(new CustomEvent("active-bet-context-change", { detail: { ...state.activeBet, sourceId } }));
  }

  function syncFields(sourceId = "") {
    syncing = true;

    Object.entries(FIELD_GROUPS).forEach(([field, ids]) => {
      const value = state.activeBet[field];
      if (value == null) return;

      ids.forEach((id) => {
        if (id === sourceId) return;
        const el = byId(id);
        if (!el || el.matches(":focus")) return;
        if (el.tagName === "SELECT" && !Array.from(el.options).some((option) => option.value === value)) return;
        el.value = value;
      });
    });

    syncing = false;
  }

  function seedFromExistingFields() {
    Object.entries(FIELD_GROUPS).forEach(([field, ids]) => {
      const current = ids.map(byId).find((el) => el && String(el.value || "").trim());
      if (current) state.activeBet[field] = current.value;
    });

    if (!state.activeBet.line) {
      state.activeBet.line = MARKET_DEFAULT_LINES[state.activeBet.market] || DEFAULT_CONTEXT.line;
    }
  }

  function attachFieldListeners() {
    Object.entries(FIELD_GROUPS).forEach(([field, ids]) => {
      ids.forEach((id) => {
        const el = byId(id);
        if (!el || el.dataset.activeBetContext === "1") return;
        el.dataset.activeBetContext = "1";

        ["change", "input"].forEach((eventName) => {
          el.addEventListener(eventName, () => updateContext(field, el.value, id));
        });
      });
    });
  }

  function init() {
    seedFromExistingFields();
    attachFieldListeners();
    syncFields();
    scheduleStripMount();
  }

  window.BaseballPropState.getActiveBet = () => ({ ...state.activeBet });
  window.BaseballPropState.setActiveBet = (patch = {}, sourceId = "") => {
    state.activeBet = { ...state.activeBet, ...patch };
    syncFields(sourceId);
    updateActiveBetStrip();
    window.dispatchEvent(new CustomEvent("active-bet-context-change", { detail: { ...state.activeBet, sourceId } }));
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
