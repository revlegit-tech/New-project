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

  function display(value, fallback = "--") {
    const text = String(value ?? "").trim();
    return text || fallback;
  }

  function recommendationClass(text = "") {
    const lower = String(text).toLowerCase();
    if (lower.includes("potential")) return "strong";
    if (lower.includes("watch") || lower.includes("lean")) return "positive";
    if (lower.includes("no bet") || lower.includes("avoid") || lower.includes("negative")) return "avoid";
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

  function readinessClass(card) {
    if (window.ModelCardsStore?.readinessClass) return window.ModelCardsStore.readinessClass(card);
    const status = String(card?.productionStatus || card?.modelStatus || "").toLowerCase();
    if (card?.canShowConfidentPick || status === "production") return "is-production";
    if (status.includes("candidate") || status.includes("experimental")) return "is-experimental";
    if (status.includes("not_ready") || status.includes("disabled")) return "is-not-ready";
    return "is-research";
  }

  function safeDecisionLabel(config, card) {
    if (window.ModelCardsStore?.decisionLabelFor) {
      return window.ModelCardsStore.decisionLabelFor(card, config.recommendation, config.edgePercent);
    }
    const edge = number(config.edgePercent);
    if (edge <= 0) return "No bet";
    if (card?.canShowConfidentPick) return "Potential edge";
    return "Watchlist";
  }

  function metric(label, value, extraClass = "") {
    return `
      <div class="result-card-metric ${extraClass}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `;
  }

  function trustMetric(label, value) {
    return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`;
  }

  function reasonList(config, card) {
    const reasons = [...(config.reasons || [])];
    if (!reasons.length) {
      reasons.push(`Price edge: ${signedPct(config.edgePercent)} versus sportsbook implied probability.`);
      reasons.push(`Market readiness: ${card?.readinessLabel || "Research only"}.`);
      reasons.push(card?.latestGradedDate ? `Latest fully graded slate: ${card.latestGradedDate}.` : "Latest fully graded slate is not available yet.");
    }
    return reasons.slice(0, 3).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("");
  }

  function warningText(card) {
    const warnings = card?.trustWarnings || [];
    if (warnings.length) return warnings[0];
    return card?.canShowConfidentPick ? "Market passed current readiness gates." : "Research-only until artifact, grading, and calibration gates pass.";
  }

  function render(target, config) {
    const output = typeof target === "string" ? document.querySelector(target) : target;
    if (!output || !config) return;

    const existing = output.parentElement?.querySelector(`[data-result-card-for="${output.id}"]`);
    if (existing) existing.remove();

    const card = config.modelCard || window.ModelCardsStore?.get?.(config.market) || null;
    const rec = safeDecisionLabel(config, card);
    const readiness = card?.readinessLabel || config.readinessLabel || "Research only";
    const warnings = card?.trustWarnings || [];
    const resultCard = document.createElement("section");
    resultCard.className = `result-card premium-prop-card ${readinessClass(card)}`;
    resultCard.dataset.resultCardFor = output.id;
    resultCard.innerHTML = `
      <div class="result-card-header premium-prop-header">
        <div>
          <p class="eyebrow">Premium Prop Card</p>
          <h3>${escapeHtml(config.title || "Prop Prediction")}</h3>
          <p>${escapeHtml(config.subtitle || "")}</p>
        </div>
        <span class="result-rec ${recommendationClass(rec)}">${escapeHtml(rec)}</span>
      </div>

      <div class="result-card-grid">
        ${metric("Model Probability", pct(config.probabilityPercent), "probability")}
        ${metric("Book Implied", pct(config.impliedPercent), "implied")}
        ${metric("Estimated Edge", signedPct(config.edgePercent), `edge ${edgeClass(config.edgePercent)}`)}
        ${metric("Fair Odds", american(config.fairOdds), "odds")}
        ${metric("Confidence", config.confidence || "Research", `confidence ${confidenceClass(config.confidence)}`)}
      </div>

      <div class="prop-card-trust-layer">
        <div class="prop-card-trust-head">
          <span class="readiness-badge">${escapeHtml(readiness)}</span>
          <strong>${escapeHtml(warningText(card))}</strong>
        </div>
        <dl class="prop-card-trust-grid">
          ${trustMetric("Training rows", display(card?.trainingRows))}
          ${trustMetric("Class split", card ? `${display(card.positiveRows, "0")} / ${display(card.negativeRows, "0")}` : "--")}
          ${trustMetric("Latest graded", display(card?.latestGradedDate, "Not yet"))}
          ${trustMetric("Calibration", card?.calibrated ? "Verified" : "Unverified")}
          ${trustMetric("Warnings", String(warnings.length))}
        </dl>
      </div>

      <div class="prop-card-reasons">
        <strong>Why it is shown</strong>
        <ol>${reasonList(config, card)}</ol>
      </div>

      ${config.notes?.length ? `<div class="result-card-notes">${config.notes.map((note) => `<span>${escapeHtml(note)}</span>`).join("")}</div>` : ""}

      <div class="prop-card-actions">
        <button class="ghost-button" type="button" data-model-card-open="${escapeHtml(config.market || card?.market || "")}">View model card</button>
        <span>${escapeHtml(card?.decisionPolicy?.copy || "No confident pick language unless trust gates pass.")}</span>
      </div>
    `;

    output.insertAdjacentElement("beforebegin", resultCard);
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
