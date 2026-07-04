import { jsonFetch } from "../../shared/api/client";
import { clear, h } from "../../shared/components/dom";
import { formatOdds, number, percent, signedPercent, text } from "../../shared/formatting";
import { marketLabel } from "../../shared/markets/markets";
import { getMlModelsStatus, getProductionGates, getShadowFreshness, getShadowReadiness, getShadowSummary } from "../api/client";
import { badgeToneClass, freshnessSeverity, rowActionability, rowBoardTrustSurface, rowFreshness, rowPropIdentity, rowReadiness, rowTrustChips, rowTrustCopy, rowTrustReasonLabel, rowTrustSummary, trustStatusLabel } from "../trust";
import {
  edgeValue,
  matchup,
  OutlierBoardRow,
  readiness,
  rowImpliedProbability,
  rowLine,
  rowMarketKey,
  rowModelProbability,
  rowOdds,
  rowPlayer,
  rowPropKey,
} from "../board/utils";
import { MlModelsStatusResponse, ProductionGatesResponse, ShadowFreshnessResponse, ShadowReadinessMarket, ShadowReadinessResponse, ShadowSummaryResponse } from "../types/modelAudit";

export interface DetailRailContext {
  date: string;
  status: unknown;
  exposure: unknown;
  requestId?: string;
  savePickLabel?: string;
}

export interface PropDetailPayload {
  status?: string;
  detail?: Record<string, unknown>;
  [key: string]: unknown;
}

interface ShadowAuditState {
  status?: MlModelsStatusResponse;
  summary?: ShadowSummaryResponse;
  readiness?: ShadowReadinessResponse;
  gates?: ProductionGatesResponse;
  freshness?: ShadowFreshnessResponse;
  error?: string;
  loading?: boolean;
}

export function renderDetailRailShell(): HTMLElement {
  return h("aside", { id: "detailRail", className: "ob-detail", attrs: { "aria-label": "Prop detail rail", "aria-live": "polite" } }, [emptyRail()]);
}

export class DetailRailController {
  private currentRow: OutlierBoardRow | null = null;
  private currentIndex = -1;
  private requestSequence = 0;

  constructor(private readonly hostProvider: () => HTMLElement | null) {}

  open(row: OutlierBoardRow, index: number, context: DetailRailContext): void {
    this.currentRow = row;
    this.currentIndex = index;
    this.render(row, context, { loading: true });
    void this.hydrate(row, context, this.requestSequence + 1);
  }

  close(): void {
    this.currentRow = null;
    this.currentIndex = -1;
    this.requestSequence += 1;
    clear(this.hostProvider(), [emptyRail()]);
  }

  rerender(context: DetailRailContext): void {
    if (!this.currentRow) return;
    this.render(this.currentRow, context, { loading: false });
  }

  selectedRow(): OutlierBoardRow | null {
    return this.currentRow;
  }

  selectedIndex(): number {
    return this.currentIndex;
  }

  private async hydrate(row: OutlierBoardRow, context: DetailRailContext, sequence: number): Promise<void> {
    this.requestSequence = sequence;
    const query = detailQuery(row, context.date);
    const [detail, audit] = await Promise.allSettled([
      jsonFetch<PropDetailPayload>(`/api/prop-detail?${query.toString()}`),
      loadShadowAudit(rowMarketKey(row)),
    ]);
    if (this.requestSequence !== sequence || this.currentRow !== row) return;
    const detailState = detail.status === "fulfilled"
      ? { detail: detail.value.payload?.detail || detail.value.payload }
      : { error: detail.reason instanceof Error ? detail.reason.message : String(detail.reason) };
    const auditState = audit.status === "fulfilled"
      ? audit.value
      : { error: audit.reason instanceof Error ? audit.reason.message : String(audit.reason) };
    this.render(row, context, { ...detailState, shadowAudit: auditState, loading: false });
  }

