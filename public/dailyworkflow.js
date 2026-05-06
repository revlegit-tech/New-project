(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    date: $("#dailyWorkflowDate"),
    before: $("#dailyBeforeButton"),
    after: $("#dailyAfterButton"),
    statusButton: $("#dailyStatusButton"),
    status: $("#dailyWorkflowStatus"),
    output: $("#dailyWorkflowOutput"),
  };

  function todayDateString() {
    return new Date().toISOString().slice(0, 10);
  }

  function dateValue() {
    return els.date?.value || todayDateString();
  }

  function publishWorkflowPayload(payload) {
    if (!payload || typeof payload !== "object") return;
    document.dispatchEvent(new CustomEvent("baseball:daily-workflow", { detail: payload }));
    window.Stage2ProductUI?.updateDailyRunbook?.(payload);
  }

  function setStatus(message, payload) {
    if (els.status) els.status.textContent = message;
    if (els.output && payload !== undefined) {
      els.output.textContent = readable(payload);
      publishWorkflowPayload(payload);
    }
  }

  function withActionHeader(options = {}) {
    const next = { ...options };
    if (String(next.method || "GET").toUpperCase() === "POST") {
      const headers = new Headers(next.headers || {});
      headers.set("X-Baseball-Prop-Action", "1");
      next.headers = headers;
    }
    return next;
  }

  async function getJson(path, options = {}) {
    const response = await fetch(path, withActionHeader(options));
    const text = await response.text();

    let payload;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`Endpoint returned non-JSON. Status ${response.status}. First text: ${text.slice(0, 120)}`);
    }

    if (!response.ok) {
      throw new Error(payload.error || `Request failed: ${response.status}`);
    }

    return payload;
  }

  function marketLabel(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function projectRootFromOutput(path) {
    const output = String(path || "");
    const relative = output.replaceAll("/", "\\");
    return `C:\\Users\\RevLe\\OneDrive\\Documents\\New project\\${relative}`;
  }

  function readableStatus(payload) {
    const lines = [
      "4. Model Readiness",
      "==================",
      "",
      "Use this after Run After Games to see which markets are ready for ML predictions.",
      "",
    ];

    for (const row of payload.markets || []) {
      const ready = row.canTrain ? "READY" : "NEEDS MORE DATA";
      lines.push(
        `${marketLabel(row.market)} ? ${ready}`,
        `Rows: ${row.trainingRows}`,
        `Results: ${JSON.stringify(row.classCounts || {})}`,
        ""
      );
    }

    lines.push(
      "Next:",
      "If a market says READY, use the Player Prop ML Predictions panel.",
      "Moneyline ML can be used after the moneyline model trains."
    );

    return lines.join("\n");
  }

  function readableBefore(payload) {
    const templatePath = payload.template?.output || "";
    const fullTemplatePath = projectRootFromOutput(templatePath);
    const notepadCommand = `notepad "${fullTemplatePath}"`;

    const autoRows = Number(payload.autofill?.updatedRows || 0);
    const moneylineRows = Number(payload.autofill?.rowsWithMoneyline || 0);
    const totalRows = Number(payload.autofill?.rowsWithTotal || 0);

    const reviewMessage = autoRows > 0
      ? "Odds were auto-saved from PropLine. Manual review is optional."
      : "No game odds were auto-filled. Review the template manually or check PropLine h2h/totals support.";

    return [
      "1. Before Games Complete",
      "========================",
      "",
      `Date: ${payload.date}`,
      "",
      "Completed:",
      `? Player props pulled: ${payload.props?.propCount ?? "--"}`,
      `? Games found: ${payload.template?.games ?? "--"}`,
      `? Game odds template created: ${payload.template?.rows ?? "--"} rows`,
      `? Auto-filled odds rows: ${autoRows}`,
      `? Rows with moneyline: ${moneylineRows}`,
      `? Rows with game total: ${totalRows}`,
      "",
      "2. Review Auto-Saved Odds",
      "=========================",
      reviewMessage,
      "",
      "Saved template file:",
      templatePath,
      "",
      "Optional review command:",
      notepadCommand,
      "",
      "Line movement note:",
      payload.autofill?.lineMovement?.note || "Current odds were saved. True open/close movement needs a historical line-movement source.",
      "",
      "3. Next Task",
      "============",
      "After games are final, click 3. Run After Games.",
    ].join("\n");
  }

  function summarizeMarketResult(item) {
    const stdout = String(item.stdout || "");
    const rows = stdout.match(/trainingRows:\s*(\d+)/)?.[1] || "--";
    const classes = stdout.match(/classCounts:\s*(\{.*?\})/)?.[1] || "{}";
    const trained = stdout.includes("Training model...") || item.trained;

    return [
      `${marketLabel(item.market)} ? ${trained ? "TRAINED / ATTEMPTED" : "NEEDS MORE DATA"}`,
      `  Rows: ${rows}`,
      `  Results: ${classes}`,
    ].join("\n");
  }

  function readableAfter(payload) {
    const lines = [
      "3. After Games Complete",
      "=======================",
      "",
      `Date: ${payload.date}`,
      "",
      "Completed:",
      `? Props read: ${payload.grade?.propsRead ?? "--"}`,
      `? Props graded: ${payload.grade?.rowsGraded ?? "--"}`,
      `? Props skipped: ${payload.grade?.rowsSkipped ?? "--"}`,
      `? Game odds matched rows: ${payload.merge?.matchedRows ?? "--"}`,
      `? Game odds unmatched rows: ${payload.merge?.unmatchedRows ?? "--"}`,
      "",
      "Player Prop Market Training",
      "===========================",
      "",
    ];

    for (const item of payload.playerPropMarkets || []) {
      lines.push(summarizeMarketResult(item), "");
    }

    lines.push(
      "Moneyline Training",
      "==================",
      payload.moneyline?.trained ? "? Moneyline model trained successfully." : "Moneyline model did not train.",
      "",
      "4. Next Task",
      "============",
      "Click 4. Check Models to see which ML markets are ready.",
      "",
      "5. Final Task",
      "=============",
      "Use Player Prop ML Predictions or Moneyline ML Predictions."
    );

    return lines.join("\n");
  }

  function readable(payload) {
    if (!payload) return "";
    if (payload.error) return `Workflow failed\n\n${payload.error}`;

    if (payload.markets) return readableStatus(payload);
    if (payload.step === "before") return readableBefore(payload);
    if (payload.step === "after") return readableAfter(payload);

    return JSON.stringify(payload, null, 2);
  }

  async function runBefore() {
    try {
      setStatus("Running step 1: before-games setup...");
      const payload = await getJson(`/api/daily-workflow/before?date=${encodeURIComponent(dateValue())}`, { method: "POST" });
      setStatus("Step 1 complete. Review step 2, then wait for games to finish.", payload);
    } catch (error) {
      console.error(error);
      setStatus(`Before-games setup failed: ${error.message}`, { error: error.message });
    }
  }

  async function runAfter() {
    try {
      setStatus("Running step 3: after-games update. This can take a little while...");
      const payload = await getJson(`/api/daily-workflow/after?date=${encodeURIComponent(dateValue())}`, { method: "POST" });
      setStatus("Step 3 complete. Next: click Check Models.", payload);
    } catch (error) {
      console.error(error);
      setStatus(`After-games update failed: ${error.message}`, { error: error.message });
    }
  }

  async function runStatus() {
    try {
      setStatus("Running step 4: checking model readiness...");
      const payload = await getJson("/api/daily-workflow/status");
      setStatus("Step 4 complete. Ready markets can now be used for predictions.", payload);
    } catch (error) {
      console.error(error);
      setStatus(`Status check failed: ${error.message}`, { error: error.message });
    }
  }

  function init() {
    if (!els.before) return;

    if (els.date && !els.date.value) {
      els.date.value = todayDateString();
    }

    els.before.addEventListener("click", runBefore);
    els.after?.addEventListener("click", runAfter);
    els.statusButton?.addEventListener("click", runStatus);

    if (els.output) {
      els.output.textContent = [
        "Daily ML Task Order",
        "===================",
        "",
        "1. Click 1. Run Before Games",
        "   Pulls props, creates game odds template, and auto-saves PropLine game odds.",
        "",
        "2. Review Auto-Saved Odds",
        "   Only needed if the output says rows are missing.",
        "",
        "3. Click 3. Run After Games",
        "   Grades props, merges game odds, prepares training files, and trains ready models.",
        "",
        "4. Click 4. Check Models",
        "   Shows which markets are ready.",
        "",
        "5. Use Predictions",
        "   Use Player Prop ML Predictions and Moneyline ML Predictions.",
      ].join("\n");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
