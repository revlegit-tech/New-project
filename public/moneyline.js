(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    team: $("#moneylineTeam"),
    opponent: $("#moneylineOpponent"),
    homeAway: $("#moneylineHomeAway"),
    teamOdds: $("#moneylineTeamOdds"),
    opponentOdds: $("#moneylineOpponentOdds"),
    gameTotal: $("#moneylineGameTotal"),
    button: $("#moneylinePredictButton"),
    winProbability: $("#moneylineWinProbability"),
    impliedProbability: $("#moneylineImpliedProbability"),
    edge: $("#moneylineEdge"),
    favoriteStatus: $("#moneylineFavoriteStatus"),
    status: $("#moneylineStatus"),
    output: $("#moneylineOutput"),
  };

  function pct(value) {
    const number = Number(value || 0);
    return `${number.toFixed(2)}%`;
  }

  function signedPct(value) {
    const number = Number(value || 0);
    return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
  }

  function american(value) {
    const number = Number(value || 0);
    return `${number > 0 ? "+" : ""}${Math.round(number)}`;
  }

  function moneylineReadable(payload) {
    if (!payload || payload.error) {
      return `Moneyline prediction failed\n\n${payload?.error || "Unknown error"}`;
    }

    return [
      "Moneyline ML Result",
      "===================",
      "",
      `Matchup: ${payload.team} vs ${payload.opponent}`,
      `Location: ${payload.homeAway || "--"}`,
      `Favorite/underdog status: ${payload.favoriteStatus || "--"}`,
      "",
      "Sportsbook",
      "-----------",
      `Team moneyline: ${american(payload.teamMoneyline)}`,
      `Opponent moneyline: ${american(payload.opponentMoneyline)}`,
      `Game total: ${payload.gameTotal ?? "--"}`,
      `Sportsbook implied probability: ${pct(payload.sportsbookImpliedPercent)}`,
      "",
      "Model",
      "-----",
      `Team win probability: ${pct(payload.teamWinPercent)}`,
      `Model edge: ${signedPct(payload.modelEdgePercent)}`,
      `Recommendation: ${payload.recommendation || "--"}`,
      `Best model: ${payload.bestModel || "--"}`,
      "",
      "Raw JSON",
      "--------",
      JSON.stringify(payload, null, 2),
    ].join("\n");
  }

  function setStatus(message, payload) {
    if (els.status) els.status.textContent = message;
    if (els.output && payload !== undefined) {
      els.output.textContent = moneylineReadable(payload);
    }
  }

  function params() {
    const query = new URLSearchParams();
    query.set("team", els.team?.value || "");
    query.set("opponent", els.opponent?.value || "");
    query.set("home_away", els.homeAway?.value || "home");
    query.set("team_moneyline", els.teamOdds?.value || "0");
    query.set("opponent_moneyline", els.opponentOdds?.value || "0");
    query.set("game_total", els.gameTotal?.value || "0");
    return query;
  }

  async function predictMoneyline() {
    try {
      setStatus("Running moneyline prediction...");
      const response = await fetch(`/api/moneyline/predict?${params().toString()}`);
      const text = await response.text();

      let payload;
      try {
        payload = text ? JSON.parse(text) : {};
      } catch {
        throw new Error(`Moneyline endpoint returned non-JSON. Status ${response.status}. First text: ${text.slice(0, 80)}`);
      }

      if (!response.ok) {
        throw new Error(payload.error || "Moneyline prediction failed.");
      }

      if (els.winProbability) els.winProbability.textContent = pct(payload.teamWinPercent);
      if (els.impliedProbability) els.impliedProbability.textContent = pct(payload.sportsbookImpliedPercent);
      if (els.edge) els.edge.textContent = signedPct(payload.modelEdgePercent);
      if (els.favoriteStatus) els.favoriteStatus.textContent = payload.favoriteStatus || "--";

      window.BaseballResultCards?.decorateMetric(els.edge, payload.modelEdgePercent);
      window.BaseballResultCards?.render(els.output, {
        title: `${payload.team || "--"} moneyline vs ${payload.opponent || "--"}`,
        subtitle: `${payload.homeAway || "--"} · ${payload.favoriteStatus || "--"} · Total ${payload.gameTotal ?? "--"}`,
        probabilityPercent: payload.teamWinPercent,
        impliedPercent: payload.sportsbookImpliedPercent,
        edgePercent: payload.modelEdgePercent,
        fairOdds: payload.fairOdds ?? payload.teamMoneyline,
        confidence: payload.bestModel || "Moneyline",
        recommendation: payload.recommendation,
        notes: [
          `Team odds: ${american(payload.teamMoneyline)}`,
          `Opponent odds: ${american(payload.opponentMoneyline)}`,
        ],
      });

      setStatus(
        `${payload.team} vs ${payload.opponent}: ${payload.recommendation}.`,
        payload
      );
    } catch (error) {
      console.error("Moneyline prediction failed", error);
      setStatus(error.message, { error: error.message });
    }
  }

  function init() {
    if (!els.button) return;
    els.button.addEventListener("click", predictMoneyline);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
