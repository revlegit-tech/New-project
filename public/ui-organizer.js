(() => {
  function $(selector, root = document) {
    return root.querySelector(selector);
  }

  function all(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function createSection(title, subtitle, className = "") {
    const section = document.createElement("section");
    section.className = `ui-task-section ${className}`.trim();

    const header = document.createElement("div");
    header.className = "ui-task-section-header";

    const h2 = document.createElement("h2");
    h2.textContent = title;

    const p = document.createElement("p");
    p.textContent = subtitle;

    header.append(h2, p);
    section.append(header);

    return section;
  }

  function normalizeSummary(details, label) {
    const summary = $("summary", details);
    if (summary) summary.textContent = label;
  }

  function moveIfExists(section, node) {
    if (node) section.appendChild(node);
  }

  function detailsByContainedId(id) {
    const element = document.getElementById(id);
    return element ? element.closest("details") : null;
  }

  function detailsBySummaryText(text) {
    return all("details").find((details) => {
      const summary = $("summary", details);
      return summary && summary.textContent.toLowerCase().includes(text.toLowerCase());
    });
  }

  function addQuickGuide(container) {
    if ($("#uiQuickGuide")) return;

    const guide = document.createElement("section");
    guide.id = "uiQuickGuide";
    guide.className = "ui-quick-guide";
    guide.innerHTML = `
      <div>
        <p class="eyebrow">Start here</p>
        <h2>Daily task order</h2>
      </div>
      <ol>
        <li><strong>Before games:</strong> pull props and auto-save game odds.</li>
        <li><strong>After games:</strong> grade results, merge odds, and train ready models.</li>
        <li><strong>Check models:</strong> see which markets are ready.</li>
        <li><strong>Predict:</strong> use Player Prop ML or Moneyline ML.</li>
      </ol>
    `;

    container.prepend(guide);
  }

  function organizePanels() {
    const controls = $(".panel.controls");
    if (!controls || $("#uiOrganizedSections")) return;

    const organizer = document.createElement("div");
    organizer.id = "uiOrganizedSections";
    organizer.className = "ui-organized-sections";

    const workflowSection = createSection(
      "1. Daily Workflow",
      "Run the app in order: before games, after games, then model status.",
      "primary"
    );

    const predictionsSection = createSection(
      "2. Predictions",
      "Use these after your models and data are ready.",
      "predictions"
    );

    const dataSection = createSection(
      "3. Data & Model Maintenance",
      "Refresh MLB/ESPN/model inputs or manage uploaded datasets.",
      "data-tools"
    );

    const advancedSection = createSection(
      "Advanced Tools",
      "Manual pipeline and debugging tools. You usually do not need these.",
      "advanced"
    );

    const daily = detailsByContainedId("dailyBeforeButton");
    const allDataProp = detailsByContainedId("allDataPredictButton");
    const propMl = detailsByContainedId("propMlPredictButton");
    const moneyline = detailsByContainedId("moneylinePredictButton");
    const pipeline = detailsByContainedId("pipelinePullPropsButton");
    const modelRefresh = detailsByContainedId("modelRefreshButton");
    const dataManager = detailsBySummaryText("data manager");

    normalizeSummary(daily, "1. Daily Workflow ? Start Here");
    normalizeSummary(allDataProp, "2A. All Data Prop Predictor");
    normalizeSummary(propMl, "2B. Player Prop ML");
    normalizeSummary(moneyline, "2B. Moneyline ML");
    normalizeSummary(modelRefresh, "3A. Refresh Model Data");
    normalizeSummary(dataManager, "3B. Data Manager");
    normalizeSummary(pipeline, "Advanced: Manual Pipeline Tools");

    if (daily) daily.open = true;
    if (allDataProp) allDataProp.open = true;
    if (propMl) propMl.open = false;
    if (moneyline) moneyline.open = false;
    if (modelRefresh) modelRefresh.open = false;
    if (dataManager) dataManager.open = false;
    if (pipeline) pipeline.open = false;

    moveIfExists(workflowSection, daily);
    moveIfExists(predictionsSection, allDataProp);
    moveIfExists(predictionsSection, propMl);
    moveIfExists(predictionsSection, moneyline);
    moveIfExists(dataSection, modelRefresh);
    moveIfExists(dataSection, dataManager);
    moveIfExists(advancedSection, pipeline);

    organizer.append(workflowSection, predictionsSection, dataSection, advancedSection);

    const predictButton = $("#predictButton");
    const insertAfter = predictButton || controls.children[controls.children.length - 1];
    insertAfter.insertAdjacentElement("afterend", organizer);

    addQuickGuide(controls);

    document.body.classList.add("organized-ui");
  }

  function improveDailyButtons() {
    const before = $("#dailyBeforeButton");
    const after = $("#dailyAfterButton");
    const status = $("#dailyStatusButton");

    if (before) before.textContent = "1. Run Before Games";
    if (after) after.textContent = "2. Run After Games";
    if (status) status.textContent = "3. Check Models";
  }

  function improvePanelHelpText() {
    const dailyStatus = $("#dailyWorkflowStatus");
    if (dailyStatus) {
      dailyStatus.textContent =
        "Use this in order. Run Before Games before the slate, Run After Games when games are final, then Check Models.";
    }

    const propStatus = $("#propMlStatus");
    if (propStatus) {
      propStatus.textContent =
        "Use after Check Models shows the market is ready. Fill player, team, opponent, line, and odds.";
    }

    const moneylineStatus = $("#moneylineStatus");
    if (moneylineStatus) {
      moneylineStatus.textContent =
        "Enter team odds to compare model win probability against sportsbook implied probability.";
    }
  }

  function init() {
    organizePanels();
    improveDailyButtons();
    improvePanelHelpText();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
