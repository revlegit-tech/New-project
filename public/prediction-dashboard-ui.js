(() => {
  const $ = (selector) => document.querySelector(selector);

  const els = {
    season: $("#predictionDashboardSeason"),
    date: $("#predictionDashboardDate"),
    market: $("#predictionDashboardMarket"),
    confidence: $("#predictionDashboardConfidence"),
    recommendation: $("#predictionDashboardRecommendation"),
    load: $("#predictionDashboardLoadButton"),
    grade: $("#predictionDashboardGradeButton"),
    cards: $("#predictionDashboardCards"),
    recent: $("#predictionDashboardRecent"),
    breakdowns: $("#predictionDashboardBreakdowns"),
    status: $("#predictionDashboardStatus"),
    output: $("#predictionDashboardOutput"),
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

  function params() {
    const q = new URLSearchParams({
      season: els.season?.value || "2026",
      limit: "75",
    });

    if (els.date?.value) q.set("date", els.date.value);
    if (els.market?.value) q.set("market", els.market.value);
    if (els.confidence?.value) q.set("confidence", els.confidence.value);
    if (els.recommendation?.value) q.set("recommendation", els.recommendation.value);

    return q.toString();
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function card(label, value, sub = "") {
    return `
      <div class="prediction-metric-card">
        <div class="prediction-metric-label">${escapeHtml(label)}</div>
        <div class="prediction-metric-value">${escapeHtml(value)}</div>
        ${sub ? `<div class="prediction-metric-sub">${escapeHtml(sub)}</div>` : ""}
      </div>
    `;
  }

  function renderCards(summary) {
    if (!els.cards) return;

    els.cards.innerHTML = [
      card("Picks", summary.picks ?? 0, `${summary.graded ?? 0} graded`),
      card("Record", `${summary.wins ?? 0}-${summary.losses ?? 0}-${summary.pushes ?? 0}`, `${summary.ungraded ?? 0} ungraded`),
      card("Win Rate", `${summary.winRate ?? 0}%`, "excluding pushes"),
      card("Profit", `${summary.profitUnits ?? 0} units`, `ROI ${summary.roiPercent ?? 0}%`),
    ].join("");
  }

  function table(rows, columns) {
    if (!rows || !rows.length) {
      return `<div class="prediction-empty">No rows yet.</div>`;
    }

    const header = columns.map((col) => `<th>${escapeHtml(col.label)}</th>`).join("");
    const body = rows.map((row) => {
      const cells = columns.map((col) => `<td>${escapeHtml(row[col.key] ?? "")}</td>`).join("");
      return `<tr>${cells}</tr>`;
    }).join("");

    return `<div class="prediction-table-scroll"><table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function renderRecent(rows) {
    if (!els.recent) return;

    els.recent.innerHTML = table(rows, [
      { key: "date", label: "Date" },
      { key: "market", label: "Market" },
      { key: "player", label: "Player" },
      { key: "team", label: "Team" },
      { key: "opponent", label: "Opp" },
      { key: "line", label: "Line" },
      { key: "actualStat", label: "Actual" },
      { key: "result", label: "Result" },
      { key: "profitUnits", label: "Units" },
      { key: "finalEdgePercent", label: "Edge %" },
      { key: "confidence", label: "Confidence" },
      { key: "recommendation", label: "Recommendation" },
    ]);
  }

  function renderBreakdownTable(title, rows, firstKey, firstLabel) {
    return `
      <div class="prediction-breakdown-card">
        <h4>${escapeHtml(title)}</h4>
        ${table(rows, [
          { key: firstKey, label: firstLabel },
          { key: "picks", label: "Picks" },
          { key: "wins", label: "W" },
          { key: "losses", label: "L" },
          { key: "pushes", label: "P" },
          { key: "winRate", label: "Win %" },
          { key: "profitUnits", label: "Units" },
          { key: "roiPercent", label: "ROI %" },
        ])}
      </div>
    `;
  }

  function renderBreakdowns(payload) {
    if (!els.breakdowns) return;

    els.breakdowns.innerHTML = [
      renderBreakdownTable("By Market", payload.byMarket || [], "market", "Market"),
      renderBreakdownTable("By Confidence", payload.byConfidence || [], "confidence", "Confidence"),
      renderBreakdownTable("By Recommendation", payload.byRecommendation || [], "recommendation", "Recommendation"),
    ].join("");
  }

  async function loadDashboard() {
    try {
      if (els.status) els.status.textContent = "Loading prediction dashboard...";

      const payload = await getJson(`/api/predictions/dashboard?${params()}`);

      renderCards(payload.summary || {});
      renderRecent(payload.recent || []);
      renderBreakdowns(payload);

      if (els.status) {
        els.status.textContent = `Loaded ${payload.summary?.picks ?? 0} picks. Profit: ${payload.summary?.profitUnits ?? 0} units.`;
      }

      if (els.output) {
        els.output.textContent = JSON.stringify(payload, null, 2);
      }
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Dashboard failed: ${error.message}`;
      if (els.output) els.output.textContent = `Dashboard failed\n\n${error.message}`;
    }
  }

  async function gradeAndRefresh() {
    try {
      const season = els.season?.value || "2026";
      if (els.status) els.status.textContent = "Grading predictions...";
      await getJson(`/api/predictions/grade?season=${encodeURIComponent(season)}`, { method: "POST" });
      await loadDashboard();
    } catch (error) {
      console.error(error);
      if (els.status) els.status.textContent = `Grade + refresh failed: ${error.message}`;
      if (els.output) els.output.textContent = `Grade + refresh failed\n\n${error.message}`;
    }
  }

  function init() {
    if (!els.load) return;

    els.load.addEventListener("click", loadDashboard);
    els.grade?.addEventListener("click", gradeAndRefresh);

    loadDashboard().catch(() => {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
