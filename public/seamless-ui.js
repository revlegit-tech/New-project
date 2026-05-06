(() => {
  function $(selector, root = document) {
    return root.querySelector(selector);
  }

  function all(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function closestDetailsById(id) {
    const element = document.getElementById(id);
    return element ? element.closest("details") : null;
  }

  function moveIfExists(parent, child) {
    if (child) parent.appendChild(child);
  }

  function makeCard(title, subtitle, id = "") {
    const card = document.createElement("section");
    card.className = "seamless-card";
    if (id) card.id = id;

    const header = document.createElement("div");
    header.className = "seamless-card-header";

    const h2 = document.createElement("h2");
    h2.textContent = title;

    const p = document.createElement("p");
    p.textContent = subtitle;

    header.append(h2, p);
    card.appendChild(header);

    return card;
  }

  function normalizeSummary(details, label) {
    if (!details) return;
    const summary = $("summary", details);
    if (summary) summary.textContent = label;
  }

  function createCommandCenter() {
    if ($("#seamlessCommandCenter")) return;

    const controls = $(".panel.controls");
    if (!controls) return;

    const command = document.createElement("section");
    command.id = "seamlessCommandCenter";
    command.className = "seamless-command-center";

    command.innerHTML = `
      <div class="seamless-hero">
        <p class="eyebrow">Start here</p>
        <h2>Daily Betting Workflow</h2>
        <p>Use this page from top to bottom: check data, choose a slate, pick a matchup, select a prop, predict, then save.</p>
      </div>

      <div class="seamless-flow-strip">
        <div><strong>1</strong><span>Check Data</span></div>
        <div><strong>2</strong><span>Choose Date</span></div>
        <div><strong>3</strong><span>Pick Matchup</span></div>
        <div><strong>4</strong><span>Predict + Save</span></div>
      </div>
    `;

    const titleBlock = controls.querySelector("h1")?.closest("div") || controls.firstElementChild;
    if (titleBlock) {
      titleBlock.insertAdjacentElement("afterend", command);
    } else {
      controls.prepend(command);
    }
  }

  function reorganizePanels() {
    if ($("#seamlessMainWorkflow")) return;

    const controls = $(".panel.controls");
    if (!controls) return;

    createCommandCenter();

    const predictionHistory = closestDetailsById("predictionSaveButton");
    const savantFeatures = closestDetailsById("savantSyncButton");
    const oddsMovement = closestDetailsById("oddsMovementSyncButton");
    const weatherFeatures = closestDetailsById("weatherSyncButton");
    const incrementalStats = closestDetailsById("incrementalStatsCatchupButton");
    const unifiedCard = closestDetailsById("unifiedPredictButton");
    const dataHealth = closestDetailsById("dataHealthButton");
    const allData = closestDetailsById("allDataPredictButton");
    const daily = closestDetailsById("dailyBeforeButton");
    const dataHub = closestDetailsById("dataHubSyncButton");
    const external = closestDetailsById("externalSyncButton");
    const autoRunner = closestDetailsById("autoBeforeButton");
    const propMl = closestDetailsById("propMlPredictButton");
    const moneyline = closestDetailsById("moneylinePredictButton");
    const pipeline = closestDetailsById("pipelinePullPropsButton");
    const dataManager = all("details").find((details) => {
      const summary = $("summary", details);
      return summary && summary.textContent.toLowerCase().includes("data manager");
    });
    const modelRefresh = closestDetailsById("modelRefreshButton");

    normalizeSummary(predictionHistory, "0A. Prediction History & Grading");
    normalizeSummary(savantFeatures, "0B. Baseball Savant Metrics");
    normalizeSummary(oddsMovement, "0B. Odds Movement Snapshots");
    normalizeSummary(weatherFeatures, "0B. Weather Features");
    normalizeSummary(incrementalStats, "0B. Incremental Stats Warehouse");
    normalizeSummary(unifiedCard, "1. Unified Prop Card");
    normalizeSummary(dataHealth, "2. Data Health");
    normalizeSummary(allData, "2. All Data Prop Predictor");
    normalizeSummary(daily, "3. Daily Workflow / Model Updates");
    normalizeSummary(dataHub, "Data Hub Sync");
    normalizeSummary(external, "External Sources");
    normalizeSummary(autoRunner, "Autonomous Runner");
    normalizeSummary(propMl, "Player Prop ML");
    normalizeSummary(moneyline, "Moneyline ML");
    normalizeSummary(pipeline, "Manual Pipeline Tools");
    normalizeSummary(dataManager, "Data Manager");
    normalizeSummary(modelRefresh, "Refresh Model Data");

    const main = document.createElement("div");
    main.id = "seamlessMainWorkflow";
    main.className = "seamless-main-workflow";

    const primary = makeCard(
      "Main Workflow",
      "Everything you need for daily use. Start here and work downward."
    );

    const supporting = makeCard(
      "Supporting Sync Tools",
      "Use these only when data is missing or you want to manually refresh sources."
    );

    const predictions = makeCard(
      "Other Prediction Tools",
      "Secondary models and legacy prediction panels."
    );

    const advanced = makeCard(
      "Legacy / Advanced Tools",
      "Older manual controls are kept here so they do not clutter the main workflow."
    );

    moveIfExists(primary, predictionHistory);
    moveIfExists(primary, savantFeatures);
    moveIfExists(primary, oddsMovement);
    moveIfExists(primary, weatherFeatures);
    moveIfExists(primary, incrementalStats);
    moveIfExists(primary, unifiedCard);
    moveIfExists(primary, dataHealth);
    moveIfExists(primary, allData);
    moveIfExists(primary, daily);

    moveIfExists(supporting, dataHub);
    moveIfExists(supporting, external);
    moveIfExists(supporting, autoRunner);

    moveIfExists(predictions, moneyline);
    moveIfExists(predictions, propMl);

    moveIfExists(advanced, modelRefresh);
    moveIfExists(advanced, dataManager);
    moveIfExists(advanced, pipeline);

    [supporting, predictions, advanced].forEach((card) => {
      const details = document.createElement("details");
      details.className = "seamless-card-details";

      const summary = document.createElement("summary");
      summary.textContent = card.querySelector("h2")?.textContent || "More tools";

      const body = document.createElement("div");
      body.className = "seamless-card-details-body";

      while (card.children.length > 1) {
        body.appendChild(card.children[1]);
      }

      card.append(details);
      details.append(summary, body);
    });

    main.append(primary, supporting, predictions, advanced);

    const command = $("#seamlessCommandCenter");
    if (command) {
      command.insertAdjacentElement("afterend", main);
    } else {
      controls.prepend(main);
    }

    // Hide old basic/manual predictor controls that are duplicated by All Data.
    [
      "#playerControl",
      "#targetSelect",
      "#lineControl",
      "#americanOdds",
      "#teamSearch",
      "#pitcherControl",
      "#adjustment",
      "#predictButton"
    ].forEach((selector) => {
      const node = $(selector);
      const wrap = node?.closest("label") || node;
      if (wrap) wrap.classList.add("seamless-hidden-legacy");
    });

    document.body.classList.add("seamless-ui");
  }

  function improveAllDataText() {
    const loadGames = $("#allDataLoadGamesButton");
    const loadProps = $("#allDataLoadPropsButton");
    const predict = $("#allDataPredictButton");
    const save = $("#allDataSavePredictionButton");

    if (loadGames) loadGames.textContent = "Load Matchups";
    if (loadProps) loadProps.textContent = "Load Props For Selected Matchup";
    if (predict) predict.textContent = "Run Prediction";
    if (save) save.textContent = "Save Pick";
  }

  function init() {
    reorganizePanels();
    improveAllDataText();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
