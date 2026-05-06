(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    season: $("#savantSeason"),
    startDate: $("#savantStartDate"),
    endDate: $("#savantEndDate"),
    sync: $("#savantSyncButton"),
    statusButton: $("#savantStatusButton"),
    status: $("#savantStatus"),
    output: $("#savantOutput"),
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
    return [
      "Baseball Savant Quality Metrics",
      "==============================",
      "",
      JSON.stringify(payload, null, 2),
    ].join("\\n");
  }

  async function sync() {
    try {
      const season = els.season?.value || "2026";
      const start = els.startDate?.value || `${season}-03-25`;
      const end = els.endDate?.value || today();

      if (els.status) els.status.textContent = "Syncing Savant data. This may take a while...";
      const payload = await getJson(`/api/savant/sync?season=${encodeURIComponent(season)}&start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}`, { method: "POST" });

      if (els.status) {
        const rows = payload.features?.rawRows ?? payload.collect?.rawRows ?? 0;
        els.status.textContent = `Savant sync complete. Raw rows: ${rows}.`;
      }

      if (els.output) els.output.textContent = readable(payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Savant sync failed: ${error.message}`;
      if (els.output) els.output.textContent = `Savant sync failed\\n\\n${error.message}`;
    }
  }

  async function status() {
    try {
      const season = els.season?.value || "2026";
      const payload = await getJson(`/api/savant/status?season=${encodeURIComponent(season)}`);

      if (els.status) {
        els.status.textContent = `Savant status loaded. Batter rows: ${payload.batterRowsCurrent ?? 0}, pitcher rows: ${payload.pitcherRowsCurrent ?? 0}.`;
      }

      if (els.output) els.output.textContent = readable(payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Savant status failed: ${error.message}`;
      if (els.output) els.output.textContent = `Savant status failed\\n\\n${error.message}`;
    }
  }

  function init() {
    if (!els.sync) return;
    if (els.endDate && !els.endDate.value) els.endDate.value = today();
    els.sync.addEventListener("click", sync);
    els.statusButton?.addEventListener("click", status);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
