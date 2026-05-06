(() => {
  const STORAGE_KEYS = {
    onboardingDismissed: "baseballPropPredictor.stage2.onboardingDismissed",
    lastDailyPayload: "baseballPropPredictor.stage2.lastDailyPayload",
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

  function todayDateString() {
    return new Date().toISOString().slice(0, 10);
  }

  function marketLabel(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function asNumber(value, fallback = 0) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function storageGet(key) {
    try {
      return window.localStorage?.getItem(key);
    } catch {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      window.localStorage?.setItem(key, value);
    } catch {
      // Storage can be unavailable in private contexts. UI still works without persistence.
    }
  }

  function stepClass(state) {
    if (state === "done") return "is-done";
    if (state === "warning") return "is-warning";
    if (state === "active") return "is-active";
    return "is-idle";
  }

  function stepIcon(state) {
    if (state === "done") return "✓";
    if (state === "warning") return "!";
    if (state === "active") return "…";
    return "•";
  }

  function getDailyPayload() {
    const raw = storageGet(STORAGE_KEYS.lastDailyPayload);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  function saveDailyPayload(payload) {
    if (!payload || typeof payload !== "object") return;
    storageSet(STORAGE_KEYS.lastDailyPayload, JSON.stringify(payload));
  }

  function dailyStepState(payload, stepName) {
    if (!payload) return stepName === "before" ? "active" : "idle";
    if (payload.error) return "warning";
    if (stepName === "before") return payload.step === "before" || payload.step === "after" || payload.markets ? "done" : "active";
    if (stepName === "review") {
      const autofill = payload.autofill || {};
      if (payload.step === "before") return asNumber(autofill.updatedRows) > 0 ? "done" : "warning";
      return payload.step === "after" || payload.markets ? "done" : "idle";
    }
    if (stepName === "after") return payload.step === "after" || payload.markets ? "done" : payload.step === "before" ? "active" : "idle";
    if (stepName === "models") return payload.markets ? "done" : payload.step === "after" ? "active" : "idle";
    return "idle";
  }

  function dailyMetrics(payload) {
    const props = payload?.props?.propCount ?? payload?.grade?.propsRead ?? "--";
    const games = payload?.template?.games ?? payload?.health?.mlbGames ?? "--";
    const graded = payload?.grade?.rowsGraded ?? "--";
    let readyMarkets = "--";
    if (Array.isArray(payload?.markets)) {
      readyMarkets = payload.markets.filter((row) => row.canTrain).length;
    }

    return [
      ["Props", props, "Pulled or graded"],
      ["Games", games, "Slate coverage"],
      ["Graded", graded, "After-game rows"],
      ["Ready ML", readyMarkets, "Trainable markets"],
    ];
  }

  function renderDailyRunbook(payload = getDailyPayload()) {
    const output = $("#dailyWorkflowOutput");
    const body = $("#dailyWorkflowDate")?.closest(".model-refresh-body");
    if (!body || $("#stage2DailyRunbook")) return;

    const card = document.createElement("section");
    card.id = "stage2DailyRunbook";
    card.className = "stage2-daily-runbook";
    card.innerHTML = `
      <div class="stage2-runbook-hero">
        <div>
          <p class="eyebrow">Daily command center</p>
          <h2>Make today's board trustworthy before you bet.</h2>
          <p>Run the slate setup first, review any missing odds, grade after games finish, then check which ML markets are ready.</p>
        </div>
        <div class="stage2-runbook-date">
          <span>Workflow date</span>
          <strong data-stage2-daily-date>${escapeHtml($("#dailyWorkflowDate")?.value || todayDateString())}</strong>
        </div>
      </div>
      <div class="stage2-runbook-steps" data-stage2-daily-steps></div>
      <div class="stage2-runbook-metrics" data-stage2-daily-metrics></div>
      <div class="stage2-runbook-actions">
        <button type="button" data-stage2-click="dailyBeforeButton" class="stage2-primary-action">Before Game Setup</button>
        <button type="button" data-stage2-click="dailyAfterButton" class="stage2-secondary-action">After Game Update</button>
        <button type="button" data-stage2-click="dailyStatusButton" class="stage2-ghost-action">Check ML Status</button>
      </div>
    `;

    body.insertBefore(card, output || body.firstChild);
    card.addEventListener("click", (event) => {
      const proxy = event.target.closest("[data-stage2-click]");
      if (!proxy) return;
      const target = document.getElementById(proxy.dataset.stage2Click);
      target?.click();
    });

    $("#dailyWorkflowDate")?.addEventListener("change", () => updateDailyRunbook(getDailyPayload()));
    updateDailyRunbook(payload);
  }

  function updateDailyRunbook(payload) {
    const card = $("#stage2DailyRunbook");
    if (!card) return;

    const date = $("#dailyWorkflowDate")?.value || payload?.date || todayDateString();
    const dateEl = $("[data-stage2-daily-date]", card);
    if (dateEl) dateEl.textContent = date;

    const stepData = [
      ["before", "1", "Before Game Setup", "Pull props, build features, create templates, and save current odds."],
      ["review", "2", "Review Odds", "Only review manually when auto-fill reports missing rows or unsupported markets."],
      ["after", "3", "After Game Update", "Grade props, merge outcomes, and train markets that have enough rows."],
      ["models", "4", "Check ML Status", "Confirm which markets are ready before using predictions."],
    ];

    const stepsEl = $("[data-stage2-daily-steps]", card);
    if (stepsEl) {
      stepsEl.innerHTML = stepData.map(([key, number, title, detail]) => {
        const state = dailyStepState(payload, key);
        return `
          <article class="stage2-runbook-step ${stepClass(state)}">
            <span class="stage2-step-icon">${stepIcon(state)}</span>
            <div>
              <strong>${escapeHtml(number)}. ${escapeHtml(title)}</strong>
              <p>${escapeHtml(detail)}</p>
            </div>
          </article>
        `;
      }).join("");
    }

    const metricsEl = $("[data-stage2-daily-metrics]", card);
    if (metricsEl) {
      metricsEl.innerHTML = dailyMetrics(payload).map(([label, value, sub]) => `
        <div>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          <small>${escapeHtml(sub)}</small>
        </div>
      `).join("");
    }
  }

  function updateDailyFromPayload(payload) {
    saveDailyPayload(payload);
    renderDailyRunbook(payload);
    updateDailyRunbook(payload);
  }

  function enhanceOnboarding() {
    const card = $("#firstRunOnboarding");
    if (!card || card.dataset.stage2Enhanced) return;
    card.dataset.stage2Enhanced = "true";

    if (storageGet(STORAGE_KEYS.onboardingDismissed) === "1") {
      card.hidden = true;
      return;
    }

    const actions = document.createElement("div");
    actions.className = "stage2-onboarding-actions";
    actions.innerHTML = `
      <button type="button" data-stage2-go-runbook>Start with Daily Runbook</button>
      <button type="button" data-stage2-dismiss-onboarding>Hide guide</button>
    `;
    card.appendChild(actions);

    actions.addEventListener("click", (event) => {
      if (event.target.closest("[data-stage2-dismiss-onboarding]")) {
        storageSet(STORAGE_KEYS.onboardingDismissed, "1");
        card.hidden = true;
      }
      if (event.target.closest("[data-stage2-go-runbook]")) {
        window.location.hash = "today-board";
        document.getElementById("stage2DailyRunbook")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  function skeletonRows(count = 5) {
    return Array.from({ length: count }, () => `
      <div class="stage2-skeleton-row">
        <span></span><span></span><span></span><span></span>
      </div>
    `).join("");
  }

  function enhancePlayerboardEmptyState() {
    const results = $("#topPlayerboardResults");
    const button = $("#topPlayerboardLoad");
    if (!results || results.dataset.stage2Enhanced) return;
    results.dataset.stage2Enhanced = "true";

    if (!results.textContent.trim()) {
      results.innerHTML = `
        <div class="stage2-empty-state">
          <strong>No board loaded yet.</strong>
          <p>Run Before Game Setup, then load the board to rank today's props by edge and confidence.</p>
        </div>
      `;
    }

    button?.addEventListener("click", () => {
      results.innerHTML = `<div class="stage2-skeleton-list" aria-label="Loading board">${skeletonRows(6)}</div>`;
    });
  }

  function summarizeProfit(summary = {}) {
    const profit = asNumber(summary.profitUnits);
    const roi = asNumber(summary.roiPercent);
    if (!summary.picks) return "No tracked picks yet. Save picks from Run a Pick to start building ROI history.";
    if (profit > 0) return `Positive tracking: +${profit.toFixed(2)} units with ${roi.toFixed(1)}% ROI.`;
    if (profit < 0) return `Negative tracking: ${profit.toFixed(2)} units with ${roi.toFixed(1)}% ROI. Check market/confidence breakdowns before scaling.`;
    return `Flat tracking: ${profit.toFixed(2)} units with ${roi.toFixed(1)}% ROI.`;
  }

  function renderMyPicksHeader(payload = null) {
    const cards = $("#predictionDashboardCards");
    const panel = $("#predictionDashboardLoadButton")?.closest("details");
    if (!cards || !panel) return;

    let header = $("#stage2MyPicksHero", panel);
    if (!header) {
      header = document.createElement("section");
      header.id = "stage2MyPicksHero";
      header.className = "stage2-my-picks-hero";
      cards.insertAdjacentElement("beforebegin", header);
    }

    const summary = payload?.summary || {};
    const picks = summary.picks ?? "--";
    const record = `${summary.wins ?? 0}-${summary.losses ?? 0}-${summary.pushes ?? 0}`;
    const winRate = `${summary.winRate ?? 0}%`;
    const profit = `${summary.profitUnits ?? 0}u`;

    header.innerHTML = `
      <div>
        <p class="eyebrow">Bet tracker</p>
        <h2>Know whether the model is making money, not just making picks.</h2>
        <p>${escapeHtml(summarizeProfit(summary))}</p>
      </div>
      <div class="stage2-my-picks-strip">
        <div><span>Picks</span><strong>${escapeHtml(picks)}</strong></div>
        <div><span>Record</span><strong>${escapeHtml(record)}</strong></div>
        <div><span>Win Rate</span><strong>${escapeHtml(winRate)}</strong></div>
        <div><span>Profit</span><strong>${escapeHtml(profit)}</strong></div>
      </div>
    `;
  }

  function observeDashboard() {
    const output = $("#predictionDashboardOutput");
    if (!output || output.dataset.stage2Observed) return;
    output.dataset.stage2Observed = "true";

    renderMyPicksHeader();

    const observer = new MutationObserver(() => {
      const text = output.textContent || "";
      if (!text.trim() || text.includes("Dashboard failed")) return;
      try {
        renderMyPicksHeader(JSON.parse(text));
      } catch {
        // Ignore non-JSON intermediate states.
      }
    });
    observer.observe(output, { childList: true, characterData: true, subtree: true });
  }

  function compactRawJsonLabels() {
    $$("pre.json-output").forEach((pre) => {
      if (pre.dataset.stage2RawEnhanced) return;
      pre.dataset.stage2RawEnhanced = "true";
      pre.setAttribute("aria-label", "Raw data output. Product cards above this block are the primary view.");
      const label = document.createElement("div");
      label.className = "stage2-raw-label";
      label.textContent = "Raw data — for debugging only";
      pre.insertAdjacentElement("beforebegin", label);
    });
  }

  function init() {
    renderDailyRunbook();
    enhanceOnboarding();
    enhancePlayerboardEmptyState();
    observeDashboard();
    compactRawJsonLabels();

    document.addEventListener("baseball:daily-workflow", (event) => updateDailyFromPayload(event.detail));

    // app-pages.js creates the onboarding card late in the load order, so run one extra pass.
    window.setTimeout(() => {
      renderDailyRunbook();
      enhanceOnboarding();
      enhancePlayerboardEmptyState();
      observeDashboard();
      compactRawJsonLabels();
    }, 0);
  }

  window.Stage2ProductUI = {
    updateDailyRunbook: updateDailyFromPayload,
    renderMyPicksHeader,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
