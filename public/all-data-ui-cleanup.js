(() => {
  function $(selector, root = document) {
    return root.querySelector(selector);
  }

  function createStep(number, title, subtitle, children = []) {
    const section = document.createElement("section");
    section.className = "all-data-step";

    const header = document.createElement("div");
    header.className = "all-data-step-header";

    const badge = document.createElement("span");
    badge.className = "all-data-step-badge";
    badge.textContent = number;

    const text = document.createElement("div");
    const h3 = document.createElement("h3");
    h3.textContent = title;

    const p = document.createElement("p");
    p.textContent = subtitle;

    text.append(h3, p);
    header.append(badge, text);
    section.append(header);

    const body = document.createElement("div");
    body.className = "all-data-step-body";
    children.filter(Boolean).forEach((child) => body.appendChild(child));
    section.append(body);

    return section;
  }

  function wrapManualFields(panel) {
    if ($("#allDataAdvancedInputs", panel)) return;

    const fieldsGrid = $(".mlb-command-grid", panel);
    if (!fieldsGrid) return;

    const advanced = document.createElement("details");
    advanced.id = "allDataAdvancedInputs";
    advanced.className = "all-data-advanced";
    advanced.open = false;

    const summary = document.createElement("summary");
    summary.textContent = "Advanced manual inputs";
    advanced.appendChild(summary);
    advanced.appendChild(fieldsGrid);

    return advanced;
  }

  function buildCleanerLayout() {
    const predictButton = $("#allDataPredictButton");
    if (!predictButton) return;

    const details = predictButton.closest("details");
    if (!details || details.dataset.cleanedAllData === "1") return;

    details.dataset.cleanedAllData = "1";
    details.classList.add("all-data-clean-panel");

    const summary = $("summary", details);
    if (summary) summary.textContent = "2A. All Data Prop Predictor";

    const body = $(".model-refresh-body", details);
    if (!body) return;

    const dateInput = $("#allDataDate");
    const marketSelect = $("#allDataMarket");
    const loadGamesButton = $("#allDataLoadGamesButton");
    const gameSelect = $("#allDataGameSelect");
    const loadPropsButton = $("#allDataLoadPropsButton");
    const savedPropSelect = $("#allDataSavedProp");
    const probabilityCards = $(".stat-grid.matchup-grid", details);
    const status = $("#allDataStatus");
    const output = $("#allDataOutput");

    const originalActionWrap = predictButton.closest(".source-actions");
    const saveButton = $("#allDataSavePredictionButton");
    const bvpButton = $("#allDataBuildBvpButton");

    const advanced = wrapManualFields(body);

    const dateMarketWrap = document.createElement("div");
    dateMarketWrap.className = "all-data-two-col";
    if (dateInput?.closest("label")) dateMarketWrap.appendChild(dateInput.closest("label"));
    if (marketSelect?.closest("label")) dateMarketWrap.appendChild(marketSelect.closest("label"));

    const gamesActions = document.createElement("div");
    gamesActions.className = "source-actions compact-actions";
    if (loadGamesButton) gamesActions.appendChild(loadGamesButton);

    const gameWrap = document.createElement("div");
    gameWrap.className = "all-data-picker-wrap";
    if (gameSelect?.closest("label")) gameWrap.appendChild(gameSelect.closest("label"));

    const propActions = document.createElement("div");
    propActions.className = "source-actions compact-actions";
    if (loadPropsButton) propActions.appendChild(loadPropsButton);

    const propWrap = document.createElement("div");
    propWrap.className = "all-data-picker-wrap";
    if (savedPropSelect?.closest("label")) propWrap.appendChild(savedPropSelect.closest("label"));

    const predictActions = document.createElement("div");
    predictActions.className = "source-actions all-data-main-actions";
    if (predictButton) predictActions.appendChild(predictButton);
    if (saveButton) predictActions.appendChild(saveButton);
    if (bvpButton) {
      bvpButton.classList.add("secondary-action");
      predictActions.appendChild(bvpButton);
    }

    const resultWrap = document.createElement("div");
    resultWrap.className = "all-data-result-wrap";
    if (probabilityCards) resultWrap.appendChild(probabilityCards);
    if (status) resultWrap.appendChild(status);
    if (output) resultWrap.appendChild(output);

    const steps = document.createElement("div");
    steps.className = "all-data-guided-flow";

    steps.appendChild(createStep(
      "1",
      "Choose date and market",
      "Pick the slate date, then choose the prop market you want to evaluate.",
      [dateMarketWrap]
    ));

    steps.appendChild(createStep(
      "2",
      "Choose matchup",
      "Load games for the selected date, then choose the matchup.",
      [gamesActions, gameWrap]
    ));

    steps.appendChild(createStep(
      "3",
      "Choose player prop",
      "Load saved PropLine props for that game, then choose the player/line.",
      [propActions, propWrap]
    ));

    steps.appendChild(createStep(
      "4",
      "Predict and save",
      "Run the all-data prediction, then save it to prediction history.",
      [predictActions, resultWrap]
    ));

    if (advanced) steps.appendChild(advanced);

    body.innerHTML = "";
    body.appendChild(steps);

    if (originalActionWrap && originalActionWrap.children.length === 0) {
      originalActionWrap.remove();
    }
  }

  function init() {
    buildCleanerLayout();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
