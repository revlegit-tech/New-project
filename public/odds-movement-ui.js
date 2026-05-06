(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    season: $("#oddsMovementSeason"),
    date: $("#oddsMovementDate"),
    market: $("#oddsMovementMarket"),
    sync: $("#oddsMovementSyncButton"),
    statusButton: $("#oddsMovementStatusButton"),
    status: $("#oddsMovementStatus"),
    output: $("#oddsMovementOutput"),
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
      "Odds Movement Snapshots",
      "=======================",
      "",
      JSON.stringify(payload, null, 2),
    ].join("\\n");
  }

  async function sync() {
    try {
      const season = els.season?.value || "2026";
      const date = els.date?.value || today();
      const market = els.market?.value || "";

      if (els.status) els.status.textContent = "Saving odds snapshot and building movement...";
      const payload = await getJson(`/api/odds-movement/sync?season=${encodeURIComponent(season)}&date=${encodeURIComponent(date)}&market=${encodeURIComponent(market)}`, { method: "POST" });

      if (els.status) {
        els.status.textContent = `Odds snapshot complete. Rows: ${payload.snapshot?.rowsSnapshotted ?? 0}, movement rows: ${payload.movement?.movementRows ?? 0}.`;
      }

      if (els.output) els.output.textContent = readable(payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Odds movement sync failed: ${error.message}`;
      if (els.output) els.output.textContent = `Odds movement sync failed\\n\\n${error.message}`;
    }
  }

  async function status() {
    try {
      const season = els.season?.value || "2026";
      const payload = await getJson(`/api/odds-movement/status?season=${encodeURIComponent(season)}`);

      if (els.status) {
        els.status.textContent = `Odds movement status loaded. Snapshot rows: ${payload.snapshotRows ?? 0}, movement rows: ${payload.movementRows ?? 0}.`;
      }

      if (els.output) els.output.textContent = readable(payload);
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Odds movement status failed: ${error.message}`;
      if (els.output) els.output.textContent = `Odds movement status failed\\n\\n${error.message}`;
    }
  }

  function init() {
    if (!els.sync) return;
    if (els.date && !els.date.value) els.date.value = today();

    els.sync.addEventListener("click", sync);
    els.statusButton?.addEventListener("click", status);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
