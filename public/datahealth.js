(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    date: $("#dataHealthDate"),
    button: $("#dataHealthButton"),
    status: $("#dataHealthStatus"),
    output: $("#dataHealthOutput"),
    props: $("#healthProps"),
    games: $("#healthGames"),
    boxscores: $("#healthBoxscores"),
    warnings: $("#healthWarnings"),
  };

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  async function getJson(path) {
    const response = await fetch(path);
    const text = await response.text();

    let payload;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`Endpoint returned non-JSON. Status ${response.status}. First text: ${text.slice(0, 120)}`);
    }

    if (!response.ok) {
      throw new Error(payload.error || `Request failed ${response.status}`);
    }

    return payload;
  }

  function readable(payload) {
    const health = payload.health || {};
    const warnings = payload.warnings || [];

    return [
      "Data Health Dashboard",
      "=====================",
      "",
      `Date: ${payload.date}`,
      `Season: ${payload.season}`,
      `Status: ${payload.ok ? "OK" : "Needs attention"}`,
      "",
      "Core Data",
      "---------",
      `MLB games: ${health.mlbGames ?? 0}`,
      `Final games: ${health.finalGames ?? 0}`,
      `Boxscores saved: ${health.boxscoresSaved ?? 0}`,
      `PropLine props: ${health.propCount ?? 0}`,
      `Prop events: ${health.propEvents ?? 0}`,
      `Game odds rows: ${health.gameOddsRows ?? 0}`,
      `Moneyline rows: ${health.rowsWithMoneyline ?? 0}`,
      `Total rows: ${health.rowsWithTotal ?? 0}`,
      `Weather rows: ${health.weatherRows ?? 0}`,
      "",
      "Season Logs",
      "-----------",
      `Batter log rows: ${health.batterLogRows ?? 0}`,
      `Pitcher log rows: ${health.pitcherLogRows ?? 0}`,
      `Team log rows: ${health.teamLogRows ?? 0}`,
      `Prediction history rows: ${health.predictionHistoryRows ?? 0}`,
      "",
      "Warnings",
      "--------",
      warnings.length ? warnings.map((x) => `- ${x}`).join("\n") : "None",
      "",
      "Important Files",
      "---------------",
      `Props: ${payload.files?.propsFile || "--"}`,
      `Game odds: ${payload.files?.gameOddsFile || "--"}`,
      `Latest odds snapshot: ${payload.files?.latestOddsSnapshot || "--"}`,
      `Prediction history: ${payload.files?.predictionHistory || "--"}`,
      "",
      "Raw JSON",
      "--------",
      JSON.stringify(payload, null, 2),
    ].join("\n");
  }

  function setOutput(message, payload) {
    if (els.status) els.status.textContent = message;
    if (els.output) els.output.textContent = readable(payload);

    const health = payload.health || {};
    if (els.props) els.props.textContent = health.propCount ?? "--";
    if (els.games) els.games.textContent = health.mlbGames ?? "--";
    if (els.boxscores) els.boxscores.textContent = health.boxscoresSaved ?? "--";
    if (els.warnings) els.warnings.textContent = (payload.warnings || []).length;
  }

  async function checkHealth() {
    try {
      if (els.status) els.status.textContent = "Checking data health...";
      const date = els.date?.value || today();
      const payload = await getJson(`/api/data-health?date=${encodeURIComponent(date)}`);
      setOutput(payload.ok ? "Data health looks good." : "Data health loaded with warnings.", payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Data health failed: ${error.message}`;
      if (els.output) els.output.textContent = `Data health failed\n\n${error.message}`;
    }
  }



  function playerboardHealthReadable(payload) {
    const markets = payload.marketsPresent || {};
    const marketLines = Object.keys(markets).length
      ? Object.entries(markets).map(([market, count]) => `- ${market}: ${count}`).join("\n")
      : "None";

    const warnings = [];
    if (!payload.exists) warnings.push("Playerboard file does not exist.");
    if (!payload.schemaOk) warnings.push(`Schema issue: ${payload.schemaIssue || "unknown"}`);
    if (payload.rowsLoaded <= 0) warnings.push("No Playerboard rows loaded for this date/filter.");
    if (payload.missingMarketDisplayRows > 0) warnings.push(`${payload.missingMarketDisplayRows} rows missing marketDisplay.`);
    if (payload.badShiftedRows > 0) warnings.push(`${payload.badShiftedRows} shifted/misaligned rows detected.`);

    return [
      "Playerboard Health",
      "==================",
      "",
      `Date: ${payload.date || "--"}`,
      `Requested date: ${payload.requestedDate || "--"}`,
      `Latest saved date: ${payload.latestAvailableDate || "--"}`,
      `Season: ${payload.season || "--"}`,
      `Status: ${payload.ok ? "OK" : "Needs attention"}`,
      `Schema: ${payload.schemaVersion || "--"}`,
      `Schema OK: ${payload.schemaOk ? "yes" : "no"}`,
      `Schema issue: ${payload.schemaIssue || "none"}`,
      "",
      "Rows",
      "----",
      `Rows loaded for filter: ${payload.rowsLoaded ?? 0}`,
      `Total rows in file: ${payload.totalRowsInFile ?? 0}`,
      `Missing marketDisplay rows: ${payload.missingMarketDisplayRows ?? 0}`,
      `Bad shifted rows: ${payload.badShiftedRows ?? 0}`,
      `Latest snapshot: ${payload.latestSnapshotAt || "--"}`,
      "",
      "Markets Present",
      "---------------",
      marketLines,
      "",
      "Warnings",
      "--------",
      warnings.length ? warnings.map((x) => `- ${x}`).join("\n") : "None",
      "",
      "Raw JSON",
      "--------",
      JSON.stringify(payload, null, 2),
    ].join("\n");
  }

  function ensurePlayerboardHealthPanel() {
    if ($("#playerboardHealthPanel")) return;

    const output = els.output || document.body;
    const panel = document.createElement("section");
    panel.id = "playerboardHealthPanel";
    panel.className = "muse-data-health-panel";
    panel.innerHTML = `
      <div class="muse-card" style="margin-top: 16px;">
        <h3>Playerboard Health</h3>
        <p>Check saved Playerboard schema, row alignment, market coverage, and missing display labels.</p>
        <div class="muse-actions" style="display:flex; gap: 8px; flex-wrap: wrap; margin: 8px 0;">
          <button id="playerboardHealthButton" type="button" class="muse-secondary">Check Playerboard Health</button>
          <button id="playerboardHealthTodayButton" type="button" class="muse-secondary">Use Today</button>
        </div>
        <div id="playerboardHealthStatus" class="muse-status">Playerboard health has not loaded yet.</div>
        <pre id="playerboardHealthOutput" class="muse-output" style="white-space: pre-wrap;"></pre>
      </div>
    `;

    output.insertAdjacentElement("afterend", panel);
  }

  async function checkPlayerboardHealth() {
    const status = $("#playerboardHealthStatus");
    const output = $("#playerboardHealthOutput");

    try {
      if (status) status.textContent = "Checking Playerboard health...";
      const requestedDate = els.date?.value || today();
      let payload = await getJson(`/api/playerboard/health?season=2026&date=${encodeURIComponent(requestedDate)}`);

      if ((payload.rowsLoaded || 0) <= 0 && payload.latestAvailableDate && payload.latestAvailableDate !== requestedDate) {
        if (status) status.textContent = `No Playerboard rows for ${requestedDate}. Loading latest saved date ${payload.latestAvailableDate}...`;
        payload = await getJson(`/api/playerboard/health?season=2026&date=${encodeURIComponent(payload.latestAvailableDate)}`);
        payload.requestedDate = requestedDate;
        payload.usedLatestAvailableDate = true;
        if (els.date) els.date.value = payload.date;
      }

      if (status) {
        if (payload.ok && payload.usedLatestAvailableDate) {
          status.textContent = `Playerboard health looks good. Showing latest saved date ${payload.date}.`;
        } else {
          status.textContent = payload.ok
            ? "Playerboard health looks good."
            : "Playerboard health loaded with warnings.";
        }
      }

      if (output) output.textContent = playerboardHealthReadable(payload);
    } catch (error) {
      console.error(error);
      if (status) status.textContent = `Playerboard health failed: ${error.message}`;
      if (output) output.textContent = `Playerboard health failed\n\n${error.message}`;
    }
  }




  function gradingHealthReadable(payload) {
    const counts = payload.counts || {};
    const summary = payload.summary || {};
    const warnings = payload.warnings || [];
    const errors = payload.errors || [];

    return [
      "Grading Health",
      "==============",
      "",
      `Latest grading date: ${payload.date || "--"}`,
      `Requested date: ${payload.requestedDate || "--"}`,
      `Season: ${payload.season || "--"}`,
      `Status: ${payload.ok ? "OK" : "Needs attention"}`,
      `Checked at: ${payload.checkedAt || "--"}`,
      "",
      "Backtest",
      "--------",
      `Rows for date: ${summary.backtestRowsForDate ?? counts.backtestRowsForDate ?? 0}`,
      `Graded rows: ${summary.gradedBacktestRowsForDate ?? counts.gradedBacktestRowsForDate ?? 0}`,
      `Results: ${JSON.stringify(counts.backtestResultsForDate || {}, null, 2)}`,
      "",
      "ML Export",
      "---------",
      `Rows for date: ${summary.mlRowsForDate ?? counts.mlRowsForDate ?? 0}`,
      `Graded rows: ${summary.gradedMlRowsForDate ?? counts.gradedMlRowsForDate ?? 0}`,
      `Results: ${JSON.stringify(counts.mlResultsForDate || {}, null, 2)}`,
      "",
      "Warnings",
      "--------",
      warnings.length ? warnings.map((x) => `- ${x}`).join("\n") : "None",
      "",
      "Errors",
      "------",
      errors.length ? errors.map((x) => `- ${x}`).join("\n") : "None",
      "",
      "Raw JSON",
      "--------",
      JSON.stringify(payload, null, 2),
    ].join("\n");
  }

  function ensureGradingHealthPanel() {
    if ($("#gradingHealthPanel")) return;

    const playerboardPanel = $("#playerboardHealthPanel");
    const output = playerboardPanel || els.output || document.body;

    const panel = document.createElement("section");
    panel.id = "gradingHealthPanel";
    panel.className = "muse-data-health-panel";
    panel.innerHTML = `
      <div class="muse-card" style="margin-top: 16px;">
        <h3>Grading Health</h3>
        <p>Check the latest daily grading summary, backtest grading counts, ML export counts, warnings, and errors.</p>
        <div class="muse-actions" style="display:flex; gap: 8px; flex-wrap: wrap; margin: 8px 0;">
          <button id="gradingHealthButton" type="button" class="muse-secondary">Check Grading Health</button>
          <button id="gradingHealthDateButton" type="button" class="muse-secondary">Use Selected Date</button>
        </div>
        <div id="gradingHealthStatus" class="muse-status">Grading health has not loaded yet.</div>
        <pre id="gradingHealthOutput" class="muse-output" style="white-space: pre-wrap;"></pre>
      </div>
    `;

    output.insertAdjacentElement("afterend", panel);
  }

  async function checkGradingHealth() {
    const status = $("#gradingHealthStatus");
    const output = $("#gradingHealthOutput");

    try {
      if (status) status.textContent = "Checking grading health...";
      const date = els.date?.value || today();
      const payload = await getJson(`/api/grading/health?date=${encodeURIComponent(date)}`);

      if (status) {
        status.textContent = payload.ok
          ? "Grading health looks good."
          : "Grading health loaded with warnings.";
      }

      if (output) output.textContent = gradingHealthReadable(payload);
    } catch (error) {
      console.error(error);
      if (status) status.textContent = `Grading health failed: ${error.message}`;
      if (output) output.textContent = `Grading health failed\n\n${error.message}`;
    }
  }




  function workflowSummariesReadable(payload) {
    const summaries = payload.summaries || {};
    const labels = {
      dailyHealth: "Daily Health Check",
      dailyGrading: "Daily Grading",
      weeklyRepair: "Weekly Repair",
    };

    const blocks = Object.entries(labels).map(([key, label]) => {
      const item = summaries[key] || {};
      const warnings = item.warnings || [];
      const errors = item.errors || [];

      return [
        label,
        "-".repeat(label.length),
        `Status: ${item.exists ? (item.ok ? "OK" : "Needs attention") : "Missing"}`,
        `Date: ${item.date || "--"}`,
        `Checked at: ${item.checkedAt || "--"}`,
        `File: ${item.file || "--"}`,
        `Size: ${item.size ?? 0}`,
        `Warnings: ${warnings.length ? warnings.join("; ") : "None"}`,
        `Errors: ${errors.length ? errors.join("; ") : "None"}`,
      ].join("\n");
    }).join("\n\n");

    return [
      "Workflow Summaries",
      "==================",
      "",
      `Status: ${payload.ok ? "OK" : "Needs attention"}`,
      `Health dir: ${payload.healthDir || "--"}`,
      "",
      blocks,
      "",
      "Combined Warnings",
      "-----------------",
      (payload.warnings || []).length ? payload.warnings.map((x) => `- ${x}`).join("\n") : "None",
      "",
      "Combined Errors",
      "---------------",
      (payload.errors || []).length ? payload.errors.map((x) => `- ${x}`).join("\n") : "None",
      "",
      "Raw JSON",
      "--------",
      JSON.stringify(payload, null, 2),
    ].join("\n");
  }

  function ensureWorkflowSummariesPanel() {
    if ($("#workflowSummariesPanel")) return;

    const gradingPanel = $("#gradingHealthPanel");
    const playerboardPanel = $("#playerboardHealthPanel");
    const output = gradingPanel || playerboardPanel || els.output || document.body;

    const panel = document.createElement("section");
    panel.id = "workflowSummariesPanel";
    panel.className = "muse-data-health-panel";
    panel.innerHTML = `
      <div class="muse-card" style="margin-top: 16px;">
        <h3>Workflow Summaries</h3>
        <p>Review latest daily health, daily grading, and weekly repair summary files from one place.</p>
        <div class="muse-actions" style="display:flex; gap: 8px; flex-wrap: wrap; margin: 8px 0;">
          <button id="workflowSummariesButton" type="button" class="muse-secondary">Check Workflow Summaries</button>
        </div>
        <div id="workflowSummariesStatus" class="muse-status">Workflow summaries have not loaded yet.</div>
        <pre id="workflowSummariesOutput" class="muse-output" style="white-space: pre-wrap;"></pre>
      </div>
    `;

    output.insertAdjacentElement("afterend", panel);
  }

  async function checkWorkflowSummaries() {
    const status = $("#workflowSummariesStatus");
    const output = $("#workflowSummariesOutput");

    try {
      if (status) status.textContent = "Checking workflow summaries...";
      const payload = await getJson("/api/workflows/health");

      if (status) {
        status.textContent = payload.ok
          ? "Workflow summaries look good."
          : "Workflow summaries loaded with warnings.";
      }

      if (output) output.textContent = workflowSummariesReadable(payload);
    } catch (error) {
      console.error(error);
      if (status) status.textContent = `Workflow summaries failed: ${error.message}`;
      if (output) output.textContent = `Workflow summaries failed\n\n${error.message}`;
    }
  }





  function systemOverviewStatusClass(ok, exists = true) {
    if (!exists) return "warn";
    return ok ? "ok" : "bad";
  }

  function systemOverviewCard(title, statusClass, status, detail, meta = "") {
    return `
      <div class="system-overview-card ${statusClass}">
        <div class="system-overview-top">
          <span class="system-overview-dot"></span>
          <strong>${title}</strong>
        </div>
        <div class="system-overview-status">${status}</div>
        <div class="system-overview-detail">${detail}</div>
        ${meta ? `<div class="system-overview-meta">${meta}</div>` : ""}
      </div>
    `;
  }

  function renderSystemOverview(payload) {
    const data = payload.dataHealth || {};
    const health = data.health || {};
    const playerboard = payload.playerboard || {};
    const grading = payload.grading || {};
    const gradingSummary = grading.summary || {};
    const workflows = payload.workflows || {};
    const summaries = workflows.summaries || {};
    const dailyHealth = summaries.dailyHealth || {};
    const dailyGrading = summaries.dailyGrading || {};
    const weeklyRepair = summaries.weeklyRepair || {};

    return [
      systemOverviewCard(
        "Data Health",
        systemOverviewStatusClass(data.ok, true),
        data.ok ? "OK" : "Needs attention",
        `${data.date || "--"} | ${health.mlbGames ?? 0} games | ${health.propCount ?? 0} props`,
        `${(data.warnings || []).length} warning(s)`
      ),
      systemOverviewCard(
        "Playerboard",
        systemOverviewStatusClass(playerboard.ok, playerboard.exists),
        playerboard.ok ? "OK" : "Needs attention",
        `${playerboard.date || playerboard.latestAvailableDate || "--"} | ${playerboard.rowsLoaded ?? 0} rows`,
        `${playerboard.badShiftedRows ?? 0} shifted | ${playerboard.missingMarketDisplayRows ?? 0} missing labels`
      ),
      systemOverviewCard(
        "Grading",
        systemOverviewStatusClass(grading.ok, grading.exists),
        grading.ok ? "OK" : "Needs attention",
        `${grading.date || "--"} | ${gradingSummary.gradedBacktestRowsForDate ?? 0}/${gradingSummary.backtestRowsForDate ?? 0} graded`,
        `${gradingSummary.gradedMlRowsForDate ?? 0}/${gradingSummary.mlRowsForDate ?? 0} ML graded`
      ),
      systemOverviewCard(
        "Workflows",
        systemOverviewStatusClass(workflows.ok, true),
        workflows.ok ? "OK" : "Needs attention",
        `Daily ${dailyHealth.date || "--"} | Grading ${dailyGrading.date || "--"}`,
        `Repair ${weeklyRepair.date || "--"}`
      ),
    ].join("");
  }

  function ensureSystemOverviewPanel() {
    if ($("#systemOverviewPanel")) return;

    const anchor = els.output?.closest(".muse-card") || els.output || document.body;

    const panel = document.createElement("section");
    panel.id = "systemOverviewPanel";
    panel.className = "muse-data-health-panel";
    panel.innerHTML = `
      <div class="muse-card system-overview-shell">
        <div class="system-overview-header">
          <div>
            <h3>System Overview</h3>
            <p>Quick status for data health, Playerboard integrity, grading, and workflow summaries.</p>
          </div>
          <button id="systemOverviewButton" type="button" class="muse-secondary">Refresh Overview</button>
        </div>
        <div id="systemOverviewStatus" class="muse-status">Overview has not loaded yet.</div>
        <div id="systemOverviewGrid" class="system-overview-grid">
          ${systemOverviewCard("Data Health", "warn", "Waiting", "Click Refresh Overview")}
          ${systemOverviewCard("Playerboard", "warn", "Waiting", "Click Refresh Overview")}
          ${systemOverviewCard("Grading", "warn", "Waiting", "Click Refresh Overview")}
          ${systemOverviewCard("Workflows", "warn", "Waiting", "Click Refresh Overview")}
        </div>
      </div>
    `;

    anchor.insertAdjacentElement("beforebegin", panel);
  }

  async function checkSystemOverview() {
    const status = $("#systemOverviewStatus");
    const grid = $("#systemOverviewGrid");

    try {
      if (status) status.textContent = "Checking system overview...";
      const date = els.date?.value || today();

      const [dataHealth, playerboardRaw, grading, workflows] = await Promise.all([
        getJson(`/api/data-health?date=${encodeURIComponent(date)}`),
        getJson(`/api/playerboard/health?season=2026&date=${encodeURIComponent(date)}`),
        getJson(`/api/grading/health?date=${encodeURIComponent(date)}`),
        getJson("/api/workflows/health"),
      ]);

      let playerboard = playerboardRaw;
      if ((playerboard.rowsLoaded || 0) <= 0 && playerboard.latestAvailableDate && playerboard.latestAvailableDate !== date) {
        playerboard = await getJson(`/api/playerboard/health?season=2026&date=${encodeURIComponent(playerboard.latestAvailableDate)}`);
      }

      const payload = { dataHealth, playerboard, grading, workflows };

      if (grid) grid.innerHTML = renderSystemOverview(payload);

      const ok = Boolean(dataHealth.ok) && Boolean(playerboard.ok) && Boolean(grading.ok) && Boolean(workflows.ok);
      if (status) {
        status.textContent = ok
          ? "System overview looks good."
          : "System overview loaded with warnings.";
      }
    } catch (error) {
      console.error(error);
      if (status) status.textContent = `System overview failed: ${error.message}`;
      if (grid) {
        grid.innerHTML = systemOverviewCard(
          "System Overview",
          "bad",
          "Failed",
          error.message,
          "Check app server and endpoint logs."
        );
      }
    }
  }


  function ensureDataAdminPolishStyles() {
    if (document.getElementById("dataAdminPolishStyles")) return;

    const style = document.createElement("style");
    style.id = "dataAdminPolishStyles";
    style.textContent = `
      /* Premium Data Admin polish v1 */
      :root {
        --admin-ink: #0f172a;
        --admin-muted: #64748b;
        --admin-border: rgba(148, 163, 184, 0.24);
        --admin-primary: #2563eb;
        --admin-soft: #f8fafc;
        --admin-shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
        --admin-soft-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
      }

      body {
        background:
          radial-gradient(circle at top, rgba(59, 130, 246, 0.08), transparent 34rem),
          linear-gradient(180deg, #f8fbff 0%, #eef4ff 100%);
      }

      .muse-data-health-panel,
      .muse-card,
      section {
        scroll-margin-top: 24px;
      }

      .muse-data-health-panel .muse-card,
      .muse-card:has(#playerboardHealthButton),
      .muse-card:has(#gradingHealthButton),
      .muse-card:has(#workflowSummariesButton) {
        border-radius: 24px;
        border: 1px solid var(--admin-border);
        background: rgba(255, 255, 255, 0.94);
        box-shadow: var(--admin-shadow);
        padding: 26px;
      }

      .muse-data-health-panel h3,
      .muse-card h3 {
        color: var(--admin-ink);
        font-size: clamp(1.2rem, 1.8vw, 1.65rem);
        letter-spacing: -0.035em;
        margin-bottom: 8px;
      }

      .muse-data-health-panel p,
      .muse-card p {
        color: var(--admin-muted);
        max-width: 780px;
        line-height: 1.5;
      }

      .muse-data-health-panel .muse-actions,
      .muse-card .muse-actions {
        justify-content: flex-start;
        margin-top: 16px !important;
        gap: 10px !important;
      }

      .muse-data-health-panel button,
      .muse-card button,
      .muse-secondary {
        min-height: 42px;
        padding: 10px 16px;
        border-radius: 14px;
        font-weight: 850;
        border: 1px solid #c7d7fe;
        background: #eef4ff;
        color: #1d4ed8;
        box-shadow: none;
        transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease;
      }

      .muse-data-health-panel button:hover,
      .muse-card button:hover,
      .muse-secondary:hover {
        transform: translateY(-1px);
        box-shadow: 0 10px 22px rgba(37, 99, 235, 0.14);
        background: #e0eaff;
      }

      .muse-status,
      #playerboardHealthStatus,
      #gradingHealthStatus,
      #workflowSummariesStatus {
        margin-top: 12px;
        color: var(--admin-muted);
        font-weight: 750;
      }

      .muse-output,
      #playerboardHealthOutput,
      #gradingHealthOutput,
      #workflowSummariesOutput {
        margin-top: 16px;
        max-height: 520px;
        overflow: auto;
        padding: 18px;
        border-radius: 18px;
        border: 1px solid rgba(148, 163, 184, 0.24);
        background:
          linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
        color: #172033;
        font-size: 0.82rem;
        line-height: 1.45;
      }


      /* Premium System Overview panel v3 */
      .system-overview-shell {
        margin-bottom: 16px;
      }

      .system-overview-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 16px;
        margin-bottom: 14px;
      }

      .system-overview-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin-top: 16px;
      }

      .system-overview-card {
        min-height: 132px;
        padding: 16px;
        border-radius: 20px;
        border: 1px solid rgba(148, 163, 184, 0.22);
        background:
          radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), transparent 14rem),
          linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
        box-shadow: 0 10px 26px rgba(15, 23, 42, 0.055);
      }

      .system-overview-top {
        display: flex;
        align-items: center;
        gap: 9px;
        color: #0f172a;
        font-size: 0.82rem;
        font-weight: 950;
      }

      .system-overview-dot {
        width: 10px;
        height: 10px;
        border-radius: 999px;
        background: #22c55e;
        box-shadow: 0 0 0 5px rgba(34, 197, 94, 0.12);
      }

      .system-overview-card.warn .system-overview-dot {
        background: #f59e0b;
        box-shadow: 0 0 0 5px rgba(245, 158, 11, 0.14);
      }

      .system-overview-card.bad .system-overview-dot {
        background: #ef4444;
        box-shadow: 0 0 0 5px rgba(239, 68, 68, 0.13);
      }

      .system-overview-status {
        margin-top: 14px;
        color: #0f172a;
        font-size: 1.22rem;
        font-weight: 950;
        letter-spacing: -0.035em;
      }

      .system-overview-detail {
        margin-top: 6px;
        color: #475569;
        font-size: 0.84rem;
        font-weight: 760;
        line-height: 1.35;
      }

      .system-overview-meta {
        margin-top: 10px;
        color: #64748b;
        font-size: 0.76rem;
        font-weight: 720;
      }

      @media (max-width: 1100px) {
        .system-overview-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }
      }

      @media (max-width: 680px) {
        .system-overview-header {
          display: grid;
        }

        .system-overview-grid {
          grid-template-columns: 1fr;
        }
      }

      @media (max-width: 900px) {
        .muse-data-health-panel .muse-card,
        .muse-card:has(#playerboardHealthButton),
        .muse-card:has(#gradingHealthButton),
        .muse-card:has(#workflowSummariesButton) {
          padding: 20px;
          border-radius: 20px;
        }

        .muse-output,
        #playerboardHealthOutput,
        #gradingHealthOutput,
        #workflowSummariesOutput {
          max-height: 420px;
        }
      }
    `;

    document.head.appendChild(style);
  }


  function init() {
    ensureSystemOverviewPanel();
    ensureDataAdminPolishStyles();
    if (!els.button) return;
    if (els.date && !els.date.value) els.date.value = today();

    ensurePlayerboardHealthPanel();
    ensureGradingHealthPanel();
    ensureWorkflowSummariesPanel();

    els.button.addEventListener("click", checkHealth);

    $("#systemOverviewButton")?.addEventListener("click", checkSystemOverview);

    $("#playerboardHealthButton")?.addEventListener("click", checkPlayerboardHealth);
    $("#playerboardHealthTodayButton")?.addEventListener("click", () => {
      if (els.date) els.date.value = today();
      checkPlayerboardHealth();
    });

    $("#gradingHealthButton")?.addEventListener("click", checkGradingHealth);
    $("#gradingHealthDateButton")?.addEventListener("click", checkGradingHealth);

    $("#workflowSummariesButton")?.addEventListener("click", checkWorkflowSummaries);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