  private render(row: OutlierBoardRow, context: DetailRailContext, state: { detail?: Record<string, unknown>; error?: string; loading?: boolean; shadowAudit?: ShadowAuditState } = {}): void {
    const rail = this.hostProvider();
    if (!rail) return;
    const severity = freshnessSeverity(context.status);
    const readiness = rowReadiness(row);
    const freshness = rowFreshness(row, severity.label);
    const actionability = rowActionability(row);
    const summary = rowTrustSummary(row);
    clear(rail, [
      h("article", { className: "ob-rail-card" }, [
        h("p", { className: "ob-kicker", text: "Detail rail" }),
        h("h2", { text: rowPlayer(row) }),
        h("p", { text: `${marketLabel(rowMarketKey(row))} · ${matchup(row)} · ${text(row.rawLabel ?? row.side, "Over")}` }),
        h("div", { className: "ob-stat-grid" }, [
          stat("Line", text(rowLine(row))),
          stat("Odds", formatOdds(rowOdds(row))),
          stat("Model", percent(rowModelProbability(row))),
          stat("Edge", signedPercent(edgeValue(row))),
        ]),
      ]),
      h("article", { className: "ob-rail-card" }, [
        h("h3", { text: "Trust context" }),
        h("p", { text: rowTrustCopy(row) }),
        h("div", { className: "ob-chip-row is-rail" }, rowTrustChips(row).map((chip) => h("span", { className: `ob-pill ob-pill-mini ${badgeToneClass(chip.tone)}`, attrs: { title: chip.title }, text: chip.label }))),
        h("div", { className: "ob-stat-grid" }, [stat("Readiness", readiness.label), stat("Freshness", freshness.label), stat("Action", actionability.label), stat("Implied", percent(rowImpliedProbability(row))), stat("Request", text(context.requestId, "latest"))]),
      ]),
      h("article", { className: "ob-rail-card" }, [
        h("h3", { text: "Why it appears" }),
        h("p", { text: summary.actionabilityReason }),
        h("div", { className: "ob-stat-grid" }, [
          stat("Prop", `${rowPlayer(row)} / ${marketLabel(rowMarketKey(row))}`),
          stat("Market readiness", trustStatusLabel(summary.marketCapabilityStatus)),
          stat("Model state", trustStatusLabel(summary.productionStatus)),
          stat("Production", summary.modelProductionEligible ? "Production eligible" : "Research only"),
          stat("Calibration", trustStatusLabel(summary.calibrationStatus || "missing")),
          stat("Backtest", trustStatusLabel(summary.backtestStatus || "missing")),
          stat("Game markets", trustStatusLabel(summary.gameMarketStatus || "missing")),
          stat("Missing groups", summary.missingFeatureGroups.length ? summary.missingFeatureGroups.join(", ") : "None reported"),
        ]),
        h("p", { className: "ob-muted", text: summary.missingDataSummary }),
      ]),
      renderExplainability(row),
      renderRowTrustDetail(row, context.status),
      renderShadowModelAudit(row, state.shadowAudit || { loading: Boolean(state.loading) }),
      renderServerDetail(state),
      h("article", { className: "ob-rail-card" }, [
        h("h3", { text: "Picks & exposure" }),
        h("p", { text: "Research-only saves stay at zero exposure and do not alter model backtests." }),
        h("button", { className: "ob-button is-primary", type: "button", text: text(context.savePickLabel, "Add research pick"), dataset: { action: "save-pick" } }),
        h("p", { id: "savePickStatus", className: "ob-muted", text: exposureCopy(context.exposure) }),
      ]),
    ]);
  }
}

async function loadShadowAudit(market: string): Promise<ShadowAuditState> {
  const [status, summary, readiness, gates, freshness] = await Promise.allSettled([
    getMlModelsStatus(),
    getShadowSummary(market),
    getShadowReadiness(market),
    getProductionGates(market),
    getShadowFreshness(market),
  ]);
  const failures = [status, summary, readiness, gates, freshness].filter((result) => result.status === "rejected") as PromiseRejectedResult[];
  const audit: ShadowAuditState = {
    status: status.status === "fulfilled" ? status.value : undefined,
    summary: summary.status === "fulfilled" ? summary.value : undefined,
    readiness: readiness.status === "fulfilled" ? readiness.value : undefined,
    gates: gates.status === "fulfilled" ? gates.value : undefined,
    freshness: freshness.status === "fulfilled" ? freshness.value : undefined,
  };
  if (failures.length === 5) {
    audit.error = failures[0].reason instanceof Error ? failures[0].reason.message : String(failures[0].reason);
  }
  return audit;
}

