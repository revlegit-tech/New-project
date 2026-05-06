(() => {
  document.documentElement.classList.add("app-pages-booting");

  const PAGES = [
    ["today-board", "Today's Board"],
    ["run-pick", "Run a Pick"],
    ["my-picks", "My Picks"],
    ["tools-data", "Tools & Data"],
  ];

  const $ = (selector, root = document) => root.querySelector(selector);
  const all = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const byId = (id) => document.getElementById(id);

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

  function createShell() {
    if (byId("appPageShell")) return byId("appPageShell");

    const main = $("main") || document.body;
    const shell = document.createElement("div");
    shell.id = "appPageShell";
    shell.className = "app-page-shell";

    const nav = document.createElement("nav");
    nav.id = "appPageNav";
    nav.className = "app-page-nav";
    nav.setAttribute("aria-label", "Main app sections");

    PAGES.forEach(([id, label]) => {
      const link = document.createElement("a");
      link.href = `#${id}`;
      link.dataset.appPageLink = id;
      link.textContent = label;
      nav.appendChild(link);

      const page = document.createElement("section");
      page.id = `appPage-${id}`;
      page.className = `app-page app-page-${id}`;
      page.dataset.appPage = id;
      page.hidden = true;
      shell.appendChild(page);
    });

    main.prepend(nav);
    nav.insertAdjacentElement("afterend", shell);
    byId("workflowJumpNav")?.remove();
    document.body.classList.add("app-pages-enabled");
    return shell;
  }

  function page(id) {
    return byId(`appPage-${id}`);
  }

  function createGroup(title, subtitle = "") {
    const section = document.createElement("section");
    section.className = "app-page-section";

    const header = document.createElement("div");
    header.className = "app-page-section-header";
    header.innerHTML = `
      <p class="eyebrow">${title.split(" ")[0]}</p>
      <h1>${title}</h1>
      ${subtitle ? `<p>${subtitle}</p>` : ""}
    `;

    const body = document.createElement("div");
    body.className = "app-page-section-body";
    section.append(header, body);
    return section;
  }

  function addGroup(pageId, title, subtitle, nodes) {
    const target = page(pageId);
    if (!target) return;

    const filtered = nodes.filter(Boolean);
    if (!filtered.length) return;

    const group = createGroup(title, subtitle);
    const body = $(".app-page-section-body", group);
    filtered.forEach((node) => body.appendChild(node));
    target.appendChild(group);
  }

  function setSummary(details, label) {
    if (!details) return;
    const summary = details.querySelector("summary");
    if (summary) summary.textContent = label;
  }

  function closeDetailsExceptPrimary() {
    all("details.model-refresh-panel, details.data-manager").forEach((details) => {
      const text = details.querySelector("summary")?.textContent?.toLowerCase() || "";
      details.open = text.includes("daily") || text.includes("unified") || text.includes("all data");
    });
  }

  function addOnboardingCard() {
    const target = page("today-board");
    if (!target || byId("firstRunOnboarding")) return;

    const card = document.createElement("section");
    card.id = "firstRunOnboarding";
    card.className = "onboarding-card";
    card.innerHTML = `
      <div>
        <p class="eyebrow">Start here</p>
        <h2>Get today's slate ready in three steps</h2>
        <p>Run setup, load the board, then choose a row to populate the active bet context.</p>
      </div>
      <ol>
        <li><strong>Before Game Setup</strong><span>Pull props, build features, and check data health.</span></li>
        <li><strong>Load Today's Board</strong><span>Rank available props by final edge and confidence.</span></li>
        <li><strong>Run a Pick</strong><span>Review probability, implied odds, edge, confidence, and raw details only if needed.</span></li>
      </ol>
    `;

    target.prepend(card);
  }

  function movePanels() {
    const simpleApp = byId("simplePropApp");
    if (simpleApp) page("today-board")?.appendChild(simpleApp);

    setSummary(closestDetailsById("dailyBeforeButton"), "Daily ML Runbook");
    setSummary(closestDetailsById("unifiedPredictButton"), "Unified Prop Card");
    setSummary(closestDetailsById("allDataPredictButton"), "All Data Prop Predictor");
    setSummary(closestDetailsById("predictionDashboardLoadButton"), "P&L / Performance Dashboard");
    setSummary(closestDetailsById("predictionSaveButton"), "Prediction History & Grading");
    setSummary(closestDetailsById("modelRefreshButton"), "Refresh Today's Data");
    setSummary(closestDetailsById("incrementalStatsCatchupButton") || closestDetailsById("incrementalStatsStatusButton"), "Player Stats Database");

    addGroup("today-board", "Daily Runbook", "Prepare the slate before betting and verify the data pipeline status.", [
      closestDetailsById("dailyBeforeButton"),
    ]);

    addGroup("run-pick", "Run a Pick", "Use one active bet context across the prediction tools. Results render as cards first; raw JSON stays available below.", [
      closestDetailsById("unifiedPredictButton"),
      closestDetailsById("allDataPredictButton"),
      closestDetailsById("propMlPredictButton"),
      closestDetailsById("moneylinePredictButton"),
    ]);

    addGroup("my-picks", "My Picks", "Track open picks, grading, ROI, and market-level model performance.", [
      closestDetailsById("predictionDashboardLoadButton"),
      closestDetailsById("predictionSaveButton"),
    ]);

    addGroup("tools-data", "Tools & Data", "Power-user refresh, sync, diagnostics, source data, and admin utilities.", [
      closestDetailsById("dataHealthButton"),
      detailsBySummaryText("data manager"),
      closestDetailsById("modelRefreshButton"),
      closestDetailsById("incrementalStatsCatchupButton") || closestDetailsById("incrementalStatsStatusButton"),
      closestDetailsById("weatherSyncButton"),
      closestDetailsById("savantSyncButton"),
      closestDetailsById("oddsMovementSyncButton"),
      closestDetailsById("pipelinePullPropsButton"),
      $(".mlb-panel"),
      $(".espn-panel"),
      $(".github-panel"),
      $(".needs-panel"),
    ]);

    const workspace = $(".workspace");
    if (workspace) workspace.hidden = true;
    closeDetailsExceptPrimary();
    addOnboardingCard();
  }

  function requestedPage() {
    const hash = window.location.hash.replace(/^#/, "");
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
  }

  function init() {
    createShell();
    movePanels();
    showPage(requestedPage());
    window.addEventListener("hashchange", () => showPage(requestedPage()));
    document.documentElement.classList.remove("app-pages-booting");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
