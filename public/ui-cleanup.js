
function bpSafeInsertBefore(parent, newNode, referenceNode) {
  if (!parent || !newNode) return;
  if (referenceNode && referenceNode.parentNode === parent) {
    parent.insertBefore(newNode, referenceNode);
  } else {
    parent.appendChild(newNode);
  }
}

(() => {
  function qs(selector, root = document) {
    return root.querySelector(selector);
  }

  function qsa(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function closestDetailsById(id) {
    const el = document.getElementById(id);
    return el ? el.closest("details") : null;
  }

  function setSummary(details, label, badge = "") {
    if (!details) return;
    const summary = details.querySelector("summary");
    if (!summary) return;

    summary.innerHTML = `
      <span class="workflow-summary-title">${label}</span>
      ${badge ? `<span class="workflow-summary-badge">${badge}</span>` : ""}
    `;
  }

  function createSection(title, description, className = "") {
    const section = document.createElement("section");
    section.className = `workflow-section ${className}`.trim();
    section.innerHTML = `
      <div class="workflow-section-header">
        <div>
          <h2>${title}</h2>
          <p>${description}</p>
        </div>
      </div>
      <div class="workflow-section-body"></div>
    `;
    return section;
  }

  function moveIfExists(section, node) {
    if (!section || !node) return;
    const body = section.querySelector(".workflow-section-body");
    if (body && !body.contains(node)) body.appendChild(node);
  }

  function collapseAdvanced(details) {
    if (!details) return;
    details.open = false;
    details.classList.add("advanced-panel");
  }

  function promotePrimary(details) {
    if (!details) return;
    details.open = true;
    details.classList.add("primary-panel");
  }

  function wrapMainPanels() {
    const main =
      qs("main") ||
      qs(".app-main") ||
      qs(".container") ||
      qs(".main-content") ||
      document.body;

    if (document.getElementById("workflowDashboard")) return;

    const dashboard = createSection(
      "Dashboard",
      "Review performance, grade predictions, and monitor the health of the system.",
      "workflow-dashboard"
    );
    dashboard.id = "workflowDashboard";

    const predictor = createSection(
      "Build a Pick",
      "Load matchups, choose props, run the Unified Prop Card, and save predictions.",
      "workflow-predictor"
    );
    predictor.id = "workflowPredictor";

    const data = createSection(
      "Daily Data",
      "Sync stats, weather, odds movement, and Baseball Savant quality metrics.",
      "workflow-data"
    );
    data.id = "workflowData";

    const advanced = createSection(
      "Advanced / Admin",
      "Manual refresh tools, diagnostics, raw outputs, and older utilities.",
      "workflow-advanced"
    );
    advanced.id = "workflowAdvanced";

    const anchor =
      qs(".results") ||
      qs("#results") ||
      qsa("details")[0] ||
      main.firstElementChild;

    bpSafeInsertBefore(main, dashboard, anchor || null);
    bpSafeInsertBefore(main, predictor, dashboard.nextSibling);
    bpSafeInsertBefore(main, data, predictor.nextSibling);
    bpSafeInsertBefore(main, advanced, data.nextSibling);

    const predictionDashboard = closestDetailsById("predictionDashboardLoadButton");
    const predictionHistory = closestDetailsById("predictionSaveButton");
    const unifiedProp = closestDetailsById("unifiedPropCardButton") || closestDetailsById("allDataPredictButton");
    const matchupProps = closestDetailsById("matchupLoadPropsButton") || closestDetailsById("loadSavedPropsButton");
    const dataHealth = closestDetailsById("dataHealthButton");
    const savant = closestDetailsById("savantSyncButton");
    const oddsMovement = closestDetailsById("oddsMovementSyncButton");
    const weather = closestDetailsById("weatherSyncButton");
    const incremental = closestDetailsById("incrementalStatsCatchupButton") || closestDetailsById("incrementalStatsStatusButton");

    setSummary(predictionDashboard, "Performance Dashboard", "Start here");
    setSummary(predictionHistory, "Save & Grade Predictions", "Feedback loop");
    setSummary(unifiedProp, "Unified Prop Card", "Main predictor");
    setSummary(matchupProps, "Matchup Props", "Pick selector");
    setSummary(dataHealth, "Data Health", "System check");
    setSummary(savant, "Baseball Savant Metrics", "Quality");
    setSummary(oddsMovement, "Odds Movement Snapshots", "Market");
    setSummary(weather, "Weather Features", "Game context");
    setSummary(incremental, "Stats Warehouse", "2026 logs");

    promotePrimary(predictionDashboard);
    promotePrimary(unifiedProp);

    moveIfExists(dashboard, predictionDashboard);
    moveIfExists(dashboard, predictionHistory);
    moveIfExists(dashboard, dataHealth);

    moveIfExists(predictor, matchupProps);
    moveIfExists(predictor, unifiedProp);

    moveIfExists(data, incremental);
    moveIfExists(data, weather);
    moveIfExists(data, savant);
    moveIfExists(data, oddsMovement);

    const known = new Set([
      predictionDashboard,
      predictionHistory,
      unifiedProp,
      matchupProps,
      dataHealth,
      incremental,
      weather,
      savant,
      oddsMovement,
    ].filter(Boolean));

    qsa("details.model-refresh-panel, details").forEach((details) => {
      if (known.has(details)) return;
      if (details.closest(".workflow-section")) return;
      collapseAdvanced(details);
      moveIfExists(advanced, details);
    });
  }

  function simplifyOutputs() {
    qsa("pre.json-output").forEach((pre) => {
      const wrapper = pre.closest(".json-output-wrap");
      if (wrapper) return;

      const container = document.createElement("div");
      container.className = "json-output-wrap";

      const toolbar = document.createElement("div");
      toolbar.className = "json-output-toolbar";
      toolbar.innerHTML = `
        <span>Details / raw output</span>
        <button type="button" class="mini-toggle-output">Show / hide</button>
      `;

      bpSafeInsertBefore(pre.parentNode, container, pre);
      container.appendChild(toolbar);
      container.appendChild(pre);

      pre.classList.add("is-compact");

      toolbar.querySelector("button")?.addEventListener("click", () => {
        pre.classList.toggle("is-compact");
      });
    });
  }

  function improveForms() {
    qsa("label").forEach((label) => {
      const input = label.querySelector("input, select, textarea");
      if (input) label.classList.add("clean-field");
    });

    qsa("button").forEach((button) => {
      if (!button.classList.length) button.classList.add("clean-button");
    });

    qsa(".source-actions").forEach((actions) => {
      actions.classList.add("clean-actions");
    });
  }

  function addJumpNav() {
    if (document.getElementById("workflowJumpNav")) return;

    const nav = document.createElement("nav");
    nav.id = "workflowJumpNav";
    nav.className = "workflow-jump-nav";
    nav.innerHTML = `
      <a href="#workflowDashboard">Dashboard</a>
      <a href="#workflowPredictor">Build a Pick</a>
      <a href="#workflowData">Daily Data</a>
      <a href="#workflowAdvanced">Advanced</a>
    `;

    const main =
      qs("main") ||
      qs(".app-main") ||
      qs(".container") ||
      qs(".main-content") ||
      document.body;

    bpSafeInsertBefore(main, nav, main.firstChild);
  }

  function improveLeftRail() {
    const candidates = [
      qs(".sidebar"),
      qs(".left-panel"),
      qs(".left-sidebar"),
      qs("aside"),
      qs("#leftPanel"),
      qs("#startHere"),
    ].filter(Boolean);

    candidates.forEach((node) => {
      node.classList.add("clean-left-rail");
    });

    qsa("summary").forEach((summary) => {
      summary.title = summary.textContent.trim();
    });
  }

  function init() {
    document.body.classList.add("clean-ui-v2");

    addJumpNav();
    wrapMainPanels();
    simplifyOutputs();
    improveForms();
    improveLeftRail();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