function renderExplainability(row: OutlierBoardRow): HTMLElement {
  const explainability = objectValue(row.explainability);
  const model = objectValue(explainability.model);
  const calibration = objectValue(explainability.calibration);
  const context = objectValue(explainability.context);
  const guardrails = objectValue(explainability.guardrails);
  const researchOnly = objectValue(explainability.researchOnly);
  const reasons = arrayValue(explainability.primaryReasons);
  const blocks = arrayValue(explainability.blocks);
  const nextChecks = arrayValue(explainability.nextChecks);
  const boardTrust = rowBoardTrustSurface(row);
  const trustChip = boardTrust.chips[0];
  const score = boardTrust.trustScore === null ? "Not available" : String(boardTrust.trustScore);
  return h("article", { className: "ob-rail-card" }, [
    h("h3", { text: "Trust explanation" }),
    h("div", { className: "ob-chip-row is-rail" }, [
      h("span", { className: `ob-pill ob-pill-mini ${badgeToneClass(trustChip.tone)}`, attrs: { title: trustChip.title }, text: trustChip.label }),
      h("span", { className: "ob-pill ob-pill-mini", text: `Score ${score}` }),
      h("span", { className: `ob-pill ob-pill-mini ${badgeToneClass("risk")}`, text: "Research only" }),
    ]),
    h("p", { text: text(explainability.summary, rowTrustCopy(row)) }),
    h("div", { className: "ob-stat-grid" }, [
      stat("Model", text(model.modelProbabilitySource, "none")),
      stat("Probability", Boolean(model.hasModelProbability) ? percent(model.modelProbabilityPercent) : "Withheld"),
      stat("Calibration", trustStatusLabel(boardTrust.calibrationStatus || calibration.calibrationStatus || row.calibrationStatus || "unknown")),
      stat("Context", trustStatusLabel(boardTrust.contextReadinessStatus || context.contextReadinessStatus || row.contextReadinessStatus || "unknown")),
      stat("Guardrail", trustStatusLabel(boardTrust.probabilityGuardrailStatus || guardrails.probabilityGuardrailStatus || row.probabilityGuardrailStatus || "unknown")),
      stat("Reason", rowTrustReasonLabel(row)),
      stat("Capability", trustStatusLabel(boardTrust.marketCapabilityStatus)),
      stat("Action", text(researchOnly.action || row.action, "Research")),
      stat("No bet action", Boolean(researchOnly.betActionAllowed) ? "Allowed" : "Disabled"),
    ]),
    reasons.length ? h("p", { className: "ob-muted", text: `Reasons: ${reasons.join(", ")}` }) : h("p", { className: "ob-muted", text: "No primary reasons reported." }),
    blocks.length ? h("p", { className: "ob-muted", text: `Blocks: ${blocks.join(", ")}` }) : h("p", { className: "ob-muted", text: "No hard blocks reported." }),
    h("p", { className: "ob-muted", text: `Next: ${nextChecks.length ? nextChecks.join(" / ") : "Check lineup confirmation / Check book/odds freshness."}` }),
  ]);
}

function renderRowTrustDetail(row: OutlierBoardRow, status: unknown): HTMLElement {
  const trust = row.trust || {};
  const model = objectValue(trust.model);
  const actionnetwork = objectValue(trust.actionnetwork);
  const runtime = objectValue(trust.runtime);
  const severity = freshnessSeverity(status);
  const summary = rowTrustSummary(row);
  const identity = rowPropIdentity(row);
  return h("article", { className: "ob-rail-card" }, [
    h("h3", { text: "Model & source trust" }),
    h("div", { className: "ob-stat-grid" }, [
      stat("Model", text(model.modelStatus ?? model.status ?? row.modelStatus, "unavailable")),
      stat("Version", text(model.modelVersion ?? model.version, "none")),
      stat("Coverage", text(model.featureCoverage ?? row.featureCoverage, "unknown")),
      stat("Calibrated", trustStatusLabel(summary.calibrationStatus || (Boolean(model.calibrated ?? row.calibrated) ? "ready" : "missing"))),
      stat("Backtest", trustStatusLabel(summary.backtestStatus || "missing")),
      stat("Snapshot", text(actionnetwork.snapshotFreshness ?? actionnetwork.status, "unknown")),
      stat("Labels", text(actionnetwork.trainableEligibility ?? actionnetwork.labelQuality, "not trainable")),
      stat("Workflow", text(runtime.workflowStatus, severity.label)),
      stat("Runtime", text(runtime.runtimeStatus, severity.label)),
      stat("Identity", trustStatusLabel(identity.identityConfidence)),
      stat("As-of audit", text(row.asOfAuditStatus ?? runtime.asOfAuditStatus, "not reported")),
      stat("Umpire", text(row.umpireStatus ?? row.umpire_context_status, "neutral fallback")),
    ]),
  ]);
}

