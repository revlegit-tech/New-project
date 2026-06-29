import { jsonFetch } from "../../shared/api/client";
import { clear, h } from "../../shared/components/dom";
import { formatOdds, number, percent, signedPercent, text } from "../../shared/formatting";
import { marketLabel } from "../../shared/markets/markets";
import { badgeToneClass, freshnessSeverity, rowActionability, rowFreshness, rowReadiness, rowTrustChips, rowTrustCopy, rowTrustSummary, trustStatusLabel } from "../trust";
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
    try {
      const query = detailQuery(row, context.date);
      const { payload } = await jsonFetch<PropDetailPayload>(`/api/prop-detail?${query.toString()}`);
      if (this.requestSequence !== sequence || this.currentRow !== row) return;
      this.render(row, context, { detail: payload?.detail || payload, loading: false });
    } catch (error) {
      if (this.requestSequence !== sequence || this.currentRow !== row) return;
      this.render(row, context, { error: error instanceof Error ? error.message : String(error), loading: false });
    }
  }

  private render(row: OutlierBoardRow, context: DetailRailContext, state: { detail?: Record<string, unknown>; error?: string; loading?: boolean } = {}): void {
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
      renderRowTrustDetail(row, context.status),
      renderServerDetail(state),
      h("article", { className: "ob-rail-card" }, [
        h("h3", { text: "Picks & exposure" }),
        h("p", { text: "Research-only saves default to 0 units and do not alter model backtests." }),
        h("button", { className: "ob-button is-primary", type: "button", text: text(context.savePickLabel, "Add research pick"), dataset: { action: "save-pick" } }),
        h("p", { id: "savePickStatus", className: "ob-muted", text: exposureCopy(context.exposure) }),
      ]),
    ]);
  }
}

function renderRowTrustDetail(row: OutlierBoardRow, status: unknown): HTMLElement {
  const trust = row.trust || {};
  const model = objectValue(trust.model);
  const actionnetwork = objectValue(trust.actionnetwork);
  const runtime = objectValue(trust.runtime);
  const severity = freshnessSeverity(status);
  const summary = rowTrustSummary(row);
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
      stat("As-of audit", text(row.asOfAuditStatus ?? runtime.asOfAuditStatus, "not reported")),
      stat("Umpire", text(row.umpireStatus ?? row.umpire_context_status, "neutral fallback")),
    ]),
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
  const units = number(source.totalStakeUnits, 0).toFixed(2);
  return `${units}u active exposure. Research-only picks stay at 0u.`;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function emptyRail(): HTMLElement {
  return h("article", { className: "ob-rail-card" }, [
    h("p", { className: "ob-kicker", text: "Research rail" }),
    h("h2", { text: "Select a prop" }),
    h("p", { text: "Open a board row to inspect price, model, freshness, and pick exposure without leaving the board." }),
  ]);
}
