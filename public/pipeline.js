(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    date: $("#pipelineDate"),
    pullProps: $("#pipelinePullPropsButton"),
    createTemplate: $("#pipelineCreateTemplateButton"),
    grade: $("#pipelineGradeButton"),
    merge: $("#pipelineMergeButton"),
    prepare: $("#pipelinePrepareButton"),
    train: $("#pipelineTrainButton"),
    runAll: $("#pipelineRunAllButton"),
    status: $("#pipelineStatus"),
    output: $("#pipelineOutput"),
  };

  function todayDateString() {
    return new Date().toISOString().slice(0, 10);
  }

  function pipelineDate() {
    return els.date?.value || todayDateString();
  }

  function readableValue(value) {
    if (value === null || value === undefined || value === "") return "--";
    return String(value);
  }

  function readableMetrics(metrics) {
    if (!metrics || typeof metrics !== "object") return [];
    const lines = ["Model metrics", "-------------"];

    for (const [name, values] of Object.entries(metrics)) {
      lines.push(
        `${name}: AUC ${Number(values.auc || 0).toFixed(3)}, Brier ${Number(values.brier || 0).toFixed(3)}, Score ${Number(values.score || 0).toFixed(3)}`
      );
    }

    return lines;
  }

  function pipelineReadable(payload) {
    if (!payload) return "";
    if (payload.error) return `Pipeline step failed\n\n${payload.error}`;

    const lines = ["Pipeline Result", "===============", ""];

    if (payload.date) lines.push(`Date: ${payload.date}`);
    if (payload.output) lines.push(`Output file: ${payload.output}`);
    if (payload.savedPath) lines.push(`Saved file: ${payload.savedPath}`);
    if (payload.modelPath) lines.push(`Model file: ${payload.modelPath}`);
    if (payload.bestModel) lines.push(`Best model: ${payload.bestModel}`);

    const summaryFields = [
      ["Games", payload.games],
      ["Rows", payload.rows],
      ["Input rows", payload.inputRows],
      ["Training rows", payload.trainingRows],
      ["Props read", payload.propsRead],
      ["Rows graded", payload.rowsGraded],
      ["Rows skipped", payload.rowsSkipped],
      ["Prop rows", payload.propRows],
      ["Game odds rows", payload.gameOddsRows],
      ["Matched rows", payload.matchedRows],
      ["Unmatched rows", payload.unmatchedRows],
      ["Teams covered", payload.teamsCovered],
      ["Opponents covered", payload.opponentsCovered],
      ["Event count", payload.eventCount],
      ["Prop count", payload.propCount],
    ];

    const presentSummary = summaryFields.filter(([, value]) => value !== undefined);
    if (presentSummary.length) {
      lines.push("", "Summary", "-------");
      for (const [label, value] of presentSummary) {
        lines.push(`${label}: ${readableValue(value)}`);
      }
    }

    if (payload.classCounts) {
      lines.push("", "Class counts", "------------");
      for (const [label, value] of Object.entries(payload.classCounts)) {
        lines.push(`${label}: ${value}`);
      }
    }

    if (payload.metrics) {
      lines.push("", ...readableMetrics(payload.metrics));
    }

    if (payload.grade || payload.merge || payload.prepare || payload.train) {
      lines.push("", "Full pipeline steps", "-------------------");

      if (payload.grade) {
        lines.push(
          `Grade: ${payload.grade.rowsGraded ?? "--"} graded, ${payload.grade.rowsSkipped ?? "--"} skipped`
        );
      }

      if (payload.merge) {
        lines.push(
          `Merge: ${payload.merge.matchedRows ?? "--"} matched, ${payload.merge.unmatchedRows ?? "--"} unmatched`
        );
      }

      if (payload.prepare) {
        lines.push(
          `Prepare: ${payload.prepare.trainingRows ?? "--"} training rows`
        );
      }

      if (payload.train) {
        lines.push(
          `Train: ${payload.train.bestModel ?? "--"} saved to ${payload.train.modelPath ?? "--"}`
        );
      }
    }

    lines.push("", "Raw JSON", "--------", JSON.stringify(payload, null, 2));
    return lines.join("\n");
  }

  function setStatus(message, payload) {
    if (els.status) {
      els.status.textContent = message;
    }

    if (els.output && payload !== undefined) {
      els.output.textContent = pipelineReadable(payload);
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

  async function api(path, options = {}) {
    const response = await fetch(path, withActionHeader(options));
    const text = await response.text();

    let payload;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      payload = { error: `Endpoint returned non-JSON. Status ${response.status}. First text: ${text.slice(0, 80)}` };
    }

    if (!response.ok) {
      throw new Error(payload.error || payload.message || `Request failed: ${response.status}`);
    }

    return payload;
  }

  async function runStep(label, path, options = { method: "POST" }) {
    try {
      setStatus(`${label} running...`);
      const payload = await api(path, options);
      setStatus(`${label} complete.`, payload);
      return payload;
    } catch (error) {
      console.error(`${label} failed`, error);
      setStatus(`${label} failed: ${error.message}`, { error: error.message });
      throw error;
    }
  }

  function bind(button, handler) {
    if (!button) return;
    button.addEventListener("click", handler);
  }

  function initPipelineUi() {
    if (!els.date) {
      return;
    }

    if (!els.date.value) {
      els.date.value = todayDateString();
    }

    bind(els.pullProps, () => {
      const date = pipelineDate();
      return runStep(
        "Pull all supported props",
        `/api/propline/props?markets=pitcher_strikeouts,batter_hits,batter_total_bases,batter_home_runs,batter_rbis,batter_stolen_bases,batter_walks,batter_singles,batter_doubles,batter_runs,batter_2plus_hits,batter_2plus_home_runs,batter_2plus_rbis,batter_3plus_rbis,pitcher_outs,pitcher_hits_allowed,pitcher_earned_runs&date=${encodeURIComponent(date)}`
      );
    });

    bind(els.createTemplate, () => {
      const date = pipelineDate();
      return runStep(
        "Create game odds template",
        `/api/pipeline/create-template?date=${encodeURIComponent(date)}`
      );
    });

    bind(els.grade, () => {
      const date = pipelineDate();
      return runStep(
        "Grade props",
        `/api/pipeline/grade?date=${encodeURIComponent(date)}`
      );
    });

    bind(els.merge, () => {
      const date = pipelineDate();
      return runStep(
        "Merge game odds",
        `/api/pipeline/merge-game-odds?date=${encodeURIComponent(date)}`
      );
    });

    bind(els.prepare, () => {
      return runStep(
        "Prepare strikeout training",
        "/api/pipeline/prepare-strikeouts"
      );
    });

    bind(els.train, () => {
      return runStep(
        "Train strikeout ML",
        "/api/pipeline/train-strikeouts"
      );
    });

    bind(els.runAll, () => {
      const date = pipelineDate();
      return runStep(
        "Full after-game pipeline",
        `/api/pipeline/run-after-game?date=${encodeURIComponent(date)}`
      );
    });

    setStatus("Pipeline UI ready. Before games: pull props and create template. After games: run grading/training steps.");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPipelineUi);
  } else {
    initPipelineUi();
  }
})();