export function renderShadowModelAudit(row: OutlierBoardRow, audit: ShadowAuditState = {}): HTMLElement {
  const market = rowMarketKey(row);
  if (audit.loading) {
    return h("article", { className: "ob-rail-card ob-shadow-audit" }, [
      h("h3", { text: "Experimental Shadow Model" }),
      h("p", { className: "ob-muted", text: "Loading shadow model audit." }),
    ]);
  }
  if (audit.error) {
    return h("article", { className: "ob-rail-card ob-shadow-audit" }, [
      h("h3", { text: "Experimental Shadow Model" }),
      h("p", { className: "ob-muted", text: "Shadow audit unavailable. Backend audit data could not be loaded safely." }),
    ]);
  }
  const summary = findMarket(audit.summary?.markets, market);
  const readiness = findMarket(audit.readiness?.markets, market);
  const gates = findMarket(audit.gates?.markets, market);
  const freshness = findMarket(audit.freshness?.markets, market);
  const selected = mergeAuditMarket(summary, readiness, gates, freshness);
  if (!selected) {
    return h("article", { className: "ob-rail-card ob-shadow-audit" }, [
      h("h3", { text: "Experimental Shadow Model" }),
      h("p", { className: "ob-muted", text: "No Sprint 19 shadow model for this market yet." }),
      h("div", { className: "ob-chip-row is-rail" }, [
        h("span", { className: "ob-pill ob-pill-mini is-watch", text: "Research only" }),
        h("span", { className: "ob-pill ob-pill-mini is-risk", text: "Not actionable" }),
      ]),
    ]);
  }
  const hardBlockers = stringList(selected.hardBlockers).length ? stringList(selected.hardBlockers) : stringList(selected.blockers);
  const softWarnings = [...stringList(selected.softWarnings), ...stringList(selected.warnings)];
  const gateStatus = text(selected.productionGateStatus || selected.gateSummary?.status, hardBlockers.length ? "blocked" : "manual_review_required");
  const manualGovernance = selected.gateSummary?.manualGovernanceRequired || hardBlockers.includes("manual_governance_review_required") || stringList(selected.blockers).includes("manual_governance_review_required");
  const validation = validationLabel(selected.validationDates);
  const freshnessInfo = objectValue(selected.freshness);
  const freshnessStatus = text(selected.freshnessStatus ?? freshnessInfo.freshnessStatus, "Unknown");
  const generatedAt = text(selected.generatedAt ?? freshnessInfo.generatedAt, "Not reported");
  const artifactAge = artifactAgeLabel(selected.artifactAgeHours ?? freshnessInfo.artifactAgeHours);
  const latestValidationDate = text(selected.latestValidationDate ?? freshnessInfo.latestValidationDate, "Not reported");
  const freshnessWarnings = dedupe([...stringList(freshnessInfo.warnings), ...stringList(selected.warnings)]);
  const recommendedNextStep = text(selected.recommendedNextStep ?? freshnessInfo.recommendedNextStep, "Manual governance review is required before any production workflow can be considered.");
  const gateChecks = Array.isArray(selected.gateChecks) ? selected.gateChecks : [];
  return h("article", { className: "ob-rail-card ob-shadow-audit" }, [
    h("p", { className: "ob-kicker", text: "Research-only model audit" }),
    h("h3", { text: "Experimental Shadow Model" }),
    h("div", { className: "ob-chip-row is-rail" }, [
      h("span", { className: "ob-pill ob-pill-mini is-watch", text: "Experimental" }),
      h("span", { className: "ob-pill ob-pill-mini is-watch", text: "Shadow" }),
      h("span", { className: "ob-pill ob-pill-mini is-risk", text: "Research only" }),
      h("span", { className: "ob-pill ob-pill-mini is-risk", text: "Not actionable" }),
      h("span", { className: "ob-pill ob-pill-mini is-risk", text: "Not production eligible" }),
      manualGovernance ? h("span", { className: "ob-pill ob-pill-mini is-risk", text: "Manual governance required" }) : null,
    ]),
    h("div", { className: "ob-stat-grid" }, [
      stat("Market", marketLabel(market)),
      stat("Model key", text(selected.modelKey, "calibrated_logistic")),
      stat("Stage", text(selected.modelStage, "shadow")),
      stat("Readiness", text(selected.readinessLabel, "Experimental")),
      stat("Action", text(selected.action, "Research")),
      stat("Production eligible", selected.productionEligible ? "Yes" : "No"),
      stat("Gate status", gateStatus),
      stat("Manual governance", manualGovernance ? "Required" : "Not reported"),
      stat("Evaluated rows", metricText(selected.evaluatedRows, "Not reported")),
      stat("AUC", metricText(selected.auc)),
      stat("Brier", metricText(selected.brierScore)),
      stat("Log loss", metricText(selected.logLoss)),
      stat("Expected calibration error", metricText(selected.expectedCalibrationError)),
      stat("Freshness status", freshnessStatus),
      stat("Generated at", generatedAt),
      stat("Artifact age", artifactAge),
      stat("Latest validation date", latestValidationDate),
      stat("Validation", validation),
      stat("Stake units", Number(selected.stakeUnits || 0) === 0 ? "0, research only" : "Withheld"),
      stat("Bet action", selected.betActionAllowed ? "Disabled by research UI" : "Disabled"),
    ]),
    hardBlockers.length ? h("p", { className: "ob-muted", text: `Hard blockers: ${hardBlockers.join(", ")}` }) : h("p", { className: "ob-muted", text: "Hard blockers: none reported by audit." }),
    softWarnings.length ? h("p", { className: "ob-muted", text: `Soft warnings: ${dedupe(softWarnings).join(", ")}` }) : h("p", { className: "ob-muted", text: "Soft warnings: none reported by audit." }),
    freshnessWarnings.length ? h("p", { className: "ob-muted", text: `Freshness warnings: ${freshnessWarnings.join(", ")}` }) : h("p", { className: "ob-muted", text: "Freshness warnings: none reported by audit." }),
    h("p", { className: "ob-muted", text: `Next: ${recommendedNextStep}` }),
    selected.artifactStatus && selected.artifactStatus !== "ready" ? h("p", { className: "ob-muted", text: `Artifact warning: ${selected.artifactStatus}. Metrics are not fabricated when artifacts are stale or missing.` }) : null,
    renderGateChecks(gateChecks),
  ]);
}

