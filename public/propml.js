(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    market: $("#propMlMarket"),
    player: $("#propMlPlayer"),
    team: $("#propMlTeam"),
    opponent: $("#propMlOpponent"),
    pitcher: $("#propMlPitcher"),
    line: $("#propMlLine"),
    odds: $("#propMlOdds"),
    recentRate: $("#propMlRecentRate"),
    seasonRate: $("#propMlSeasonRate"),
    opponentRate: $("#propMlOpponentRate"),
    parkFactor: $("#propMlParkFactor"),
    button: $("#propMlPredictButton"),
    probability: $("#propMlProbability"),
    implied: $("#propMlImplied"),
    edge: $("#propMlEdge"),
    fairOdds: $("#propMlFairOdds"),
    status: $("#propMlStatus"),
    output: $("#propMlOutput"),
    trainingStatus: $("#propMlTrainingStatus"),
  };

  let marketStatus = {};

  function pct(value) {
    return `${Number(value || 0).toFixed(2)}%`;
  }

  function signedPct(value) {
    const number = Number(value || 0);
    return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
  }

  function american(value) {
    const number = Number(value || 0);
    return `${number > 0 ? "+" : ""}${Math.round(number)}`;
  }

  function marketLabel(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function currentMarketInfo(market) {
    return marketStatus[market] || null;
  }

  function confidenceWarning(payload) {
    const info = currentMarketInfo(payload.market);
    const warnings = [];

    if (!payload.player) warnings.push("player is blank");
    if (!payload.team) warnings.push("team is blank");
    if (!payload.opponent) warnings.push("opponent is blank");

    if (!info || !info.canTrain) {
      warnings.push("market-specific training data is not ready");
    }

    if (Number(payload.probabilityPercent || 0) < 5 || Number(payload.probabilityPercent || 0) > 95) {
      warnings.push("model output is extreme, which can happen with weak/imbalanced training data");
    }

    if (!warnings.length) {
      return "Model confidence: usable, but still compare against your data and market context.";
    }

    return `Model confidence: LOW. Warning: ${warnings.join("; ")}.`;
  }

  function readable(payload) {
    if (!payload || payload.error) {
      return `Player Prop ML failed\n\n${payload?.error || "Unknown error"}`;
    }

    const info = currentMarketInfo(payload.market);

    return [
      "Player Prop ML Result",
      "=====================",
      "",
      confidenceWarning(payload),
      "",
      "Market training status",
      "----------------------",
      `Market: ${marketLabel(payload.market)}`,
      `Training rows: ${info?.trainingRows ?? "unknown"}`,
      `Class counts: ${JSON.stringify(info?.classCounts || {})}`,
      `Can train: ${info?.canTrain ? "yes" : "no"}`,
      "",
      `Player: ${payload.player || "--"}`,
      `Team: ${payload.team || "--"}`,
      `Opponent: ${payload.opponent || "--"}`,
      `Pitcher: ${payload.pitcher || "--"}`,
      "",
      "Sportsbook",
      "-----------",
      `Line: ${payload.line}`,
      `American odds: ${american(payload.americanOdds)}`,
      `Sportsbook implied probability: ${pct(payload.impliedProbabilityPercent)}`,
      "",
      "Model",
      "-----",
      `Model probability: ${pct(payload.probabilityPercent)}`,
      `Model edge: ${signedPct(payload.edgePercent)}`,
      `Fair odds: ${american(payload.fairOdds)}`,
      `Expected value per unit: ${signedPct(payload.expectedValuePercent)}`,
      `Recommendation: ${payload.recommendation || "--"}`,
      `Model version: ${payload.modelVersion || "--"}`,
      "",
      "Raw JSON",
      "--------",
      JSON.stringify(payload, null, 2),
    ].join("\n");
  }

  function trainingStatusReadable(payload) {
    if (!payload || payload.error) {
      return `Training status unavailable\n\n${payload?.error || "Unknown error"}`;
    }

    const lines = [
      "Player Prop ML Training Status",
      "==============================",
      "",
    ];

    for (const row of payload.markets || []) {
      lines.push(
        `${marketLabel(row.market)}: ${row.status}`,
        `  rows: ${row.trainingRows}`,
        `  classes: ${JSON.stringify(row.classCounts || {})}`,
        `  can train: ${row.canTrain ? "yes" : "no"}`,
        ""
      );
    }

    return lines.join("\n");
  }

  async function loadTrainingStatus() {
    if (!els.trainingStatus) return;

    try {
      const response = await fetch("/api/prop-ml/status");
      const payload = await response.json();

      marketStatus = {};
      for (const row of payload.markets || []) {
        marketStatus[row.market] = row;
      }

      els.trainingStatus.textContent = trainingStatusReadable(payload);
    } catch (error) {
      els.trainingStatus.textContent = `Training status unavailable\n\n${error.message}`;
    }
  }

  function params() {
    const query = new URLSearchParams();
    query.set("market", els.market?.value || "pitcher_strikeouts");
    query.set("player", els.player?.value || "");
    query.set("team", els.team?.value || "");
    query.set("opponent", els.opponent?.value || "");
    query.set("pitcher", els.pitcher?.value || "");
    query.set("line", els.line?.value || "0.5");
    query.set("american_odds", els.odds?.value || "-110");
    query.set("recent_rate", els.recentRate?.value || "0");
    query.set("season_rate", els.seasonRate?.value || "0");
    query.set("opponent_rate", els.opponentRate?.value || "0");
    query.set("park_factor", els.parkFactor?.value || "1");
    return query;
  }

  function setStatus(message, payload) {
    if (els.status) els.status.textContent = message;
    if (els.output && payload !== undefined) {
      els.output.textContent = readable(payload);
    }
  }

  async function predictPropMl() {
    try {
      await loadTrainingStatus();
      await window.ModelCardsStore?.load?.();

      setStatus("Running player prop ML prediction...");
      const response = await fetch(`/api/prop-ml/predict?${params().toString()}`);
      const text = await response.text();

      let payload;
      try {
        payload = text ? JSON.parse(text) : {};
      } catch {
        throw new Error(`Prop ML endpoint returned non-JSON. Status ${response.status}. First text: ${text.slice(0, 80)}`);
      }

      if (!response.ok) {
        throw new Error(payload.error || "Player prop ML prediction failed.");
      }

      if (els.probability) els.probability.textContent = pct(payload.probabilityPercent);
      if (els.implied) els.implied.textContent = pct(payload.impliedProbabilityPercent);
      if (els.edge) els.edge.textContent = signedPct(payload.edgePercent);
      if (els.fairOdds) els.fairOdds.textContent = american(payload.fairOdds);

      window.BaseballResultCards?.decorateMetric(els.edge, payload.edgePercent);
      const modelCard = window.ModelCardsStore?.get?.(payload.market);
      const safeDecision = window.ModelCardsStore?.decisionLabelFor?.(modelCard, payload.recommendation, payload.edgePercent) || payload.recommendation;

      window.BaseballResultCards?.render(els.output, {
        market: payload.market,
        modelCard,
        title: `${payload.player || "--"} ${marketLabel(payload.market)} over ${payload.line ?? "--"}`,
        subtitle: `${payload.team || "--"} vs ${payload.opponent || "--"}${payload.pitcher ? ` · Pitcher: ${payload.pitcher}` : ""}`,
        probabilityPercent: payload.probabilityPercent,
        impliedPercent: payload.impliedProbabilityPercent,
        edgePercent: payload.edgePercent,
        fairOdds: payload.fairOdds,
        confidence: confidenceWarning(payload).includes("LOW") ? "Low" : "Medium",
        recommendation: safeDecision,
        notes: [
          `Expected value: ${signedPct(payload.expectedValuePercent)}`,
          `Model version: ${payload.modelVersion || "--"}`,
          `Readiness: ${modelCard?.readinessLabel || "Research only"}`,
        ],
        reasons: [
          `Model probability is ${pct(payload.probabilityPercent)} versus book implied ${pct(payload.impliedProbabilityPercent)}.`,
          `Estimated edge is ${signedPct(payload.edgePercent)} after current inputs.`,
          modelCard?.latestGradedDate ? `Market latest fully graded slate is ${modelCard.latestGradedDate}.` : "Latest fully graded slate is not available yet.",
        ],
      });

      setStatus(`${marketLabel(payload.market)}: ${safeDecision}.`, payload);
    } catch (error) {
      console.error("Player prop ML prediction failed", error);
      setStatus(error.message, { error: error.message });
    }
  }

  function setDefaultLineForMarket() {
    const market = els.market?.value || "";
    if (!els.line) return;

    const defaults = {
      batter_hits: "0.5",
      batter_total_bases: "1.5",
      batter_home_runs: "0.5",
      pitcher_strikeouts: "4.5",
      pitcher_hits_allowed: "4.5",
      pitcher_earned_runs: "2.5",
    };

    els.line.value = defaults[market] || "0.5";
  }

  function init() {
    if (!els.button) return;
    els.market?.addEventListener("change", () => {
      setDefaultLineForMarket();
      loadTrainingStatus();
    });
    els.button.addEventListener("click", predictPropMl);
    setDefaultLineForMarket();
    loadTrainingStatus();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
