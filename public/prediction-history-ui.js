(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    season: $("#predictionSeason"),
    date: $("#predictionDate"),
    market: $("#predictionMarket"),
    player: $("#predictionPlayer"),
    team: $("#predictionTeam"),
    opponent: $("#predictionOpponent"),
    pitcher: $("#predictionPitcher"),
    line: $("#predictionLine"),
    odds: $("#predictionOdds"),
    save: $("#predictionSaveButton"),
    grade: $("#predictionGradeButton"),
    statusButton: $("#predictionStatusButton"),
    status: $("#predictionStatus"),
    output: $("#predictionOutput"),
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

  function query() {
    const params = new URLSearchParams({
      season: els.season?.value || "2026",
      date: els.date?.value || today(),
      market: els.market?.value || "batter_total_bases",
      player: els.player?.value || "",
      team: els.team?.value || "",
      opponent: els.opponent?.value || "",
      pitcher: els.pitcher?.value || "",
      line: els.line?.value || "1.5",
      american_odds: els.odds?.value || "-110",
    });

    return params.toString();
  }

  function readable(title, payload) {
    return [
      title,
      "=".repeat(title.length),
      "",
      JSON.stringify(payload, null, 2),
    ].join("\\n");
  }

  async function savePrediction() {
    try {
      if (!els.player?.value || !els.team?.value || !els.opponent?.value) {
        throw new Error("Player, team, and opponent are required.");
      }

      if (els.status) els.status.textContent = "Saving prediction...";
      const payload = await getJson(`/api/predictions/save?${query()}`, { method: "POST" });

      if (els.status) els.status.textContent = `Prediction saved: ${payload.predictionId}`;
      if (els.output) els.output.textContent = readable("Saved Prediction", payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Save failed: ${error.message}`;
      if (els.output) els.output.textContent = `Save failed\\n\\n${error.message}`;
    }
  }

  async function gradePredictions() {
    try {
      const season = els.season?.value || "2026";
      if (els.status) els.status.textContent = "Grading predictions...";
      const payload = await getJson(`/api/predictions/grade?season=${encodeURIComponent(season)}`, { method: "POST" });

      if (els.status) {
        els.status.textContent = `Grading complete. Graded: ${payload.graded}, Profit: ${payload.profitUnits} units.`;
      }

      if (els.output) els.output.textContent = readable("Prediction Grades", payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Grade failed: ${error.message}`;
      if (els.output) els.output.textContent = `Grade failed\\n\\n${error.message}`;
    }
  }

  async function status() {
    try {
      const season = els.season?.value || "2026";
      const payload = await getJson(`/api/predictions/status?season=${encodeURIComponent(season)}`);

      if (els.status) {
        els.status.textContent = `Predictions: ${payload.predictions}, Grades: ${payload.grades}.`;
      }

      if (els.output) els.output.textContent = readable("Prediction Status", payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Status failed: ${error.message}`;
      if (els.output) els.output.textContent = `Status failed\\n\\n${error.message}`;
    }
  }

  function init() {
    if (!els.save) return;
    if (els.date && !els.date.value) els.date.value = today();

    els.save.addEventListener("click", savePrediction);
    els.grade?.addEventListener("click", gradePredictions);
    els.statusButton?.addEventListener("click", status);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