function renderGateChecks(gateChecks: NonNullable<ShadowReadinessMarket["gateChecks"]>): HTMLElement {
  if (!gateChecks.length) {
    return h("p", { className: "ob-muted", text: "Gate checks unavailable for this audit response." });
  }
  return h("details", { className: "ob-gate-checks" }, [
    h("summary", { text: `Gate checks (${gateChecks.length})` }),
    h("div", { className: "ob-gate-list" }, gateChecks.map((check) => {
      const key = text(check.label || check.name || check.key, "Gate check");
      const status = text(check.status || (check.passed ? "pass" : "blocked"), "unknown");
      const reason = text(check.reason || check.message || check.details, "");
      return h("div", { className: "ob-gate-row" }, [
        h("strong", { text: key }),
        h("span", { text: status }),
        reason ? h("em", { text: reason }) : null,
      ]);
    })),
  ]);
}

function renderServerDetail(state: { detail?: Record<string, unknown>; error?: string; loading?: boolean }): HTMLElement {
  if (state.loading) {
    return h("article", { className: "ob-rail-card" }, [h("h3", { text: "Server drilldown" }), h("p", { className: "ob-muted", text: "Loading prop-detail contract…" })]);
  }
  if (state.error) {
    return h("article", { className: "ob-rail-card" }, [h("h3", { text: "Server drilldown" }), h("p", { className: "ob-muted", text: `Unavailable: ${state.error}` })]);
  }
  const detail = state.detail || {};
  const overview = objectValue(detail.overview);
  const priceComparison = objectValue(detail.priceComparison);
  const modelExplanation = objectValue(detail.modelExplanation);
  const riskContext = objectValue(detail.riskContext);
  if (!Object.keys(detail).length) {
    return h("article", { className: "ob-rail-card" }, [h("h3", { text: "Server drilldown" }), h("p", { className: "ob-muted", text: "No additional drilldown was returned for this prop." })]);
  }
  return h("article", { className: "ob-rail-card" }, [
    h("h3", { text: "Server drilldown" }),
    h("div", { className: "ob-stat-grid" }, [
      stat("Book", text(priceComparison.bestBook ?? priceComparison.book ?? overview.book, "Market")),
      stat("Fair", percent(priceComparison.fairProbability ?? modelExplanation.probability ?? overview.modelProbability)),
      stat("Risk", text(riskContext.label ?? riskContext.tier ?? riskContext.level, "Research")),
      stat("Lookup", text(detail.lookupMode ?? overview.lookupMode, "snapshot")),
    ]),
    h("p", { className: "ob-muted", text: text(modelExplanation.summary ?? riskContext.summary ?? detail.summary, "Detail API responded; use this rail as the isolated drilldown surface.") }),
  ]);
}

