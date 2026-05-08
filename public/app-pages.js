(() => {
  document.documentElement.classList.add("app-pages-booting");

  const PAGES = [
    ["today-board", "Today"],
    ["games", "Games"],
    ["run-pick", "Props"],
    ["my-picks", "My Picks"],
    ["model-room", "Model Room"],
    ["tools-data", "Data Health"],
  ];

  const ADVANCED_STORAGE_KEY = "mlbAdvancedModeEnabled";
  const $ = (selector, root = document) => root.querySelector(selector);
  const all = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const byId = (id) => document.getElementById(id);

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function closestDetailsById(id) {
    const element = byId(id);
    return element ? element.closest("details") : null;
  }

  function detailsBySummaryText(text) {
    const needle = text.toLowerCase();
    return all("details").find((details) => {
      const summary = $("summary", details);
      return summary && summary.textContent.toLowerCase().includes(needle);
    });
  }

  function detailsByContainedSelector(selector) {
    const element = $(selector);
    return element ? element.closest("details") : null;
  }

  function page(id) {
    return byId(`appPage-${id}`);
  }

  function createShell() {
    if (byId("appPageShell")) return byId("appPageShell");

    const main = $("main") || document.body;
    const header = document.createElement("header");
    header.id = "edgeBoardHeader";
    header.className = "edge-board-header";
    header.innerHTML = `
      <div class="edge-board-title-block">
        <p class="eyebrow">Bloomberg Terminal for Bettors</p>
        <h1>Today’s Edge Board</h1>
        <p>Research-first MLB betting intelligence with model readiness, grading, and data confidence visible before every decision.</p>
      </div>
      <div class="edge-board-controls" aria-label="Slate controls">
        <label>
          Slate date
          <input id="edgeBoardDate" type="date" />
        </label>
        <div class="edge-board-status-pill" id="edgeBoardSlateStatus">Loading slate status…</div>
        <button id="advancedModeToggle" type="button" class="edge-board-advanced-toggle" aria-pressed="false">Advanced Mode</button>
      </div>
      <div class="edge-board-kpis" id="edgeBoardKpis" aria-live="polite">
        <div><span>Board date</span><strong>--</strong></div>
        <div><span>Latest odds</span><strong>--</strong></div>
        <div><span>Fully graded</span><strong>--</strong></div>
        <div><span>Data confidence</span><strong>--</strong></div>
      </div>
    `;

    const nav = document.createElement("nav");
    nav.id = "appPageNav";
    nav.className = "app-page-nav";
    nav.setAttribute("aria-label", "Main app sections");

    const shell = document.createElement("div");
    shell.id = "appPageShell";
    shell.className = "app-page-shell";

    PAGES.forEach(([id, label]) => {
      const link = document.createElement("a");
      link.href = `#${id}`;
      link.dataset.appPageLink = id;
      link.textContent = label;
      nav.appendChild(link);

      const pageSection = document.createElement("section");
      pageSection.id = `appPage-${id}`;
      pageSection.className = `app-page app-page-${id}`;
      pageSection.dataset.appPage = id;
      pageSection.hidden = true;
      shell.appendChild(pageSection);
    });

    main.prepend(header, nav, shell);
    byId("workflowJumpNav")?.remove();
    document.body.classList.add("app-pages-enabled", "edge-board-stage");
    return shell;
  }

  function createGroup(title, subtitle = "", options = {}) {
    const section = document.createElement("section");
    section.className = `app-page-section ${options.className || ""}`.trim();
    if (options.id) section.id = options.id;
    if (options.advanced) section.dataset.advancedMode = "1";

    const header = document.createElement("div");
    header.className = "app-page-section-header";
    header.innerHTML = `
      <p class="eyebrow">${escapeHtml(options.eyebrow || title.split(" ")[0])}</p>
      <h2>${escapeHtml(title)}</h2>
      ${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ""}
    `;

    const body = document.createElement("div");
    body.className = "app-page-section-body";
    section.append(header, body);
    return section;
  }

  function addGroup(pageId, title, subtitle, nodes, options = {}) {
    const target = page(pageId);
    if (!target) return null;

    const filtered = nodes.filter(Boolean);
    if (!filtered.length && !options.allowEmpty) return null;

    const group = createGroup(title, subtitle, options);
    const body = $(".app-page-section-body", group);
    filtered.forEach((node) => body.appendChild(node));
    target.appendChild(group);
    return group;
  }

  function setSummary(details, label) {
    if (!details) return;
    const summary = details.querySelector("summary");
    if (summary) summary.textContent = label;
  }

  function emptyState(title, body, cta = "") {
    const section = document.createElement("section");
    section.className = "edge-board-empty-state";
    section.innerHTML = `
      <div>
        <p class="eyebrow">Coming next</p>
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(body)}</p>
        ${cta ? `<strong>${escapeHtml(cta)}</strong>` : ""}
      </div>
    `;
    return section;
  }

  function createAdvancedPanel() {
    const panel = document.createElement("section");
    panel.id = "advancedModePanel";
    panel.className = "advanced-mode-panel";
    panel.dataset.advancedMode = "1";
    panel.hidden = true;
    panel.innerHTML = `
      <div class="advanced-mode-intro">
        <p class="eyebrow">Advanced Mode</p>
        <h2>Developer, repair, training, and source-management tools</h2>
        <p>These controls can mutate data, run workflows, or expose raw diagnostics. They stay hidden from the normal bettor workflow.</p>
      </div>
      <div class="advanced-mode-grid"></div>
    `;
    return panel;
  }

  function appendAdvanced(nodes) {
    const panel = byId("advancedModePanel") || createAdvancedPanel();
    const grid = $(".advanced-mode-grid", panel) || panel;
    nodes.filter(Boolean).forEach((node) => {
      node.dataset.advancedMode = "1";
      grid.appendChild(node);
    });
    if (!panel.isConnected) page("tools-data")?.appendChild(panel);
  }

  function closeDetailsExceptPrimary() {
    all("details.model-refresh-panel, details.data-manager").forEach((details) => {
      const text = details.querySelector("summary")?.textContent?.toLowerCase() || "";
      details.open = text.includes("unified") || text.includes("data health") || text.includes("model room");
    });
  }

  function movePanels() {
    const simpleApp = byId("simplePropApp");
    if (simpleApp) page("today-board")?.appendChild(simpleApp);

    setSummary(closestDetailsById("unifiedPredictButton"), "Unified Prop Card");
    setSummary(closestDetailsById("allDataPredictButton"), "All Data Prop Predictor");
    setSummary(closestDetailsById("propMlPredictButton"), "Player Prop ML");
    setSummary(closestDetailsById("moneylinePredictButton"), "Moneyline ML");
    setSummary(closestDetailsById("predictionDashboardLoadButton"), "P&L / Performance Dashboard");
    setSummary(closestDetailsById("predictionSaveButton"), "Prediction History & Grading");
    setSummary(closestDetailsById("dataHealthButton"), "Data Health Summary");
    setSummary(detailsByContainedSelector("#modelCardsGrid"), "Model Room: Market Readiness");
    setSummary(closestDetailsById("dailyBeforeButton"), "Daily ML Runbook");
    setSummary(closestDetailsById("modelRefreshButton"), "Refresh Model Data");
    setSummary(closestDetailsById("pipelinePullPropsButton"), "Manual Pipeline Tools");

    addGroup("run-pick", "Props", "Run a focused prop analysis after the board identifies a watchlist row. Raw details stay available below each premium card.", [
      closestDetailsById("unifiedPredictButton"),
      closestDetailsById("allDataPredictButton"),
      closestDetailsById("propMlPredictButton"),
      closestDetailsById("moneylinePredictButton"),
    ], { eyebrow: "Research" });

    addGroup("my-picks", "My Picks", "Track saved picks, grading, bankroll impact, and model-vs-user performance separately.", [
      closestDetailsById("predictionDashboardLoadButton"),
      closestDetailsById("predictionSaveButton"),
    ], { eyebrow: "Tracking" });

    const modelRoom = addGroup("model-room", "Model Room", "Market readiness, training sample size, grading state, calibration, and backtest context for every model-backed surface.", [
      detailsByContainedSelector("#modelCardsGrid"),
    ], { eyebrow: "Governance" });
    if (!modelRoom) page("model-room")?.appendChild(emptyState("Model cards are loading", "The model room appears here once /api/model-cards responds."));

    addGroup("tools-data", "Data Health", "Read-only health summaries stay visible in normal mode. Mutating repair and pipeline actions require Advanced Mode.", [
      closestDetailsById("dataHealthButton"),
    ], { eyebrow: "Health" });

    page("games")?.appendChild(emptyState(
      "Games board shell",
      "The next slice will group today’s props by matchup, show game totals, weather, probable pitchers, and correlated exposure.",
      "Today’s Edge Board remains the primary workflow for this stage."
    ));

    appendAdvanced([
      closestDetailsById("dailyBeforeButton"),
      detailsBySummaryText("data manager"),
      closestDetailsById("modelRefreshButton"),
      closestDetailsById("incrementalStatsCatchupButton") || closestDetailsById("incrementalStatsStatusButton"),
      closestDetailsById("weatherSyncButton"),
      closestDetailsById("savantSyncButton"),
      closestDetailsById("oddsMovementSyncButton"),
      closestDetailsById("pipelinePullPropsButton"),
      closestDetailsById("dataHubSyncButton"),
      closestDetailsById("externalSyncButton"),
      closestDetailsById("autoBeforeButton"),
      $(".mlb-panel"),
      $(".espn-panel"),
      $(".github-panel"),
      $(".needs-panel"),
    ]);

    const workspace = $(".workspace");
    if (workspace) workspace.hidden = true;
    closeDetailsExceptPrimary();
  }

  function requestedPage() {
    const hash = window.location.hash.replace(/^#/, "");
    if (hash === "props") return "run-pick";
    if (hash === "data-health") return "tools-data";
    if (hash === "today") return "today-board";
    return PAGES.some(([id]) => id === hash) ? hash : "today-board";
  }

  function showPage(pageId) {
    PAGES.forEach(([id]) => {
      const target = page(id);
      const link = $(`[data-app-page-link="${id}"]`);
      const active = id === pageId;

      if (target) {
        target.hidden = !active;
        target.classList.toggle("active", active);
      }

      if (link) {
        link.classList.toggle("active", active);
        if (active) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      }
    });

    document.body.dataset.appPage = pageId;
    document.dispatchEvent(new CustomEvent("mlb:app-page-shown", { detail: { pageId } }));
  }

  function advancedEnabled() {
    return localStorage.getItem(ADVANCED_STORAGE_KEY) === "1";
  }

  function setAdvancedMode(enabled) {
    localStorage.setItem(ADVANCED_STORAGE_KEY, enabled ? "1" : "0");
    document.body.classList.toggle("advanced-mode-enabled", enabled);
    all("[data-advanced-mode]").forEach((node) => {
      node.hidden = !enabled;
    });
    const button = byId("advancedModeToggle");
    if (button) {
      button.setAttribute("aria-pressed", enabled ? "true" : "false");
      button.textContent = enabled ? "Advanced Mode On" : "Advanced Mode";
    }
  }

  async function loadHeaderStatus() {
    const dateInput = byId("edgeBoardDate");
    if (dateInput && !dateInput.value) dateInput.value = byId("simpleDate")?.value || today();

    try {
      const response = await fetch("/api/app/status?season=2026", { cache: "no-store" });
      if (!response.ok) throw new Error(`Status ${response.status}`);
      const payload = await response.json();
      const playerboard = payload.playerboard || {};
      const grading = payload.grading || {};
      const product = payload.productStateDetail || {};
      const kpis = byId("edgeBoardKpis");
      if (kpis) {
        const items = kpis.querySelectorAll("strong");
        if (items[0]) items[0].textContent = playerboard.date || playerboard.latestAvailableDate || "--";
        if (items[1]) items[1].textContent = playerboard.latestSnapshotAt || payload.latestOddsTimestamp || "--";
        if (items[2]) items[2].textContent = payload.latestFullyGradedDate || "Not yet";
        if (items[3]) items[3].textContent = payload.dataConfidence || playerboard.dataConfidence || "Partial";
      }
      const slate = byId("edgeBoardSlateStatus");
      if (slate) slate.textContent = `${product.label || "Research Mode"} · ${grading.state || "grading unknown"}`;
    } catch (error) {
      const slate = byId("edgeBoardSlateStatus");
      if (slate) slate.textContent = "Status unavailable · Research Mode";
      console.error(error);
    }
  }

  function bindHeader() {
    byId("advancedModeToggle")?.addEventListener("click", () => setAdvancedMode(!advancedEnabled()));
    byId("edgeBoardDate")?.addEventListener("change", (event) => {
      const value = event.target.value;
      const simpleDate = byId("simpleDate");
      if (simpleDate && value) {
        simpleDate.value = value;
        simpleDate.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  }

  function init() {
    createShell();
    movePanels();
    bindHeader();
    setAdvancedMode(advancedEnabled());
    showPage(requestedPage());
    loadHeaderStatus();
    window.addEventListener("hashchange", () => showPage(requestedPage()));
    document.documentElement.classList.remove("app-pages-booting");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
