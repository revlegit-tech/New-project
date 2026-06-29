import { jsonFetch } from "../../shared/api/client";
import { clear, h } from "../../shared/components/dom";
import { formatOdds, signedPercent, text } from "../../shared/formatting";

export interface ResearchReportCard {
  player?: string;
  matchup?: string;
  marketDisplay?: string;
  side?: string;
  line?: string | number | null;
  americanOdds?: string | number | null;
  grade?: string;
  score?: number;
  riskBucket?: string;
  edgePercent?: number;
  decisionLabel?: string;
  readinessLabel?: string;
  actionLabel?: string;
  marketCapabilityStatus?: string;
  modelProductionEligible?: boolean;
  calibrationStatus?: string;
  backtestStatus?: string;
  missingDataCount?: number;
  warningCount?: number;
  actionabilityReason?: string;
  reasons?: string[];
}

export interface ResearchReportSection {
  key: string;
  title: string;
  description?: string;
  publishTier?: string;
  cardCount?: number;
  cards?: ResearchReportCard[];
  emptyState?: string;
}

export interface ResearchReportPayload {
  status?: string;
  date?: string;
  product?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  sections?: ResearchReportSection[];
  pricing?: Record<string, unknown>;
  publishPlan?: Array<Record<string, unknown>>;
  meta?: Record<string, unknown>;
}

export async function loadResearchReport(date: string): Promise<ResearchReportPayload> {
  const params = new URLSearchParams({ limit: "5000" });
  if (date) params.set("date", date);
  const { payload } = await jsonFetch<ResearchReportPayload>(`/api/research/report?${params.toString()}`);
  return payload;
}

export function renderResearchReportLoading(host: HTMLElement | null): void {
  clear(host, [
    h("div", { className: "ob-report-head" }, [
      h("div", {}, [h("p", { className: "ob-kicker", text: "RevLegit MLB Edge" }), h("h2", { text: "Daily report" }), h("p", { className: "ob-muted", text: "Packaging the EdgeBoard into free preview, paid board, lotto, and fade sections…" })]),
      h("button", { className: "ob-button is-ghost", type: "button", text: "Generate report", dataset: { action: "reload-report" } }),
    ]),
  ]);
}

export function renderResearchReportError(host: HTMLElement | null, message: string): void {
  clear(host, [
    h("div", { className: "ob-report-head" }, [
      h("div", {}, [h("p", { className: "ob-kicker", text: "RevLegit MLB Edge" }), h("h2", { text: "Daily report unavailable" }), h("p", { className: "ob-muted", text: message })]),
      h("button", { className: "ob-button is-ghost", type: "button", text: "Retry", dataset: { action: "reload-report" } }),
    ]),
  ]);
}

export function renderResearchReport(host: HTMLElement | null, report: ResearchReportPayload): void {
  const sections = Array.isArray(report.sections) ? report.sections : [];
  const summary = report.summary || {};
  const product = report.product || {};
  const pricing = report.pricing || {};
  clear(host, [
    h("div", { className: "ob-report-head" }, [
      h("div", {}, [
        h("p", { className: "ob-kicker", text: text(product.name, "RevLegit MLB Edge") }),
        h("h2", { text: "Daily MLB research report" }),
        h("p", { className: "ob-muted", text: text(product.positioning, "MLB-only prop research generated from the production board.") }),
      ]),
      h("button", { className: "ob-button is-ghost", type: "button", text: "Regenerate", dataset: { action: "reload-report" } }),
    ]),
    h("div", { className: "ob-report-stats" }, [
      reportStat("Board rows", summary.rowCount),
      reportStat("Positive edges", summary.positiveEdgeRows),
      reportStat("Core", summary.coreRows),
      reportStat("Lotto", summary.lottoRows),
      reportStat("Production eligible", summary.productionEligibleRows),
      reportStat("Missing data", summary.missingDataRows),
    ]),
    renderReadinessSummary(report),
    h("div", { className: "ob-report-sections" }, sections.map(renderSection)),
    h("div", { className: "ob-report-footer" }, [
      h("strong", { text: "Publishing guardrail" }),
      h("span", { text: text(product.disclaimer, "Research only. Outcomes are uncertain. Verify live sportsbook lines and use responsible bankroll rules.") }),
    ]),
  ]);
}

