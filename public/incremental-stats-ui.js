(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    season: $("#incrementalStatsSeason"),
    endDate: $("#incrementalStatsEndDate"),
    phase: $("#incrementalStatsPhase"),
    catchup: $("#incrementalStatsCatchupButton"),
    statusButton: $("#incrementalStatsStatusButton"),
    features: $("#incrementalFeaturesBuildButton"),
    crossPlayer: $("#incrementalCrossPlayer"),
    crossKind: $("#incrementalCrossKind"),
    crossButton: $("#incrementalCrossButton"),
    status: $("#incrementalStatsStatus"),
    output: $("#incrementalStatsOutput"),
  };

  function today() {
    return new Date().toISOString().slice(0, 10);
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
      throw new Error(payload.error || `Request failed ${response.status}`);
    }

    return payload;
  }

  function readable(payload) {
    if (!payload || payload.error) {
      return `Incremental Stats failed\n\n${payload?.error || "Unknown error"}`;
    }

    const rows = payload.rowCounts || {};

    return [
      "Incremental Stats Warehouse",
      "===========================",
      "",
      `Season: ${payload.season || "--"}`,
      `Range: ${payload.startDate || "--"} to ${payload.endDate || "--"}`,
      `Updated at: ${payload.updatedAt || "--"}`,
      `Regular season start: ${payload.regularSeasonStart || "--"}`,
      `Collection mode: ${payload.seasonPhase || "--"}`,
      "",
      "Run Summary",
      "-----------",
      `Games seen: ${payload.gamesSeen ?? "--"}`,
      `Final games seen: ${payload.finalGamesSeen ?? "--"}`,
      `Skipped already-cached final games: ${payload.skippedFinalCached ?? "--"}`,
      `Boxscores read: ${payload.boxscoresRead ?? "--"}`,
      `Live feeds read for BvP: ${payload.liveFeedsRead ?? "--"}`,
      `Errors: ${payload.errorCount ?? 0}`,
      `Regular games cached: ${payload.phaseBreakdown?.regular ?? "--"}`,
      `Practice games cached: ${payload.phaseBreakdown?.practice ?? "--"}`,
      "",
      "Stored Rows",
      "-----------",
      `Games: ${rows.games ?? "--"}`,
      `Batter logs: ${rows.batters ?? "--"}`,
      `Pitcher logs: ${rows.pitchers ?? "--"}`,
      `Team logs: ${rows.teams ?? "--"}`,
      `Batter-vs-pitcher PA: ${rows.bvp ?? "--"}`,
      `Player index: ${rows.players ?? "--"}`,
      `Team index: ${rows.teamIndex ?? "--"}`,
      "",
      "Files",
      "-----",
      payload.files ? Object.entries(payload.files).map(([k, v]) => `${k}: ${v}`).join("\n") : "--",
      "",
      "Raw JSON",
      "--------",
      JSON.stringify(payload, null, 2),
    ].join("\n");
  }

  async function catchup() {
    try {
      const season = els.season?.value || "2026";
      const endDate = els.endDate?.value || today();

      if (els.status) {
        els.status.textContent = `Catching up ${season} stats through ${endDate}. This can take a bit on first run...`;
      }

      const phase = els.phase?.value || "regular";
      const startDate = phase === "regular" && season === "2026" ? "2026-03-25" : `${season}-03-01`;

      const payload = await getJson(
        `/api/incremental-stats/catchup?season=${encodeURIComponent(season)}&start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}&season_phase=${encodeURIComponent(phase)}`,
        { method: "POST" }
      );

      if (els.status) {
        els.status.textContent = `Stats catch-up complete. Batter logs: ${payload.rowCounts?.batters ?? 0}, Pitcher logs: ${payload.rowCounts?.pitchers ?? 0}, BvP rows: ${payload.rowCounts?.bvp ?? 0}.`;
      }

      if (els.output) els.output.textContent = readable(payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Stats catch-up failed: ${error.message}`;
      if (els.output) els.output.textContent = `Stats catch-up failed\n\n${error.message}`;
    }
  }

  async function status() {
    try {
      const season = els.season?.value || "2026";
      const payload = await getJson(`/api/incremental-stats/status?season=${encodeURIComponent(season)}`);

      if (els.status) {
        els.status.textContent = `Stats warehouse loaded. BvP rows: ${payload.rowCounts?.bvp ?? 0}.`;
      }

      if (els.output) els.output.textContent = readable(payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Stats status failed: ${error.message}`;
      if (els.output) els.output.textContent = `Stats status failed\n\n${error.message}`;
    }
  }


  async function buildFeatures() {
    try {
      const season = els.season?.value || "2026";
      const phase = els.phase?.value || "regular";

      if (els.status) {
        els.status.textContent = `Building aggregate feature files for ${season} ${phase} games...`;
      }

      const payload = await getJson(`/api/incremental-features/build?season=${encodeURIComponent(season)}&phase=${encodeURIComponent(phase)}`, { method: "POST" });

      if (els.status) {
        els.status.textContent = `Feature build complete. Batter totals: ${payload.outputRows?.batterTotals ?? 0}, Pitcher totals: ${payload.outputRows?.pitcherTotals ?? 0}.`;
      }

      if (els.output) {
        els.output.textContent = [
          "Aggregate Feature Build",
          "=======================",
          "",
          `Season: ${payload.season}`,
          `Phase: ${payload.phase}`,
          `Regular season start: ${payload.regularSeasonStart}`,
          "",
          "Input Rows",
          "----------",
          `Batter logs: ${payload.inputRows?.batters ?? 0}`,
          `Pitcher logs: ${payload.inputRows?.pitchers ?? 0}`,
          `Team logs: ${payload.inputRows?.teams ?? 0}`,
          `BvP rows: ${payload.inputRows?.bvp ?? 0}`,
          "",
          "Output Rows",
          "-----------",
          `Batter totals: ${payload.outputRows?.batterTotals ?? 0}`,
          `Pitcher totals: ${payload.outputRows?.pitcherTotals ?? 0}`,
          `Team totals: ${payload.outputRows?.teamTotals ?? 0}`,
          `BvP totals: ${payload.outputRows?.bvpTotals ?? 0}`,
          `Batter recent: ${payload.outputRows?.batterRecent ?? 0}`,
          `Pitcher recent: ${payload.outputRows?.pitcherRecent ?? 0}`,
          "",
          "Files",
          "-----",
          payload.files ? Object.entries(payload.files).map(([k, v]) => `${k}: ${v}`).join("\\n") : "--",
          "",
          "Raw JSON",
          "--------",
          JSON.stringify(payload, null, 2),
        ].join("\\n");
      }
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Feature build failed: ${error.message}`;
      if (els.output) els.output.textContent = `Feature build failed\\n\\n${error.message}`;
    }
  }

  async function crossReference() {
    try {
      const season = els.season?.value || "2026";
      const player = els.crossPlayer?.value || "";
      const kind = els.crossKind?.value || "batter";

      if (!player) {
        throw new Error("Enter a player name to cross-check.");
      }

      if (els.status) {
        els.status.textContent = `Cross-referencing ${player} with MLB StatsAPI...`;
      }

      const payload = await getJson(`/api/incremental-features/cross-reference?season=${encodeURIComponent(season)}&kind=${encodeURIComponent(kind)}&player=${encodeURIComponent(player)}`, { method: "POST" });

      if (els.status) {
        els.status.textContent = payload.foundLocal
          ? `Cross-reference complete for ${payload.player}.`
          : `Cross-reference failed: ${payload.error}`;
      }

      if (els.output) {
        els.output.textContent = [
          "MLB API Cross-Reference",
          "=======================",
          "",
          `Player: ${payload.player || player}`,
          `Kind: ${payload.kind || kind}`,
          `Found local: ${payload.foundLocal}`,
          "",
          "Comparisons",
          "-----------",
          payload.comparisons
            ? Object.entries(payload.comparisons).map(([name, row]) => `${name}: local=${row.local}, mlbApi=${row.mlbApi}, diff=${row.difference}`).join("\\n")
            : payload.error || "--",
          "",
          "Note",
          "----",
          payload.note || "No note.",
          "",
          "Raw JSON",
          "--------",
          JSON.stringify(payload, null, 2),
        ].join("\\n");
      }
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Cross-reference failed: ${error.message}`;
      if (els.output) els.output.textContent = `Cross-reference failed\\n\\n${error.message}`;
    }
  }


  function init() {
    if (!els.catchup) return;
    if (els.endDate && !els.endDate.value) els.endDate.value = today();

    els.catchup.addEventListener("click", catchup);
    els.statusButton?.addEventListener("click", status);
    els.features?.addEventListener("click", buildFeatures);
    els.crossButton?.addEventListener("click", crossReference);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
