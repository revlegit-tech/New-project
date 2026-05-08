(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  async function getJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    const text = await response.text();
    let payload = {};
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`Endpoint returned non-JSON. Status ${response.status}. First text: ${text.slice(0, 120)}`);
    }
    if (!response.ok) throw new Error(payload.error || `Request failed ${response.status}`);
    return payload;
  }

  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function statusClass(status) {
    return String(status || "Missing").toLowerCase().replace(/[^a-z0-9]+/g, "-");
  }

  function cardMarkup(card) {
    const warnings = card.warnings || [];
    return `
      <article class="data-confidence-card ${statusClass(card.status)}">
        <div class="data-confidence-card-top">
          <span class="data-confidence-dot" aria-hidden="true"></span>
          <span class="data-confidence-status">${esc(card.status || "Missing")}</span>
        </div>
        <h4>${esc(card.label)}</h4>
        <div class="data-confidence-metric">${esc(card.metric ?? "--")}</div>
        <p>${esc(card.summary || "--")}</p>
        <small>${esc(card.detail || "")}</small>
        ${card.timestamp ? `<div class="data-confidence-timestamp">Updated ${esc(card.timestamp)}</div>` : ""}
        ${warnings.length ? `<ul class="data-confidence-warnings">${warnings.slice(0, 2).map((warning) => `<li>${esc(warning)}</li>`).join("")}</ul>` : ""}
        ${card.repairTarget ? `<button type="button" class="data-confidence-advanced-link" data-repair-target="${esc(card.repairTarget)}">Advanced repair</button>` : ""}
      </article>
    `;
  }

  function phaseMarkup(phase) {
    const checks = phase.checks || [];
    const progress = phase.progress || {};
    return `
      <article class="workflow-phase-card ${statusClass(phase.status)}">
        <div class="workflow-phase-header">
          <div>
            <span class="workflow-phase-status">${esc(phase.status || "Missing")}</span>
            <h4>${esc(phase.label)}</h4>
          </div>
          <strong>${esc(progress.passed ?? 0)}/${esc(progress.total ?? checks.length)}</strong>
        </div>
        <div class="workflow-phase-checks">
          ${checks.map((check) => `<span class="workflow-check ${check.ok ? "ok" : "missing"}">${check.ok ? "✓" : "•"} ${esc(check.label)}</span>`).join("")}
        </div>
        <div class="workflow-phase-meta">Last run: ${esc(phase.lastRunDate || "not recorded")}</div>
      </article>
    `;
  }

  function renderDashboard(payload) {
    const cards = payload.cards || [];
    const phases = payload.workflowPhases || [];
    const warnings = payload.warnings || [];
    const summary = payload.summary || {};
    return `
      <section class="data-confidence-shell" aria-labelledby="dataConfidenceTitle">
        <div class="data-confidence-hero">
          <div>
            <div class="data-confidence-eyebrow">Product-grade data health</div>
            <h3 id="dataConfidenceTitle">Data Confidence Dashboard</h3>
            <p>Read-only status for today’s board. Repair and pipeline controls stay behind Advanced Mode.</p>
          </div>
          <div class="data-confidence-score ${statusClass(payload.overallStatus)}">
            <span>Data confidence</span>
            <strong>${esc(payload.dataConfidence || payload.overallStatus || "Partial")}</strong>
            <small>${esc(payload.productState?.label || "Research Mode")}</small>
          </div>
        </div>

        <div class="data-confidence-kpis">
          <div><span>Board date</span><strong>${esc(payload.latestBoardDate || "--")}</strong></div>
          <div><span>Fully graded slate</span><strong>${esc(payload.latestFullyGradedDate || "Not yet")}</strong></div>
          <div><span>Warnings</span><strong>${esc(summary.warnings ?? warnings.length)}</strong></div>
          <div><span>Generated</span><strong>${esc((payload.generatedAt || "").slice(0, 19).replace("T", " ") || "--")}</strong></div>
        </div>

        <div class="data-confidence-grid">
          ${cards.map(cardMarkup).join("")}
        </div>

        <div class="workflow-state-shell">
          <div class="workflow-state-header">
            <div>
              <div class="data-confidence-eyebrow">Daily workflow state machine</div>
              <h3>Morning → Pre-lock → Postgame → Weekly</h3>
              <p>Each phase exposes timestamped completion checks without showing raw admin controls.</p>
            </div>
          </div>
          <div class="workflow-phase-grid">
            ${phases.map(phaseMarkup).join("")}
          </div>
        </div>

        ${warnings.length ? `
          <details class="data-confidence-warning-panel">
            <summary>${warnings.length} health warning(s)</summary>
            <ul>${warnings.map((warning) => `<li>${esc(warning)}</li>`).join("")}</ul>
          </details>
        ` : ""}
      </section>
    `;
  }

  function ensureDashboardHost() {
    let host = $("#productDataHealthDashboard");
    if (host) return host;

    const output = $("#dataHealthOutput");
    const anchor = output?.closest(".muse-card") || output?.parentElement || $("#app-page-tools-data") || document.body;
    host = document.createElement("div");
    host.id = "productDataHealthDashboard";
    host.className = "product-data-health-dashboard";
    anchor.insertAdjacentElement("beforebegin", host);
    return host;
  }

  function markRawHealthAsAdvanced() {
    const rawSelectors = [
      "#dataHealthOutput",
      "#playerboardHealthPanel",
      "#gradingHealthPanel",
      "#workflowSummariesPanel",
      "#systemOverviewPanel",
    ];
    rawSelectors.forEach((selector) => {
      const node = $(selector);
      if (node) node.dataset.advancedMode = "1";
    });

    const rawCard = $("#dataHealthOutput")?.closest(".muse-card");
    if (rawCard) rawCard.dataset.advancedMode = "1";
  }

  async function loadDashboard() {
    const host = ensureDashboardHost();
    const date = $("#dataHealthDate")?.value || $("#edgeBoardDate")?.value || today();
    host.innerHTML = `
      <section class="data-confidence-shell loading">
        <div class="data-confidence-hero">
          <div>
            <div class="data-confidence-eyebrow">Product-grade data health</div>
            <h3>Loading Data Confidence Dashboard…</h3>
            <p>Checking odds, playerboard, grading, workflows, and model-artifact readiness.</p>
          </div>
        </div>
      </section>
    `;
    try {
      const payload = await getJson(`/api/data-health/dashboard?season=2026&date=${encodeURIComponent(date)}`);
      host.innerHTML = renderDashboard(payload);
      bindAdvancedRepairLinks(host);
    } catch (error) {
      console.error(error);
      host.innerHTML = `
        <section class="data-confidence-shell failed">
          <div class="data-confidence-hero">
            <div>
              <div class="data-confidence-eyebrow">Product-grade data health</div>
              <h3>Dashboard unavailable</h3>
              <p>${esc(error.message)}</p>
            </div>
          </div>
        </section>
      `;
    }
  }

  function bindAdvancedRepairLinks(root) {
    $$("[data-repair-target]", root).forEach((button) => {
      button.addEventListener("click", () => {
        localStorage.setItem("mlbAdvancedModeEnabled", "1");
        document.body.classList.add("advanced-mode-enabled");
        $$('[data-advanced-mode]').forEach((node) => { node.hidden = false; });
        const target = button.dataset.repairTarget || "";
        const possible = {
          "pipeline": "pipelinePullPropsButton",
          "daily-workflow": "dailyBeforeButton",
          "weather-sync": "weatherSyncButton",
          "savant-sync": "savantSyncButton",
          "grading-repair": "gradingHealthButton",
          "workflow-summaries": "workflowSummariesButton",
          "model-room": "modelCardsGrid",
        }[target];
        const node = possible ? document.getElementById(possible) : null;
        if (node) node.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });
  }

  function init() {
    ensureDashboardHost();
    markRawHealthAsAdvanced();
    loadDashboard();
    $("#dataHealthButton")?.addEventListener("click", () => setTimeout(loadDashboard, 120));
    $("#dataHealthDate")?.addEventListener("change", loadDashboard);
    document.addEventListener("mlb:app-page-shown", (event) => {
      if (event.detail?.pageId === "tools-data") loadDashboard();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