function detailQuery(row: OutlierBoardRow, date: string): URLSearchParams {
  const params = new URLSearchParams();
  const propKey = rowPropKey(row);
  if (propKey) params.set("propKey", propKey);
  params.set("market", rowMarketKey(row));
  params.set("player", rowPlayer(row));
  params.set("team", text(row.team, ""));
  params.set("opponent", text(row.opponent ?? row.home, ""));
  params.set("line", text(rowLine(row), ""));
  params.set("americanOdds", text(rowOdds(row), ""));
  if (date) params.set("date", date);
  return params;
}

function stat(label: string, value: unknown): HTMLElement {
  return h("div", { className: "ob-stat" }, [h("span", { text: label }), h("strong", { text: value })]);
}

function exposureCopy(exposure: unknown): string {
  const source = exposure && typeof exposure === "object" ? (exposure as Record<string, unknown>) : {};
  const exposureValue = number(source.totalStakeUnits, 0).toFixed(2);
  return `${exposureValue} active exposure. Research-only saves stay at zero exposure.`;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function arrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => text(item, "")).filter(Boolean) : [];
}

function findMarket<T extends { market?: string }>(markets: T[] | undefined, market: string): T | undefined {
  return Array.isArray(markets) ? markets.find((item) => item.market === market) : undefined;
}

function mergeAuditMarket(...markets: Array<Record<string, unknown> | undefined>): ShadowReadinessMarket | null {
  const selected = markets.filter(Boolean);
  return selected.length ? Object.assign({}, ...selected) as ShadowReadinessMarket : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => text(item, "")).filter(Boolean) : [];
}

function metricText(value: unknown, fallback = "--"): string {
  if (value === null || value === undefined || value === "") return fallback;
  const parsed = number(value, Number.NaN);
  if (!Number.isFinite(parsed)) return text(value, fallback);
  return Number.isInteger(parsed) ? String(parsed) : parsed.toFixed(3);
}

function artifactAgeLabel(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not reported";
  const parsed = number(value, Number.NaN);
  if (!Number.isFinite(parsed)) return text(value, "Not reported");
  return `${parsed.toFixed(parsed >= 10 ? 1 : 2)} hours`;
}

function validationLabel(dates: unknown): string {
  const values = stringList(dates);
  if (!values.length) return "Not reported";
  if (values.length === 1) return `${values[0]} (1 date)`;
  return `${values[0]} to ${values[values.length - 1]} (${values.length} dates)`;
}

function dedupe(values: string[]): string[] {
  return Array.from(new Set(values));
}

export function emptyRail(): HTMLElement {
  return h("article", { className: "ob-rail-card" }, [
    h("p", { className: "ob-kicker", text: "Research rail" }),
    h("h2", { text: "Select a prop" }),
    h("p", { text: "Open a board row to inspect price, model, freshness, and pick exposure without leaving the board." }),
  ]);
}
