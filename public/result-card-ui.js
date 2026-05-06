(() => {
  function number(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n : 0;
  }

  function pct(value) {
    return `${number(value).toFixed(2)}%`;
  }

  function signedPct(value) {
    const n = number(value);
    return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
  }

  function american(value) {
    const n = number(value);
    if (!n) return "--";
    return `${n > 0 ? "+" : ""}${Math.round(n)}`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function recommendationClass(text = "") {
    const lower = String(text).toLowerCase();
    if (lower.includes("strong")) return "strong";
    if (lower.includes("positive")) return "positive";
    if (lower.includes("avoid") || lower.includes("negative")) return "avoid";
    return "neutral";
  }

  function edgeClass(edge) {
    const n = number(edge);
    if (n >= 3) return "strong";
    if (n > 0) return "positive";
    if (n < 0) return "negative";
    return "neutral";
  }

  function confidenceClass(confidence = "") {
    const lower = String(confidence).toLowerCase();
    if (lower.includes("high")) return "high";
    if (lower.includes("medium")) return "medium";
    return "low";
  }

  function metric(label, value, extraClass = "") {
    return `
      <div class="result-card-metric ${extraClass}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `;
  }

  function render(target, config) {
    const output = typeof target === "string" ? document.querySelector(target) : target;
    if (!output || !config) return;

    const existing = output.parentElement?.querySelector(`[data-result-card-for="${output.id}"]`);
    if (existing) existing.remove();

    const edge = config.edgePercent;
    const rec = config.recommendation || (number(edge) > 0 ? "Positive edge" : number(edge) < 0 ? "Avoid" : "No clear edge");
    const card = document.createElement("section");
    card.className = "result-card";
    card.dataset.resultCardFor = output.id;
    card.innerHTML = `
      <div class="result-card-header">
        <div>
          <p class="eyebrow">Prediction Result</p>
          <h3>${escapeHtml(config.title || "Prop Prediction")}</h3>
          <p>${escapeHtml(config.subtitle || "")}</p>
        </div>
        <span class="result-rec ${recommendationClass(rec)}">${escapeHtml(rec)}</span>
      </div>
      <div class="result-card-grid">
        ${metric("Final Probability", pct(config.probabilityPercent), "probability")}
        ${metric("Sportsbook Implied", pct(config.impliedPercent), "implied")}
        ${metric("Edge", signedPct(edge), `edge ${edgeClass(edge)}`)}
        ${metric("Fair Odds", american(config.fairOdds), "odds")}
        ${metric("Confidence", config.confidence || "--", `confidence ${confidenceClass(config.confidence)}`)}
      </div>
      ${config.notes?.length ? `<div class="result-card-notes">${config.notes.map((note) => `<span>${escapeHtml(note)}</span>`).join("")}</div>` : ""}
    `;

    output.insertAdjacentElement("beforebegin", card);
  }

  function decorateMetric(el, numericValue, type = "edge") {
    if (!el) return;
    el.classList.remove("metric-positive", "metric-negative", "metric-neutral", "metric-high", "metric-medium", "metric-low");
    if (type === "confidence") {
      el.classList.add(`metric-${confidenceClass(numericValue)}`);
      return;
    }
    el.classList.add(`metric-${edgeClass(numericValue)}`);
  }

  window.BaseballResultCards = { render, decorateMetric };
})();
