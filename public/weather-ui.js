(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    season: $("#weatherSeason"),
    phase: $("#weatherPhase"),
    sync: $("#weatherSyncButton"),
    build: $("#weatherBuildButton"),
    status: $("#weatherStatus"),
    output: $("#weatherOutput"),
  };

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
      return `Weather sync failed\n\n${payload?.error || "Unknown error"}`;
    }

    const collect = payload.collect || payload;
    const features = payload.features || payload;

    return [
      "Weather Features",
      "================",
      "",
      `Season: ${collect.season ?? features.season ?? "--"}`,
      `Phase: ${collect.phase ?? features.phase ?? "--"}`,
      "",
      "Collection",
      "----------",
      `Rows collected: ${collect.rowsCollected ?? "--"}`,
      `Skipped existing: ${collect.skippedExisting ?? "--"}`,
      `Errors: ${collect.errorCount ?? 0}`,
      `Weather file: ${collect.weatherFile || "--"}`,
      "",
      "Features",
      "--------",
      `Input weather rows: ${features.inputWeatherRows ?? "--"}`,
      `Feature rows: ${features.featureRows ?? "--"}`,
      `Feature file: ${features.featureFile || "--"}`,
      "",
      "Raw JSON",
      "--------",
      JSON.stringify(payload, null, 2),
    ].join("\\n");
  }

  async function syncWeather() {
    try {
      const season = els.season?.value || "2026";
      const phase = els.phase?.value || "regular";

      if (els.status) els.status.textContent = "Syncing weather and building features...";
      const payload = await getJson(`/api/weather/sync?season=${encodeURIComponent(season)}&phase=${encodeURIComponent(phase)}`, { method: "POST" });

      if (els.status) {
        const rows = payload.features?.featureRows ?? 0;
        els.status.textContent = `Weather sync complete. Feature rows: ${rows}.`;
      }

      if (els.output) els.output.textContent = readable(payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Weather sync failed: ${error.message}`;
      if (els.output) els.output.textContent = `Weather sync failed\\n\\n${error.message}`;
    }
  }

  async function buildWeather() {
    try {
      const season = els.season?.value || "2026";
      const phase = els.phase?.value || "regular";

      if (els.status) els.status.textContent = "Rebuilding weather features...";
      const payload = await getJson(`/api/weather/build?season=${encodeURIComponent(season)}&phase=${encodeURIComponent(phase)}`, { method: "POST" });

      if (els.status) els.status.textContent = `Weather features rebuilt. Rows: ${payload.featureRows}.`;
      if (els.output) els.output.textContent = readable(payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Weather build failed: ${error.message}`;
      if (els.output) els.output.textContent = `Weather build failed\\n\\n${error.message}`;
    }
  }

  function init() {
    if (!els.sync) return;
    els.sync.addEventListener("click", syncWeather);
    els.build?.addEventListener("click", buildWeather);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
