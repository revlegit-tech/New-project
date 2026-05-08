(function () {
  const state = {
    loaded: false,
    cards: new Map(),
    payload: null,
  };

  const $ = (selector) => document.querySelector(selector);

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

  function pct(value) {
    if (value === null || value === undefined || value === "") return "--";
    const n = Number(value);
    return Number.isFinite(n) ? `${n.toFixed(2)}%` : "--";
  }

  function number(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  function readinessClass(card) {
    const status = String(card?.productionStatus || card?.modelStatus || "").toLowerCase();
    if (card?.canShowConfidentPick || status === "production") return "is-production";
    if (status.includes("candidate") || status.includes("experimental")) return "is-experimental";
    if (status.includes("not_ready") || status.includes("disabled")) return "is-not-ready";
    return "is-research";
  }

  function decisionLabelFor(card, recommendation, edgePercent) {
    const rec = String(recommendation || "").toLowerCase();
    const edge = number(edgePercent);
    if (rec.includes("negative") || rec.includes("avoid") || edge <= 0) return "No bet";
    if (card?.canShowConfidentPick) return "Potential edge";
    if (card?.productionStatus === "experimental" || card?.productionStatus === "production_candidate") return "Model lean";
    return "Watchlist";
  }

  function cardByMarket(market) {
    return state.cards.get(String(market || "").trim().toLowerCase());
  }

  function metric(label, value) {
    return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`;
  }

  function warningList(card, limit = 3) {
    const warnings = card?.trustWarnings || [];
    if (!warnings.length) return '<li>No active model-card warnings.</li>';
    return warnings.slice(0, limit).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  }

  function renderCard(card) {
    const backtest = card.backtest || {};
    const calibration = card.calibration || {};
    return `
      <article class="model-card ${readinessClass(card)}" data-market="${escapeHtml(card.market)}">
        <div class="model-card-topline">
          <div>
            <p class="eyebrow">Model Card</p>
            <h3>${escapeHtml(card.marketName || card.market)}</h3>
          </div>
          <span class="readiness-badge">${escapeHtml(card.readinessLabel || card.productionStatus || "Research")}</span>
        </div>
        <dl class="model-card-metrics">
          ${metric("Training rows", display(card.trainingRows))}
          ${metric("Class split", `${display(card.positiveRows, "0")} / ${display(card.negativeRows, "0")}`)}
          ${metric("Latest graded", display(card.latestGradedDate, "Not yet"))}
          ${metric("Backtest ROI", pct(backtest.roiPercent))}
          ${metric("Win rate", pct(backtest.winRatePercent))}
          ${metric("Brier", display(backtest.brierScore))}
        </dl>
        <div class="model-card-status-copy">
          <strong>${escapeHtml(card.decisionPolicy?.primaryLabel || "No bet")}</strong>
          <span>${escapeHtml(card.reason || calibration.message || "Market remains research-first.")}</span>
        </div>
        <ul class="model-card-warnings">${warningList(card)}</ul>
        <button class="ghost-button model-card-open" type="button" data-model-card-open="${escapeHtml(card.market)}">View model details</button>
      </article>
    `;
  }

  function renderPanel() {
    const panel = $("#modelCardsGrid");
    if (!panel) return;
    const cards = Array.from(state.cards.values());
    if (!cards.length) {
      panel.innerHTML = '<p class="model-note">No model cards are available yet.</p>';
      return;
    }
    panel.innerHTML = cards.map(renderCard).join("");

    const summary = $("#modelCardsSummary");
    if (summary && state.payload?.summary) {
      const data = state.payload.summary;
      summary.textContent = `${data.totalMarkets} markets · ${data.productionEligibleMarkets} production eligible · ${data.researchOnlyMarkets} research-only · ${data.missingArtifacts} missing artifacts`;
    }
  }

  function detailRows(card) {
    const backtest = card.backtest || {};
    const calibration = card.calibration || {};
    const rows = [
      ["Market", card.marketName || card.market],
      ["Production status", card.productionStatus],
      ["Can show confident pick", card.canShowConfidentPick ? "Yes" : "No"],
      ["Training rows", card.trainingRows],
      ["Positive rows", card.positiveRows],
      ["Negative rows", card.negativeRows],
      ["Trained at", display(card.trainedAt)],
      ["Latest graded slate", display(card.latestGradedDate, "Not yet")],
      ["Backtest graded rows", backtest.graded],
      ["Backtest ROI", pct(backtest.roiPercent)],
      ["Win rate", pct(backtest.winRatePercent)],
      ["Profit", backtest.profitUnits === null || backtest.profitUnits === undefined ? "--" : `${backtest.profitUnits}u`],
      ["Brier score", display(backtest.brierScore)],
      ["Log loss", display(backtest.logLoss)],
      ["Average CLV", pct(backtest.avgClvPercent)],
      ["Calibration", calibration.status || "uncalibrated"],
      ["Artifact exists", card.artifactExists ? "Yes" : "No"],
      ["Feature metadata", card.metadataExists ? "Yes" : "No"],
    ];
    return rows.map(([label, value]) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(value)}</td></tr>`).join("");
  }

  function ensureModal() {
    let modal = $("#modelCardModal");
    if (modal) return modal;
    modal = document.createElement("div");
    modal.id = "modelCardModal";
    modal.className = "model-card-modal hidden";
    modal.innerHTML = `
      <div class="model-card-modal-backdrop" data-model-card-close="1"></div>
      <section class="model-card-modal-panel" role="dialog" aria-modal="true" aria-labelledby="modelCardModalTitle">
        <button class="model-card-modal-close" type="button" data-model-card-close="1" aria-label="Close model card">×</button>
        <p class="eyebrow">Model Room</p>
        <h2 id="modelCardModalTitle">Model Card</h2>
        <p id="modelCardModalSubtitle" class="model-note"></p>
        <div id="modelCardModalBody"></div>
      </section>
    `;
    document.body.appendChild(modal);
    modal.addEventListener("click", (event) => {
      if (event.target?.dataset?.modelCardClose) closeModal();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeModal();
    });
    return modal;
  }

  function openCard(market) {
    const card = typeof market === "object" ? market : cardByMarket(market);
    if (!card) return;
    const modal = ensureModal();
    const title = $("#modelCardModalTitle");
    const subtitle = $("#modelCardModalSubtitle");
    const body = $("#modelCardModalBody");
    if (title) title.textContent = card.marketName || card.market;
    if (subtitle) subtitle.textContent = card.decisionPolicy?.copy || "Research-first model governance details.";
    if (body) {
      body.innerHTML = `
        <div class="model-card-detail-status ${readinessClass(card)}">
          <span class="readiness-badge">${escapeHtml(card.readinessLabel || card.productionStatus)}</span>
          <strong>${escapeHtml(card.decisionPolicy?.primaryLabel || "No bet")}</strong>
          <p>${escapeHtml(card.reason || "No promotion reason available.")}</p>
        </div>
        <table class="model-card-detail-table"><tbody>${detailRows(card)}</tbody></table>
        <h3>Trust warnings</h3>
        <ul class="model-card-warnings detail">${warningList(card, 12)}</ul>
      `;
    }
    modal.classList.remove("hidden");
  }

  function closeModal() {
    $("#modelCardModal")?.classList.add("hidden");
  }

  async function load() {
    if (state.loaded) return state.payload;
    const response = await fetch("/api/model-cards", { cache: "no-store" });
    if (!response.ok) throw new Error(`Model cards status ${response.status}`);
    const payload = await response.json();
    state.payload = payload;
    state.cards.clear();
    for (const card of payload.markets || []) {
      state.cards.set(String(card.market || "").toLowerCase(), card);
    }
    state.loaded = true;
    renderPanel();
    return payload;
  }

  document.addEventListener("click", (event) => {
    const button = event.target?.closest?.("[data-model-card-open]");
    if (!button) return;
    openCard(button.dataset.modelCardOpen);
  });

  document.addEventListener("DOMContentLoaded", () => {
    load().catch((error) => {
      const panel = $("#modelCardsGrid");
      if (panel) panel.innerHTML = `<p class="model-note">Model cards unavailable: ${escapeHtml(error.message)}</p>`;
    });
  });

  window.ModelCardsStore = {
    load,
    get: cardByMarket,
    open: openCard,
    decisionLabelFor,
    readinessClass,
  };
})();
