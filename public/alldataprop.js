(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    date: $("#allDataDate"),
    market: $("#allDataMarket"),
    gameSelect: $("#allDataGameSelect"),
    loadGames: $("#allDataLoadGamesButton"),
    savedProp: $("#allDataSavedProp"),
    loadProps: $("#allDataLoadPropsButton"),
    player: $("#allDataPlayer"),
    team: $("#allDataTeam"),
    opponent: $("#allDataOpponent"),
    pitcher: $("#allDataPitcher"),
    line: $("#allDataLine"),
    odds: $("#allDataOdds"),
    predict: $("#allDataPredictButton"),
    save: $("#allDataSavePredictionButton"),
    buildBvp: $("#allDataBuildBvpButton"),
    probability: $("#allDataProbability"),
    implied: $("#allDataImplied"),
    edge: $("#allDataEdge"),
    confidence: $("#allDataConfidence"),
    status: $("#allDataStatus"),
    output: $("#allDataOutput"),
  };

  let savedGames = [];
  let savedProps = [];
  let latestPrediction = null;

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

  function american(value) {
    const number = Number(value || 0);
    return `${number > 0 ? "+" : ""}${Math.round(number)}`;
  }

  function label(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
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

  function selectedGame() {
    if (!els.gameSelect || !els.gameSelect.value) return null;
    return savedGames[Number(els.gameSelect.value)] || null;
  }

  function params() {
    const query = new URLSearchParams();
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
      return `All Data Prop Predictor failed\n\n${payload?.error || "Unknown error"}`;
    }

    return [
      "All Data Prop Prediction",
      "========================",
      "",
      `Pick: ${payload.player || "--"} ${label(payload.market)} over ${payload.line}`,
      `Team/Opponent: ${payload.team || "--"} vs ${payload.opponent || "--"}`,
      `Pitcher: ${payload.pitcher || "--"}`,
      "",
      "Result",
      "------",
      `Probability: ${pct(payload.probabilityPercent)}`,
      `Sportsbook implied: ${pct(payload.sportsbookImpliedPercent)}`,
      `Edge: ${signedPct(payload.edgePercent)}`,
      `Fair odds: ${american(payload.fairOdds)}`,
      `Confidence: ${payload.confidence}`,
      `Recommendation: ${payload.recommendation}`,
      "",
      "Data Used",
      "---------",
      payload.dataUsed?.length ? payload.dataUsed.map((x) => `? ${x}`).join("\n") : "None yet",
      "",
      "Missing / Weak Data",
      "-------------------",
      payload.missingData?.length ? payload.missingData.map((x) => `- ${x}`).join("\n") : "None",
      "",
      "Adjustment Breakdown",
      "--------------------",
      payload.adjustments?.length
        ? payload.adjustments.map((x) => `${x.name}: ${signedPct(x.amountPercent)} ? ${x.reason}`).join("\n")
        : "No adjustments applied",
      "",
      "Raw JSON",
      "--------",
      JSON.stringify(payload, null, 2),
    ].join("\n");
  }

  function setOutput(message, payload) {
    if (els.status) els.status.textContent = message;
    if (els.output) els.output.textContent = readable(payload);
  }

  async function loadGames() {
    try {
      if (els.status) els.status.textContent = "Loading games for selected date...";
      const date = els.date?.value || today();
      const payload = await getJson(`/api/saved-games?date=${encodeURIComponent(date)}`);

      savedGames = payload.games || [];

      if (els.gameSelect) {
        els.gameSelect.innerHTML = "";

        const first = document.createElement("option");
        first.value = "";
        first.textContent = savedGames.length ? "Choose a matchup..." : "No games found for this date";
        els.gameSelect.appendChild(first);

        savedGames.forEach((game, index) => {
          const option = document.createElement("option");
          option.value = String(index);

          const pitcherText = [game.awayProbablePitcher, game.homeProbablePitcher]
            .filter(Boolean)
            .join(" vs ");

          option.textContent = pitcherText
            ? `${game.label} ? ${pitcherText}`
            : game.label;

          els.gameSelect.appendChild(option);
        });
      }

      if (els.status) {
        els.status.textContent = `Loaded ${savedGames.length} games from ${payload.source}`;
      }
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Load games failed: ${error.message}`;
      if (els.output) els.output.textContent = `Load games failed\n\n${error.message}`;
    }
  }

  function applyGameToFields() {
    const game = selectedGame();
    if (!game) return;

    // Leave team blank until a prop is selected, but set opponent hints if useful.
    if (els.status) {
      els.status.textContent = `Selected matchup: ${game.label}. Now click Load Props For Matchup.`;
    }
  }


  async function tryPullPropLineProps(date, market) {
    try {
      if (els.status) {
        els.status.textContent = "No saved props found. Pulling PropLine props automatically...";
      }

      const markets = market || [
        "pitcher_strikeouts",
        "pitcher_outs",
        "pitcher_hits_allowed",
        "pitcher_earned_runs",
        "batter_hits",
        "batter_total_bases",
        "batter_home_runs",
        "batter_rbis",
        "batter_stolen_bases",
        "batter_walks",
        "batter_singles",
        "batter_doubles",
        "batter_runs",
        "batter_2plus_hits",
        "batter_2plus_home_runs",
        "batter_2plus_rbis",
        "batter_3plus_rbis",
      ].join(",");

      await getJson(`/api/propline/props?markets=${encodeURIComponent(markets)}&date=${encodeURIComponent(date)}`, { method: "POST" });
      return true;
    } catch (error) {
      console.warn("Auto PropLine pull failed", error);
      if (els.status) {
        els.status.textContent = `No saved props found, and automatic PropLine pull failed: ${error.message}`;
      }
      return false;
    }
  }


  async function loadSavedProps() {
    try {
      if (els.status) els.status.textContent = "Loading saved PropLine props for selected matchup...";
      const date = els.date?.value || today();
      const market = els.market?.value || "";
      const game = selectedGame();

      let url = `/api/saved-props?date=${encodeURIComponent(date)}&market=${encodeURIComponent(market)}`;

      if (game) {
        url = `/api/saved-props-for-game?date=${encodeURIComponent(date)}&market=${encodeURIComponent(market)}&away=${encodeURIComponent(game.away)}&home=${encodeURIComponent(game.home)}`;
      }

      const payload = await getJson(url);
      savedProps = payload.rows || [];

      if (!savedProps.length) {
        const pulled = await tryPullPropLineProps(date, market);
        if (pulled) {
          const retryPayload = await getJson(url);
          savedProps = retryPayload.rows || [];
          if (retryPayload.warning && els.status) {
            els.status.textContent = retryPayload.warning;
          }
        }
      }

      if (payload.warning && els.status) {
        els.status.textContent = payload.warning;
      }

      if (els.savedProp) {
        els.savedProp.innerHTML = "";

        const first = document.createElement("option");
        first.value = "";
        first.textContent = savedProps.length ? "Choose a player/prop..." : "No saved props found";
        els.savedProp.appendChild(first);

        savedProps.forEach((row, index) => {
          const option = document.createElement("option");
          option.value = String(index);
          option.textContent = row.label || `${row.player} ${row.market}`;
          els.savedProp.appendChild(option);
        });
      }

      if (els.status) {
        const matchupText = game ? ` for ${game.label}` : "";
        els.status.textContent = savedProps.length
          ? `Loaded ${savedProps.length} saved props${matchupText}.`
          : `No saved props found${matchupText}. Try a different market or run Data Hub Sync.`;
      }
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Load saved props failed: ${error.message}`;
      if (els.output) els.output.textContent = `Load saved props failed\n\n${error.message}`;
    }
  }

  function applySavedProp() {
    if (!els.savedProp || !els.savedProp.value) return;

    const row = savedProps[Number(els.savedProp.value)];
    if (!row) return;

    const game = selectedGame();

    if (els.market && row.market) els.market.value = row.market;
    if (els.player) els.player.value = row.player || "";
    if (els.team) els.team.value = row.team || "";
    if (els.opponent) {
      if (row.opponent) {
        els.opponent.value = row.opponent;
      } else if (game && row.team === game.away) {
        els.opponent.value = game.home;
      } else if (game && row.team === game.home) {
        els.opponent.value = game.away;
      } else {
        els.opponent.value = row.opponent || "";
      }
    }

    // If the selected prop is a batter prop and probable pitchers are known,
    // auto-fill the opposing probable pitcher based on team.
    if (els.pitcher) {
      if (row.pitcher) {
        els.pitcher.value = row.pitcher;
      } else if (game && row.team === game.away) {
        els.pitcher.value = game.homeProbablePitcher || "";
      } else if (game && row.team === game.home) {
        els.pitcher.value = game.awayProbablePitcher || "";
      } else {
        els.pitcher.value = "";
      }
    }

    if (els.line) els.line.value = row.line || "0.5";
    if (els.odds) els.odds.value = row.americanOdds || "-110";

    if (els.status) els.status.textContent = "Player/prop loaded into predictor fields.";
  }

  async function predict() {
    try {
      if (els.status) els.status.textContent = "Running All Data Prop Predictor...";
      const payload = await getJson(`/api/all-data-prop/predict?${params().toString()}`);
      latestPrediction = payload;

      if (els.probability) els.probability.textContent = pct(payload.probabilityPercent);
      if (els.implied) els.implied.textContent = pct(payload.sportsbookImpliedPercent);
      if (els.edge) els.edge.textContent = signedPct(payload.edgePercent);
      if (els.confidence) els.confidence.textContent = payload.confidence;

      window.BaseballResultCards?.decorateMetric(els.edge, payload.edgePercent);
      window.BaseballResultCards?.decorateMetric(els.confidence, payload.confidence, "confidence");
      window.BaseballResultCards?.render(els.output, {
        title: `${payload.player || "--"} ${label(payload.market)} over ${payload.line ?? "--"}`,
        subtitle: `${payload.team || "--"} vs ${payload.opponent || "--"}${payload.pitcher ? ` · Pitcher: ${payload.pitcher}` : ""}`,
        probabilityPercent: payload.probabilityPercent,
        impliedPercent: payload.sportsbookImpliedPercent,
        edgePercent: payload.edgePercent,
        fairOdds: payload.fairOdds,
        confidence: payload.confidence,
        recommendation: payload.recommendation,
        notes: [
          `Data sources: ${(payload.dataUsed || []).length}`,
          `Missing/weak data: ${(payload.missingData || []).length}`,
        ],
      });

      setOutput("All Data Prop Prediction complete. Raw details are collapsed below.", payload);
    } catch (error) {
      console.error(error);
      setOutput(`All Data prediction failed: ${error.message}`, { error: error.message });
    }
  }

  async function savePrediction() {
    try {
      if (!latestPrediction) {
        await predict();
      }

      const payload = await getJson(`/api/all-data-prop/save-prediction?${params().toString()}`, { method: "POST" });

      if (els.status) els.status.textContent = `Prediction saved. History rows: ${payload.rows}`;
      if (els.output) {
        els.output.textContent = [
          "Prediction Saved",
          "================",
          "",
          `Path: ${payload.path}`,
          `Rows: ${payload.rows}`,
          "",
          "Saved Prediction",
          "----------------",
          JSON.stringify(payload.prediction, null, 2),
        ].join("\n");
      }
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Save prediction failed: ${error.message}`;
      if (els.output) els.output.textContent = `Save prediction failed\n\n${error.message}`;
    }
  }

  async function buildBvp() {
    try {
      if (els.status) els.status.textContent = "Building batter-vs-pitcher samples from latest Savant sync...";
      const payload = await getJson("/api/all-data-prop/build-bvp", { method: "POST" });
      if (els.status) els.status.textContent = "Batter-vs-pitcher samples updated.";
      if (els.output) els.output.textContent = JSON.stringify(payload, null, 2);
    } catch (error) {
      console.error(error);
      setOutput(`BvP build failed: ${error.message}`, { error: error.message });
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

  function init() {
    if (!els.predict) return;

    if (els.date && !els.date.value) els.date.value = today();

    els.date?.addEventListener("change", () => {
      loadGames();
    });

    els.market?.addEventListener("change", () => {
      setDefaultLine();
      loadSavedProps();
    });

    els.loadGames?.addEventListener("click", loadGames);
    els.gameSelect?.addEventListener("change", () => {
      applyGameToFields();
      loadSavedProps();
    });
    els.loadProps?.addEventListener("click", loadSavedProps);
    els.savedProp?.addEventListener("change", applySavedProp);
    els.predict.addEventListener("click", predict);
    els.save?.addEventListener("click", savePrediction);
    els.buildBvp?.addEventListener("click", buildBvp);

    setDefaultLine();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
