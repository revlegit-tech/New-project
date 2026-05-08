(function () {
  const APP_STATUS_SCHEMA = "app-status-v1";
  const $ = (selector) => document.querySelector(selector);
  function display(value, fallback = "--") { const text = String(value || "").trim(); return text || fallback; }
  function confidenceClass(value) { const text = String(value || "").toLowerCase(); if (text === "good") return "is-good"; if (text === "missing" || text === "failed") return "is-bad"; return "is-partial"; }
  function appendText(parent, tagName, text, className) { const element = document.createElement(tagName); if (className) element.className = className; element.textContent = text; parent.appendChild(element); return element; }
  function metric(label, value, fallback) { const wrapper = document.createElement("div"); appendText(wrapper, "dt", label); appendText(wrapper, "dd", display(value, fallback)); return wrapper; }
  function isObject(value) { return Boolean(value) && typeof value === "object" && !Array.isArray(value); }
  function stringList(value) { if (!Array.isArray(value)) return []; return value.map((item) => String(item)).filter((item) => item.trim()); }
  function stateLabel(detail, state) { const raw = detail && typeof detail.label === "string" ? detail.label : String(state || "research_mode").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()); return display(raw, "Research Mode"); }
  function requestIdFrom(response, payload) { return response?.headers?.get("X-Request-Id") || payload?.meta?.requestId || payload?.requestId || ""; }
  function validatePayload(payload) {
    const errors = [];
    if (!isObject(payload)) return ["status payload must be an object"];
    if (payload.status !== "ok") errors.push("status must be ok");
    if (typeof payload.productState !== "string") errors.push("productState must be a string");
    if (!isObject(payload.productStateDetail)) errors.push("productStateDetail must be an object");
    if (!isObject(payload.grading) || typeof payload.grading.state !== "string") errors.push("grading.state must be a string");
    if (typeof payload.dataConfidence !== "string") errors.push("dataConfidence must be a string");
    if (!Array.isArray(payload.productionEligibleMarkets)) errors.push("productionEligibleMarkets must be an array");
    if (!isObject(payload.meta)) errors.push("meta must be an object");
    if (isObject(payload.meta) && payload.meta.schema !== APP_STATUS_SCHEMA) errors.push(`meta.schema must be ${APP_STATUS_SCHEMA}`);
    if (isObject(payload.meta) && typeof payload.meta.requestId !== "string") errors.push("meta.requestId must be a string");
    const hasBoardDate = typeof payload.latestBoardDate === "string" || typeof payload.playerboard?.latestAvailableDate === "string" || typeof payload.playerboard?.date === "string";
    if (!hasBoardDate) errors.push("latestBoardDate or playerboard date must be present");
    if (isObject(payload.playerboard)) {
      if (typeof payload.playerboard.dataConfidence !== "string") errors.push("playerboard.dataConfidence must be a string");
      if (typeof payload.playerboard.rowsLoaded !== "number") errors.push("playerboard.rowsLoaded must be a number");
    } else { errors.push("playerboard must be an object"); }
    return errors;
  }
  function normalizeStatus(payload, requestId) {
    const detail = isObject(payload.productStateDetail) ? payload.productStateDetail : {};
    const state = typeof payload.productState === "string" ? payload.productState : detail.state;
    const productionMarkets = Array.isArray(payload.productionEligibleMarkets) ? payload.productionEligibleMarkets : [];
    const warnings = stringList(payload.warnings);
    const explicitMissing = payload.dataConfidence === "Missing" || payload.grading?.state === "failed" || payload.grading?.state === "not_started";
    return { state: state || detail.state || "research_mode", label: explicitMissing && productionMarkets.length === 0 ? "Research Only" : stateLabel(detail, state), message: detail.message || "Research-first mode is enabled until markets pass grading and model-readiness gates.", boardDate: payload.latestBoardDate || payload.playerboard?.latestAvailableDate || payload.playerboard?.date || "", oddsTimestamp: payload.playerboard?.latestSnapshotAt || payload.slateStatus?.latestOddsTimestamp || "", gradedDate: payload.latestFullyGradedDate || payload.grading?.latestFullyGradedDate || "", gradingState: payload.grading?.state || "not_started", dataConfidence: payload.dataConfidence || payload.playerboard?.dataConfidence || "Missing", productionMarkets, warnings, requestId: requestId || payload.meta?.requestId || "", schema: payload.meta?.schema || "" };
  }
  function render(status) {
    const banner = $("#trustSurfaceBanner"); if (!banner) return;
    banner.classList.remove("is-good", "is-partial", "is-bad"); banner.classList.add(confidenceClass(status.dataConfidence)); banner.replaceChildren();
    const main = document.createElement("div"); main.className = "trust-surface-main"; appendText(main, "span", display(status.label), "trust-mode-pill");
    const copy = document.createElement("div"); appendText(copy, "strong", "Today’s board is research-first."); appendText(copy, "p", display(status.message)); main.appendChild(copy); banner.appendChild(main);
    const metrics = document.createElement("dl"); metrics.className = "trust-surface-metrics"; metrics.setAttribute("aria-label", "Board trust status"); metrics.appendChild(metric("Board date", status.boardDate)); metrics.appendChild(metric("Latest odds", status.oddsTimestamp)); metrics.appendChild(metric("Fully graded slate", status.gradedDate, "Not yet")); metrics.appendChild(metric("Grading", status.gradingState)); metrics.appendChild(metric("Data confidence", status.dataConfidence)); metrics.appendChild(metric("Production markets", status.productionMarkets.length)); if (status.requestId) metrics.appendChild(metric("Request ID", status.requestId)); banner.appendChild(metrics);
    const warning = $("#trustSurfaceWarning"); if (warning) { const text = status.warnings?.[0] || "No confident picks are shown unless a market has exact model artifacts, grading history, and readiness gates."; warning.textContent = text; }
  }
  function renderSafeFailure(message, requestId) { render({ label: "Research Only", message: display(message, "Status is unavailable. Treat all model output as research-only until health checks recover."), dataConfidence: "Missing", gradingState: "failed", productionMarkets: [], warnings: [display(message, "Malformed or unavailable trust-surface status payload.")], requestId: requestId || "", schema: APP_STATUS_SCHEMA }); }
  async function loadTrustSurface() {
    const banner = $("#trustSurfaceBanner"); if (!banner) return;
    try {
      const response = await fetch("/api/app/status", { cache: "no-store" });
      const requestId = requestIdFrom(response, null);
      if (!response.ok) throw new Error(`Status ${response.status}${requestId ? ` (${requestId})` : ""}`);
      const payload = await response.json();
      const finalRequestId = requestIdFrom(response, payload);
      const validationErrors = validatePayload(payload);
      if (validationErrors.length) { console.warn("Trust surface contract violation", { errors: validationErrors, requestId: finalRequestId }); renderSafeFailure("Malformed status payload. Treat this slate as research-only until contract validation passes.", finalRequestId); return; }
      render(normalizeStatus(payload, finalRequestId));
    } catch (error) { const message = String(error && error.message ? error.message : error); console.warn("Trust surface status load failed", { error: message }); renderSafeFailure(message, ""); }
  }
  window.__MLBTrustSurfaceTestHooks = { APP_STATUS_SCHEMA, validatePayload, normalizeStatus, renderSafeFailure };
  document.addEventListener("DOMContentLoaded", loadTrustSurface);
})();
