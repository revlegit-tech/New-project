(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    season: $("#unifiedSeason"),
    date: $("#unifiedDate"),
    market: $("#unifiedMarket"),
    player: $("#unifiedPlayer"),
    team: $("#unifiedTeam"),
    opponent: $("#unifiedOpponent"),
    pitcher: $("#unifiedPitcher"),
    line: $("#unifiedLine"),
    odds: $("#unifiedOdds"),
    backfill: $("#unifiedBackfillButton"),
    statusButton: $("#unifiedStatusButton"),
    predict: $("#unifiedPredictButton"),
    finalProbability: $("#unifiedFinalProbability"),
    implied: $("#unifiedImplied"),
    edge: $("#unifiedEdge"),
    confidence: $("#unifiedConfidence"),
    status: $("#unifiedStatus"),
    output: $("#unifiedOutput"),
  };

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function pct(value) {
    return `${Number(value || 0).toFixed(2)}%`;
  }

  function signedPct(value) {
    const number = Number(value || 0);
    return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
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

  function params() {
    const query = new URLSearchParams();
    query.set("season", els.season?.value || "2026");
    query.set("date", els.date?.value || today());
    query.set("market", els.market?.value || "batter_hits");
    query.set("player", els.player?.value || "");
    query.set("team", els.team?.value || "");
    query.set("opponent", els.opponent?.value || "");
    query.set("pitcher", els.pitcher?.value || "");
    query.set("line", els.line?.value || "0.5");
    query.set("american_odds", els.odds?.value || "-110");
    return query;
  }

  function readable(payload) {
    if (!payload || payload.error) {
      return `Unified Prop Card failed\n\n${payload?.error || "Unknown error"}`;
    }

    const cached = payload.cachedContexts || {};

    return [
      "Unified Prop Card",
      "=================",
      "",
      `Pick: ${payload.player || "--"} ${payload.market || "--"} over ${payload.line}`,
      `Matchup: ${payload.team || "--"} vs ${payload.opponent || "--"}`,
      `Pitcher: ${payload.pitcher || "--"}`,
      "",
      "Final Result",
      "------------",
      `Final probability: ${pct(payload.finalProbabilityPercent)}`,
      `All Data probability: ${pct(payload.allDataProbabilityPercent)}`,
      `Cached stat adjustment: ${signedPct(payload.cachedStatsAdjustmentPercent)}`,
      `Weather adjustment: ${signedPct(payload.weatherAdjustmentPercent)}`,
      `Odds movement adjustment: ${signedPct(payload.oddsMovementAdjustmentPercent)}`,
      `Savant adjustment: ${signedPct(payload.savantAdjustmentPercent)}`,
      `Sportsbook implied: ${pct(payload.sportsbookImpliedPercent)}`,
      `Final edge: ${signedPct(payload.finalEdgePercent)}`,
      `Confidence: ${payload.confidence}`,
      `Recommendation: ${payload.recommendation}`,
      "",
      "Baseball Savant",
      "---------------",
      `Batter batted balls: ${payload.savantContext?.batter?.battedBalls || "--"}`,
      `Batter avg EV: ${payload.savantContext?.batter?.avgExitVelocity || "--"}`,
      `Batter barrel rate: ${payload.savantContext?.batter?.barrelRate || "--"}%`,
      `Batter hard-hit rate: ${payload.savantContext?.batter?.hardHitRate || "--"}%`,
      `Pitcher whiff rate: ${payload.savantContext?.pitcher?.whiffRate || "--"}%`,
      `Pitcher xwOBA allowed: ${payload.savantContext?.pitcher?.avgXWOBAAllowed || "--"}`,
      "",
      "Odds Movement",
      "-------------",
      `Snapshots: ${payload.oddsMovementContext?.snapshots || "--"}`,
      `First odds: ${payload.oddsMovementContext?.firstAmericanOdds || "--"}`,
      `Latest odds: ${payload.oddsMovementContext?.latestAmericanOdds || "--"}`,
      `Implied move: ${payload.oddsMovementContext?.impliedProbabilityMove || "--"}`,
      `Summary: ${payload.oddsMovementContext?.movementSummary || "--"}`,
      "",
      "Weather Context",
      "---------------",
      `Venue: ${payload.weatherContext?.venue || "--"}`,
      `Temp: ${payload.weatherContext?.temperatureF || "--"}?F`,
      `Wind: ${payload.weatherContext?.windMph || "--"} mph`,
      `Rain risk: ${payload.weatherContext?.precipitationProbability || "--"}%`,
      `Weather summary: ${payload.weatherContext?.weatherSummary || "--"}`,
      "",
      "Cached 2026 Context",
      "-------------------",
      `Batter games: ${cached.batter?.games ?? "--"}`,
      `Batter H/G: ${cached.batter?.hitsPerGame ?? "--"}`,
      `Batter TB/G: ${cached.batter?.totalBasesPerGame ?? "--"}`,
      `Pitcher games: ${cached.pitcher?.games ?? "--"}`,
      `Pitcher K/G: ${cached.pitcher?.strikeoutsPerGame ?? "--"}`,
      `Team runs/G: ${cached.team?.runsPerGame ?? "--"}`,
      `Opponent runs allowed/G: ${cached.opponent?.runsAllowedPerGame ?? "--"}`,
      "",
      "Cached Adjustments",
      "------------------",
      payload.cachedAdjustments?.length
        ? payload.cachedAdjustments.map((x) => `${x.name}: ${signedPct(x.amountPercent)} ? ${x.reason}`).join("\n")
        : "No cached stat adjustments applied",
      "",
      "Data Used",
      "---------",
      payload.dataUsed?.length ? payload.dataUsed.map((x) => `? ${x}`).join("\n") : "None",
      "",
      "Missing Data",
      "------------",
      payload.missingData?.length ? payload.missingData.map((x) => `- ${x}`).join("\n") : "None",
      "",
      "Raw JSON",
      "--------",
      JSON.stringify(payload, null, 2),
    ].join("\n");
  }

  function setOutput(message, payload) {
    if (els.status) els.status.textContent = message;
    if (els.output) els.output.textContent = typeof payload === "string" ? payload : readable(payload);
  }

  async function backfill() {
    try {
      const season = els.season?.value || "2026";
      const endDate = els.date?.value || today();

      if (els.status) {
        els.status.textContent = `Backfilling ${season} played games through ${endDate}. This can take a bit...`;
      }

      const payload = await getJson(`/api/season-cache/backfill?season=${encodeURIComponent(season)}&start_date=${season}-03-01&end_date=${encodeURIComponent(endDate)}`, { method: "POST" });

      if (els.status) {
        els.status.textContent = `Backfill complete. Batter rows: ${payload.batterRowsUpserted}, Pitcher rows: ${payload.pitcherRowsUpserted}.`;
      }

      if (els.output) {
        els.output.textContent = [
          "Season Cache Backfill",
          "=====================",
          "",
          `Season: ${payload.season}`,
          `Date range: ${payload.startDate} to ${payload.endDate}`,
          `Games found: ${payload.gamesFound}`,
          `Final games: ${payload.finalGames}`,
          `Boxscores fetched/read: ${payload.boxscoresFetched}`,
          `Batter rows upserted: ${payload.batterRowsUpserted}`,
          `Pitcher rows upserted: ${payload.pitcherRowsUpserted}`,
          `Team rows upserted: ${payload.teamRowsUpserted}`,
          `Players indexed: ${payload.indexes?.players ?? "--"}`,
          `Teams indexed: ${payload.indexes?.teams ?? "--"}`,
          "",
          "Raw JSON",
          "--------",
          JSON.stringify(payload, null, 2),
        ].join("\n");
      }
    } catch (error) {
      console.error(error);
      setOutput(`Backfill failed: ${error.message}`, { error: error.message });
    }
  }

  async function cacheStatus() {
    try {
      const season = els.season?.value || "2026";
      const payload = await getJson(`/api/season-cache/status?season=${encodeURIComponent(season)}`);

      if (els.status) {
        els.status.textContent = `Cache loaded. Players indexed: ${payload.rowCounts?.players ?? 0}`;
      }

      if (els.output) {
        els.output.textContent = [
          "Season Cache Status",
          "===================",
          "",
          `Season: ${payload.season || season}`,
          `Games: ${payload.rowCounts?.games ?? 0}`,
          `Batter rows: ${payload.rowCounts?.batters ?? 0}`,
          `Pitcher rows: ${payload.rowCounts?.pitchers ?? 0}`,
          `Team rows: ${payload.rowCounts?.teams ?? 0}`,
          `Player index rows: ${payload.rowCounts?.players ?? 0}`,
          `Team index rows: ${payload.rowCounts?.teamIndex ?? 0}`,
          `Updated at: ${payload.updatedAt || "--"}`,
          "",
          "Raw JSON",
          "--------",
          JSON.stringify(payload, null, 2),
        ].join("\n");
      }
    } catch (error) {
      console.error(error);
      setOutput(`Cache status failed: ${error.message}`, { error: error.message });
    }
  }

  async function predict() {
    try {
      if (els.status) els.status.textContent = "Running Unified Prop Card...";
      const payload = await getJson(`/api/unified-prop-card/predict?${params().toString()}`);

      if (els.finalProbability) els.finalProbability.textContent = pct(payload.finalProbabilityPercent);
      if (els.implied) els.implied.textContent = pct(payload.sportsbookImpliedPercent);
      if (els.edge) els.edge.textContent = signedPct(payload.finalEdgePercent);
      if (els.confidence) els.confidence.textContent = payload.confidence;

      window.BaseballResultCards?.decorateMetric(els.edge, payload.finalEdgePercent);
      window.BaseballResultCards?.decorateMetric(els.confidence, payload.confidence, "confidence");
      window.BaseballResultCards?.render(els.output, {
        title: `${payload.player || "--"} ${payload.market || "prop"} over ${payload.line ?? "--"}`,
        subtitle: `${payload.team || "--"} vs ${payload.opponent || "--"}${payload.pitcher ? ` · Pitcher: ${payload.pitcher}` : ""}`,
        probabilityPercent: payload.finalProbabilityPercent,
        impliedPercent: payload.sportsbookImpliedPercent,
        edgePercent: payload.finalEdgePercent,
        fairOdds: payload.fairOdds,
        confidence: payload.confidence,
        recommendation: payload.recommendation,
        notes: [
          `All Data probability: ${pct(payload.allDataProbabilityPercent)}`,
          `Weather adj: ${signedPct(payload.weatherAdjustmentPercent)}`,
          `Odds movement adj: ${signedPct(payload.oddsMovementAdjustmentPercent)}`,
        ],
      });

      setOutput("Unified Prop Card complete. Raw details are collapsed below.", payload);
    } catch (error) {
      console.error(error);
      setOutput(`Unified Prop Card failed: ${error.message}`, { error: error.message });
    }
  }

  function setDefaultLine() {
    const defaults = {
      batter_hits: "0.5",
      batter_total_bases: "1.5",
      batter_home_runs: "0.5",
      pitcher_strikeouts: "4.5",
      pitcher_hits_allowed: "4.5",
      pitcher_earned_runs: "2.5",
    };

    if (els.line) els.line.value = defaults[els.market?.value] || "0.5";
  }

  function attachLookup(input, kind) {
    if (!input || input.dataset.unifiedLookup === "1") return;
    input.dataset.unifiedLookup = "1";

    const wrap = input.closest("label");
    if (wrap) wrap.classList.add("propml-autocomplete-wrap");

    const box = document.createElement("div");
    box.className = "propml-autocomplete-results hidden";
    input.insertAdjacentElement("afterend", box);

    async function search() {
      const season = els.season?.value || "2026";
      const q = input.value || "";

      if (!q) {
        box.innerHTML = '<div class="propml-autocomplete-empty">Start typing to search cached data</div>';
        box.classList.remove("hidden");
        return;
      }

      const payload = await getJson(`/api/incremental-stats/lookup?season=${encodeURIComponent(season)}&kind=${encodeURIComponent(kind)}&q=${encodeURIComponent(q)}&limit=12`);
      const results = payload.results || [];

      box.innerHTML = "";

      if (!results.length) {
        box.innerHTML = '<div class="propml-autocomplete-empty">No cached matches. Run backfill first.</div>';
        box.classList.remove("hidden");
        return;
      }

      results.forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "propml-autocomplete-item";
        button.innerHTML = `<strong>${item.name || item.team}</strong><span>${item.team || item.role || ""}</span>`;

        button.addEventListener("mousedown", (event) => {
          event.preventDefault();

          if (item.type === "team") {
            input.value = item.team || "";
          } else {
            input.value = item.name || "";
            if (input === els.player && els.team && !els.team.value && item.team) {
              els.team.value = item.team;
            }
          }

          box.classList.add("hidden");
        });

        box.appendChild(button);
      });

      box.classList.remove("hidden");
    }

    input.addEventListener("focus", search);
    input.addEventListener("input", search);

    document.addEventListener("mousedown", (event) => {
      if (!box.contains(event.target) && event.target !== input) {
        box.classList.add("hidden");
      }
    });
  }

  function init() {
    if (!els.predict) return;

    if (els.date && !els.date.value) els.date.value = today();

    els.market?.addEventListener("change", setDefaultLine);
    els.backfill?.addEventListener("click", backfill);
    els.statusButton?.addEventListener("click", cacheStatus);
    els.predict.addEventListener("click", predict);

    attachLookup(els.player, "player");
    attachLookup(els.pitcher, "pitcher");
    attachLookup(els.team, "team");
    attachLookup(els.opponent, "team");

    setDefaultLine();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