function renderReadinessSummary(report: ResearchReportPayload): HTMLElement {
  const summary = report.summary || {};
  const trust = report.trust || {};
  const runtime = typeof trust.runtimeReadiness === "object" && trust.runtimeReadiness ? trust.runtimeReadiness as Record<string, unknown> : {};
  const gameMarkets = report.gameMarketEnrichment || {};
  const eligibleProduction = Array.isArray(summary.eligibleProductionMarkets) ? summary.eligibleProductionMarkets.length : 0;
  return h("article", { className: "ob-report-readiness" }, [
    h("h3", { text: "Readiness summary" }),
    h("div", { className: "ob-report-stats" }, [
      reportStat("Daily collector", text(runtime.collectorStatus ?? summary.collectorStatus, "not reported")),
      reportStat("Data sources", text(runtime.dataSourceCapabilityStatus ?? summary.boardDataConfidence, "missing")),
      reportStat("Feature store", runtime.featureStoreReady === true ? "ready" : "not ready"),
      reportStat("Model readiness", runtime.readyForProductionTraining === true ? "production ready" : "research only"),
      reportStat("Calibration", compactCounts(summary.calibrationStatusCounts)),
      reportStat("Backtest", compactCounts(summary.backtestStatusCounts)),
      reportStat("Baseline markets", Array.isArray(summary.eligibleBaselineMarkets) ? summary.eligibleBaselineMarkets.length : 0),
      reportStat("Production markets", eligibleProduction || "0"),
      reportStat("Game markets", text(gameMarkets.matchedRows, "0")),
      reportStat("Umpire", text(summary.umpireStatus, "not reported")),
    ]),
    h("p", { className: "ob-muted", text: eligibleProduction ? "Production eligible markets are listed by the readiness contract." : "No markets are production eligible yet." }),
  ]);
}

function renderSection(section: ResearchReportSection): HTMLElement {
  const cards = Array.isArray(section.cards) ? section.cards : [];
  return h("article", { className: "ob-report-section" }, [
    h("div", { className: "ob-report-section-title" }, [
      h("div", {}, [h("h3", { text: section.title }), h("p", { text: text(section.description, "Section generated from current board rows.") })]),
      h("span", { className: "ob-pill", text: `${cards.length} · ${text(section.publishTier, "premium")}` }),
    ]),
    ...(cards.length ? cards.slice(0, 3).map(renderCard) : [h("p", { className: "ob-muted", text: text(section.emptyState, "No rows cleared this section today.") })]),
  ]);
}

function renderCard(card: ResearchReportCard): HTMLElement {
  const reason = Array.isArray(card.reasons) && card.reasons.length ? card.reasons[0] : "Open the prop rail before publishing this as a final recommendation.";
  return h("div", { className: "ob-report-card" }, [
    h("div", {}, [
      h("strong", { text: text(card.player, "MLB") }),
      h("span", { text: `${text(card.marketDisplay, "Prop")} · ${text(card.side, "Over")} ${text(card.line, "")}`.trim() }),
      h("em", { text: text(card.matchup, "Matchup pending") }),
    ]),
    h("div", { className: "ob-report-card-meta" }, [
      h("span", { className: `ob-pill ${gradeTone(card.grade)}`, text: text(card.grade, "--") }),
      h("span", { className: "ob-pill", text: `${text(card.score, "0")}/100` }),
      h("span", { className: "ob-pill", text: formatOdds(card.americanOdds) }),
      h("span", { className: "ob-pill", text: signedPercent(card.edgePercent) }),
      h("span", { className: "ob-pill", text: text(card.actionLabel, "Research only") }),
      h("span", { className: "ob-pill", text: card.modelProductionEligible ? "Production eligible" : "Research only" }),
      h("span", { className: "ob-pill", text: `Cal ${text(card.calibrationStatus, "missing")}` }),
      h("span", { className: "ob-pill", text: `BT ${text(card.backtestStatus, "missing")}` }),
    ]),
    h("p", { className: "ob-muted", text: text(card.actionabilityReason, reason) }),
  ]);
}

function reportStat(label: string, value: unknown): HTMLElement {
  return h("div", { className: "ob-stat" }, [h("span", { text: label }), h("strong", { text: text(value, "0") })]);
}

function gradeTone(grade: unknown): string {
  const raw = text(grade, "").toLowerCase();
  if (raw.startsWith("a")) return "is-good";
  if (raw.startsWith("b") || raw.startsWith("c")) return "is-watch";
  return "is-risk";
}

function compactCounts(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "missing";
  const entries = Object.entries(value as Record<string, unknown>).filter(([, count]) => Number(count) > 0);
  return entries.length ? entries.map(([key, count]) => `${key}:${count}`).join(" ") : "missing";
}
