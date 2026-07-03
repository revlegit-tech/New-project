import { number, text } from "../../shared/formatting";
import { ActionabilityStatus, OutlierBoardRow, TrustTone } from "../board/types";

export interface NormalizedPropIdentity {
  player: string;
  team: string;
  opponent: string;
  market: string;
  line: unknown;
  side: string;
  book: string;
  identityConfidence: string;
  identityWarnings: string[];
  playerTeamVerified: boolean;
  opponentVerified: boolean;
  attributionStatus: string;
  attributionCorrectionApplied: boolean;
  attributionCorrectionReason: string;
  playerTeamEvidenceStatus: string;
}

export interface NormalizedModelEdge {
  edgePercent: number | null;
  modelProbabilityPercent: unknown;
  impliedProbabilityPercent: unknown;
  tone: "positive" | "neutral" | "negative";
}

export interface NormalizedReadiness {
  label: string;
  status: string;
  tone: TrustTone;
  canAct: boolean;
  warnings: string[];
}

export interface NormalizedFreshness {
  label: string;
  status: string;
  tone: TrustTone;
  ageSeconds?: number;
  source: string;
}

export interface NormalizedActionability {
  label: string;
  status: ActionabilityStatus;
  tone: TrustTone;
  suggestedStake: string;
  stakeUnits: number;
  reason: string;
}

export interface TrustChip {
  label: string;
  tone: TrustTone;
  title: string;
}

export interface RowTrustSummary {
  actionLabel: string;
  marketCapabilityStatus: string;
  modelProductionEligible: boolean;
  productionStatus: string;
  productionGateStatus: string;
  productionGateReasons: string[];
  calibrationStatus: string;
  backtestStatus: string;
  freshnessStatus: string;
  gameMarketStatus: string;
  missingDataCount: number;
  warningCount: number;
  canShowConfidentPick: boolean;
  hasCriticalMissingData: boolean;
  actionabilityReason: string;
  productionEligibleReason: string;
  missingFeatureGroups: string[];
  missingDataSummary: string;
}

export interface RowBoardTrustSurface {
  trustTier: string;
  trustScore: number | null;
  calibrationStatus: string;
  probabilityGuardrailStatus: string;
  contextReadinessStatus: string;
  unscoredReason: string;
  marketCapabilityStatus: string;
  chips: TrustChip[];
}

export function rowPropIdentity(row: OutlierBoardRow): NormalizedPropIdentity {
  const identity = objectValue(row.trust?.propIdentity);
  return {
    player: text(identity.player ?? row.player ?? row.playerName ?? row.team, "MLB"),
    team: text(identity.team ?? row.team ?? row.away, ""),
    opponent: text(identity.opponent ?? row.opponent ?? row.home, ""),
    market: text(identity.market ?? row.market ?? row.baseMarket, ""),
    line: identity.line ?? row.line ?? row.propLine,
    side: text(identity.side ?? row.side ?? row.rawLabel ?? row.pickSide, "Over"),
    book: text(identity.book ?? row.book ?? row.sportsbook ?? row.bestBook, "Market"),
    identityConfidence: normalizedStatus(identity.identityConfidence ?? row.identityConfidence ?? "unknown") || "unknown",
    identityWarnings: arrayText(identity.identityWarnings ?? row.identityWarnings ?? row.attributionWarnings),
    playerTeamVerified: Boolean(identity.playerTeamVerified ?? row.playerTeamVerified),
    opponentVerified: Boolean(identity.opponentVerified ?? row.opponentVerified),
    attributionStatus: normalizedStatus(identity.attributionStatus ?? row.attributionStatus),
    attributionCorrectionApplied: Boolean(identity.attributionCorrectionApplied ?? row.attributionCorrectionApplied),
    attributionCorrectionReason: text(identity.attributionCorrectionReason ?? row.attributionCorrectionReason, ""),
    playerTeamEvidenceStatus: normalizedStatus(identity.playerTeamEvidenceStatus ?? row.playerTeamEvidenceStatus),
  };
}

export function rowModelEdge(row: OutlierBoardRow): NormalizedModelEdge {
  const modelEdge = objectValue(row.trust?.modelEdge);
  const rawEdge = modelEdge.edgePercent ?? row.edgePercent;
  const edge = rawEdge === null || rawEdge === undefined || rawEdge === "" ? null : number(rawEdge, Number.NaN);
  const normalizedEdge = Number.isFinite(edge) ? edge : null;
  const explicitTone = text(modelEdge.tone, "");
  return {
    edgePercent: normalizedEdge,
    modelProbabilityPercent: modelEdge.modelProbabilityPercent ?? row.modelProbabilityPercent ?? row.modelProbability ?? row.probabilityPercent ?? row.probability ?? row.prob,
    impliedProbabilityPercent: modelEdge.impliedProbabilityPercent ?? row.impliedProbabilityPercent ?? row.sportsbookImpliedPercent ?? row.impliedProbability ?? row.impliedPercent,
    tone: explicitTone === "positive" || explicitTone === "neutral" || explicitTone === "negative" ? explicitTone : normalizedEdge !== null && normalizedEdge > 0 ? "positive" : normalizedEdge !== null && normalizedEdge < 0 ? "negative" : "neutral",
  };
}

export function rowReadiness(row: OutlierBoardRow): NormalizedReadiness {
  const trust = objectValue(row.trust?.readiness);
  const modelCard = objectValue(row.modelCard);
  const label = text(trust.label ?? row.readinessLabel ?? modelCard.readinessLabel ?? modelCard.status ?? row.readiness ?? row.confidence, "Research only");
  const status = text(trust.status ?? row.productionStatus ?? modelCard.productionStatus ?? label, label).toLowerCase().replace(/\s+/g, "_");
  return {
    label,
    status,
    tone: normalizeTone(trust.tone, readinessToneFromLabel(label, status, Boolean(trust.canShowConfidentPick ?? row.canShowConfidentPick ?? modelCard.canShowConfidentPick))),
    canAct: Boolean(trust.canShowConfidentPick ?? row.canShowConfidentPick ?? modelCard.canShowConfidentPick),
    warnings: Array.isArray(trust.warnings) ? trust.warnings.map((item) => text(item, "")).filter(Boolean) : Array.isArray(row.trustWarnings) ? row.trustWarnings.map((item) => text(item, "")).filter(Boolean) : [],
  };
}

export function rowFreshness(row: OutlierBoardRow, fallback = "Research"): NormalizedFreshness {
  const freshness = objectValue(row.freshness);
  const status = text(freshness.status ?? row.freshnessStatus ?? row.dataFreshness ?? fallback, fallback).toLowerCase();
  const label = text(freshness.label ?? statusLabel(status) ?? fallback, fallback);
  return {
    label,
    status,
    tone: normalizeTone(freshness.tone, freshnessToneFromStatus(status, label)),
    ageSeconds: typeof freshness.ageSeconds === "number" ? freshness.ageSeconds : undefined,
    source: text(freshness.source ?? row.freshnessSource ?? "", ""),
  };
}

export function rowActionability(row: OutlierBoardRow): NormalizedActionability {
  const actionability = objectValue(row.trust?.actionability);
  const readiness = rowReadiness(row);
  const edge = rowModelEdge(row);
  const decision = text(row.decisionLabel ?? row.recommendation ?? "", "");
  const status = normalizeActionabilityStatus(actionability.status, decision, readiness, edge.edgePercent);
  const label = text(actionability.label ?? actionabilityLabel(status, decision), actionabilityLabel(status, decision));
  const productionEligible = Boolean(row.modelProductionEligible ?? objectValue(row.trust?.readiness).modelProductionEligible);
  const stakeUnits = productionEligible && typeof actionability.stakeUnits === "number" ? actionability.stakeUnits : 0;
  return {
    label,
    status,
    tone: actionabilityTone(status),
    suggestedStake: productionEligible ? text(actionability.suggestedStake ?? row.suggestedStake ?? "Research only", "Research only") : "0u until production eligible",
    stakeUnits,
    reason: text(actionability.reason ?? firstReason(row) ?? "", ""),
  };
}

export function rowTrustCopy(row: OutlierBoardRow): string {
  const identity = rowPropIdentity(row);
  if (identity.identityConfidence === "medium" || identity.identityConfidence === "weak" || identity.identityConfidence === "unknown") {
    return identity.identityWarnings[0] || "Identity is inferred from board context. Research only.";
  }
  const readiness = rowReadiness(row);
  const actionability = rowActionability(row);
  if (actionability.status === "actionable" && readiness.canAct) {
    return "This prop clears model-readiness gates, but line movement and limits still need a final book check.";
  }
  if (actionability.status === "watchlist") {
    if (actionability.label.toLowerCase().includes("research") || !readiness.canAct) {
      return "This prop has a positive research lean from an experimental projection, but it should stay on the watchlist until model readiness gates are complete.";
    }
    return "This prop has a positive model lean, but it should stay on the watchlist until the readiness gates are complete.";
  }
  return "This prop is visible for research but should stay 0u until data and model gates are satisfied.";
}

export function rowTrustChips(row: OutlierBoardRow): TrustChip[] {
  return [
    actionLabelChip(row),
    marketCapabilityChip(row),
    productionEligibilityChip(row),
    productionGateChip(row),
    productionStatusChip(row),
    calibrationChip(row),
    backtestChip(row),
    freshnessChip(row),
    gameMarketChip(row),
    identityChip(row),
    missingDataChip(row),
    warningChip(row),
    modelTrustChip(row),
    featureCoverageChip(row),
    actionNetworkTrustChip(row),
  ].filter(Boolean) as TrustChip[];
}

export function rowBoardTrustSurface(row: OutlierBoardRow): RowBoardTrustSurface {
  const explainability = objectValue(row.explainability);
  const calibration = objectValue(explainability.calibration);
  const context = objectValue(explainability.context);
  const guardrails = objectValue(explainability.guardrails);
  const trust = objectValue(row.trust);
  const trustTier = normalizedStatus(row.trustTier ?? explainability.trustTier) || "unknown";
  const probabilityGuardrailStatus = normalizedStatus(row.probabilityGuardrailStatus ?? guardrails.probabilityGuardrailStatus) || "unknown";
  const unscoredReason = visibleUnscoredReason(row, trustTier, probabilityGuardrailStatus, guardrails);
  const surface = {
    trustTier,
    trustScore: trustScore(row.trustScore ?? explainability.trustScore),
    calibrationStatus: normalizedStatus(row.calibrationStatus ?? calibration.calibrationStatus) || "unknown",
    probabilityGuardrailStatus,
    contextReadinessStatus: normalizedStatus(row.contextReadinessStatus ?? context.contextReadinessStatus) || "unknown",
    unscoredReason,
    marketCapabilityStatus: normalizedStatus(row.marketCapabilityStatus ?? trust.marketCapabilityStatus) || "unknown",
  };
  return {
    ...surface,
    chips: [
      trustTierChip(surface.trustTier, surface.trustScore),
      calibrationStatusChip(surface.calibrationStatus),
      probabilityGuardrailStatusChip(surface.probabilityGuardrailStatus),
      contextReadinessStatusChip(surface.contextReadinessStatus),
      unscoredReasonChip(surface.unscoredReason),
      marketCapabilityStatusChip(surface.marketCapabilityStatus),
    ],
  };
}

export function rowAttributionChip(row: OutlierBoardRow): TrustChip | null {
  const identity = rowPropIdentity(row);
  if (identity.attributionStatus === "conflict") {
    return { label: "Possible team mismatch", tone: "risk", title: identity.identityWarnings[0] || "Player/team attribution conflicts with local evidence." };
  }
  if (identity.attributionStatus === "ambiguous") {
    return { label: "Ambiguous player", tone: "risk", title: identity.identityWarnings[0] || "Player identity could not be uniquely resolved." };
  }
  if (identity.attributionStatus === "invalid_player_label") {
    return { label: "Invalid player label", tone: "risk", title: identity.identityWarnings[0] || "Market label could not be safely treated as a player." };
  }
  if (identity.attributionCorrectionApplied || identity.attributionStatus === "corrected") {
    return { label: "Corrected", tone: "good", title: identity.attributionCorrectionReason || "Source mismatch corrected by roster evidence." };
  }
  if (Boolean(row.contextBlockedByAttribution)) {
    return { label: "Context limited", tone: "risk", title: identity.identityWarnings[0] || "Model/context join blocked by attribution confidence." };
  }
  if (identity.attributionStatus === "source_missing") {
    return { label: "Source missing team", tone: "watch", title: identity.identityWarnings[0] || "Source team or opponent was missing." };
  }
  return null;
}

export function rowTrustSummary(row: OutlierBoardRow): RowTrustSummary {
  const trust = objectValue(row.trust);
  const readiness = objectValue(trust.readiness);
  const actionability = objectValue(trust.actionability);
  const productionGate = objectValue(trust.productionGate);
  const freshness = rowFreshness(row, "Unknown");
  const missingFeatureGroups = arrayText(row.missingFeatureGroups ?? readiness.missingFeatureGroups);
  const missingDataCount = integer(row.missingDataCount ?? readiness.missingDataCount ?? missingFeatureGroups.length);
  const warningCount = integer(row.warningCount ?? (Array.isArray(row.trustWarnings) ? row.trustWarnings.length : readiness.warnings instanceof Array ? readiness.warnings.length : 0));
  const productionStatus = normalizedStatus(row.productionStatus ?? readiness.status ?? row.modelState);
  const productionGateStatus = normalizedStatus(row.productionGateStatus ?? productionGate.status ?? readiness.productionGateStatus);
  const productionGateReasons = arrayText(row.productionGateReasons ?? productionGate.reasons ?? readiness.productionGateReasons);
  const calibrationStatus = normalizedStatus(row.calibrationStatus ?? readiness.calibrationStatus ?? trust.calibrationStatus);
  const backtestStatus = normalizedStatus(row.backtestStatus ?? readiness.backtestStatus ?? trust.backtestStatus);
  const marketCapabilityStatus = normalizedStatus(row.marketCapabilityStatus ?? trust.marketCapabilityStatus);
  return {
    actionLabel: text(row.actionLabel ?? trust.actionLabel ?? actionability.label, "Research only"),
    marketCapabilityStatus,
    modelProductionEligible: Boolean(row.productionEligible ?? productionGate.productionEligible ?? row.modelProductionEligible ?? readiness.modelProductionEligible),
    productionStatus,
    productionGateStatus,
    productionGateReasons,
    calibrationStatus,
    backtestStatus,
    freshnessStatus: normalizedStatus(freshness.status),
    gameMarketStatus: normalizedStatus(row.game_market_enrichment_status ?? row.gameMarketStatus),
    missingDataCount,
    warningCount,
    canShowConfidentPick: Boolean(row.canShowConfidentPick ?? readiness.canShowConfidentPick),
    hasCriticalMissingData: missingDataCount > 0,
    actionabilityReason: text(row.actionabilityReason ?? actionability.reason, "Research only because production model gates have not passed."),
    productionEligibleReason: text(row.productionEligibleReason ?? productionGate.copy, ""),
    missingFeatureGroups,
    missingDataSummary: text(row.missingDataSummary, missingDataCount ? "Missing data is present." : "No critical missing feature groups reported."),
  };
}

export function rowIsTrustedMarket(row: OutlierBoardRow): boolean {
  const summary = rowTrustSummary(row);
  return summary.modelProductionEligible &&
    summary.canShowConfidentPick &&
    summary.freshnessStatus !== "stale" &&
    summary.freshnessStatus !== "missing" &&
    summary.marketCapabilityStatus !== "unsupported" &&
    !summary.hasCriticalMissingData;
}

export function trustStatusLabel(value: unknown): string {
  const raw = normalizedStatus(value);
  if (!raw) return "Any";
  if (raw === "research_only") return "Research only";
  if (raw === "model_supported") return "Model supported";
  if (raw === "production_candidate") return "Experimental";
  return raw.split("_").filter(Boolean).map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");
}

export function uniqueTrustValues(rows: OutlierBoardRow[], getter: (row: OutlierBoardRow) => unknown): string[] {
  return Array.from(new Set(rows.map((row) => normalizedStatus(getter(row))).filter(Boolean))).sort();
}

export function uniqueBoardTrustValues(rows: OutlierBoardRow[], getter: (row: RowBoardTrustSurface) => unknown): string[] {
  return Array.from(new Set(rows.map((row) => normalizedStatus(getter(rowBoardTrustSurface(row)) || "unknown")).filter(Boolean))).sort();
}

export function modelTrustChip(row: OutlierBoardRow): TrustChip {
  const model = objectValue(row.trust?.model);
  const status = text(model.modelStatus ?? model.status ?? row.modelStatus ?? row.productionStatus, "").toLowerCase();
  if (status === "production") return { label: "Model Production", tone: "good", title: text(model.modelVersion ?? model.version, "Production model is active.") };
  if (status === "shadow") return { label: "Model Shadow", tone: "watch", title: "Shadow model is visible but cannot alter board ranking." };
  if (status === "candidate") return { label: "Production Gated", tone: "watch", title: "Candidate model has not cleared promotion gates." };
  return { label: "Model Unavailable", tone: "risk", title: "No production model is available for this row." };
}

function actionLabelChip(row: OutlierBoardRow): TrustChip {
  const label = rowTrustSummary(row).actionLabel || "Research only";
  const raw = label.toLowerCase();
  if (raw.includes("unsupported")) return { label: "Unsupported market", tone: "risk", title: "Unsupported market for model scoring." };
  if (raw.includes("stale")) return { label: "Data stale", tone: "risk", title: "Data stale; review after the next collector run." };
  if (raw.includes("no bet")) return { label: "No bet", tone: "risk", title: "This row does not clear the current research threshold." };
  if (raw.includes("model lean")) return { label: "Model lean", tone: "watch", title: "Positive model lean, still research-first." };
  if (raw.includes("watch")) return { label: "Watchlist", tone: "watch", title: "Watchlist row for manual review." };
  return { label: "Research only", tone: "watch", title: "Research only because production gates have not passed." };
}

function marketCapabilityChip(row: OutlierBoardRow): TrustChip {
  const status = rowTrustSummary(row).marketCapabilityStatus;
  if (status === "unsupported") return { label: "Unsupported market", tone: "risk", title: "No supported model scoring for this market." };
  if (status === "model_supported") return { label: "Model supported", tone: "good", title: "This market has model support." };
  return { label: "Research only", tone: "watch", title: "Market remains research-only." };
}

function trustTierChip(status: string, score: number | null): TrustChip {
  const suffix = score === null ? "" : ` ${score}`;
  if (status === "standard") return { label: `Standard${suffix}`, tone: "good", title: "Trust tier: standard." };
  if (status === "low" || status === "limited") return { label: trustStatusLabel(status), tone: "watch", title: `Trust tier: ${trustStatusLabel(status)}.` };
  if (status === "unscored") return { label: "Unscored", tone: "watch", title: "Model unavailable for this row." };
  if (status === "blocked") return { label: "Blocked", tone: "risk", title: "Trust guardrails blocked this row." };
  if (status === "unsupported") return { label: "Unsupported market", tone: "risk", title: "Unsupported market." };
  return { label: "Unknown", tone: "neutral", title: "Trust tier unavailable." };
}

function calibrationStatusChip(status: string): TrustChip {
  if (["applied", "ready", "ok", "passed", "calibrated"].includes(status)) return { label: "Calibrated", tone: "good", title: `Calibration: ${trustStatusLabel(status)}.` };
  if (status === "missing" || status === "not_available" || status === "unavailable") return { label: "Calibration unavailable", tone: "neutral", title: `Calibration: ${trustStatusLabel(status)}.` };
  if (status === "unknown") return { label: "Unknown", tone: "neutral", title: "Calibration status unavailable." };
  return { label: trustStatusLabel(status), tone: "watch", title: `Calibration: ${trustStatusLabel(status)}.` };
}

function probabilityGuardrailStatusChip(status: string): TrustChip {
  if (["ok", "ready", "passed", "standard"].includes(status)) return { label: "Guardrail ok", tone: "good", title: `Probability guardrail: ${trustStatusLabel(status)}.` };
  if (status === "blocked" || status === "invalid") return { label: "Blocked", tone: "risk", title: `Probability guardrail: ${trustStatusLabel(status)}.` };
  if (status === "unknown" || status === "missing") return { label: "Unknown", tone: "neutral", title: "Probability guardrail status unavailable." };
  return { label: trustStatusLabel(status), tone: "watch", title: `Probability guardrail: ${trustStatusLabel(status)}.` };
}

function contextReadinessStatusChip(status: string): TrustChip {
  if (["ready", "ok", "standard"].includes(status)) return { label: "Context ready", tone: "good", title: `Context readiness: ${trustStatusLabel(status)}.` };
  if (status === "limited" || status === "low" || status === "partial") return { label: "Context limited", tone: "watch", title: `Context readiness: ${trustStatusLabel(status)}.` };
  if (status === "blocked") return { label: "Blocked", tone: "risk", title: "Context readiness blocked." };
  if (status === "unknown" || status === "missing") return { label: "Unknown", tone: "neutral", title: "Context readiness unavailable." };
  return { label: trustStatusLabel(status), tone: "watch", title: `Context readiness: ${trustStatusLabel(status)}.` };
}

function unscoredReasonChip(status: string): TrustChip {
  if (!status || status === "none") return { label: "Scored", tone: "good", title: "No blocking unscored reason is displayed for this scored row." };
  if (status === "unsupported_market") return { label: "Unsupported market", tone: "risk", title: `Unscored reason: ${trustStatusLabel(status)}.` };
  if (status.includes("invalid") || status.includes("blocked")) return { label: "Blocked", tone: "risk", title: `Unscored reason: ${trustStatusLabel(status)}.` };
  return { label: "Unscored", tone: "watch", title: `Unscored reason: ${trustStatusLabel(status)}.` };
}

function marketCapabilityStatusChip(status: string): TrustChip {
  if (status === "model_supported") return { label: "Model supported", tone: "good", title: "Market capability: model supported." };
  if (status === "unsupported") return { label: "Unsupported market", tone: "risk", title: "Market capability: unsupported." };
  if (status === "unknown" || status === "missing") return { label: "Unknown", tone: "neutral", title: "Market capability unavailable." };
  return { label: trustStatusLabel(status), tone: "watch", title: `Market capability: ${trustStatusLabel(status)}.` };
}

function productionEligibilityChip(row: OutlierBoardRow): TrustChip {
  const summary = rowTrustSummary(row);
  if (summary.modelProductionEligible && summary.canShowConfidentPick) {
    return { label: "Production eligible", tone: "good", title: summary.productionEligibleReason || "Production eligibility gates passed." };
  }
  return { label: "Research only", tone: "watch", title: summary.productionEligibleReason || "Production model gates have not passed." };
}

function productionGateChip(row: OutlierBoardRow): TrustChip {
  const summary = rowTrustSummary(row);
  if (summary.productionGateStatus === "eligible_not_enabled") {
    return { label: "Gates pass, disabled", tone: "watch", title: summary.productionEligibleReason || "Research only. Production betting gates passed, but bet actions are disabled." };
  }
  if (summary.productionGateStatus === "blocked") {
    const reason = summary.productionGateReasons[0] ? summary.productionGateReasons[0].replace(/_/g, " ") : "quality gates are incomplete";
    return { label: "Production gates closed", tone: "risk", title: summary.productionEligibleReason || `Research only. Production betting gates are closed: ${reason}.` };
  }
  return { label: "Production gates closed", tone: "watch", title: "Research only. Production betting gates are closed." };
}

function productionStatusChip(row: OutlierBoardRow): TrustChip | null {
  const status = rowTrustSummary(row).productionStatus;
  if (!status) return null;
  if (status === "production") return { label: "Production eligible", tone: "good", title: "Production status is active." };
  if (status.includes("baseline")) return { label: "Baseline trained", tone: "watch", title: "Baseline model exists but production gates still apply." };
  if (status.includes("experimental") || status.includes("candidate")) return { label: "Experimental", tone: "watch", title: "Experimental model state." };
  return { label: trustStatusLabel(status), tone: "watch", title: "Model state." };
}

function calibrationChip(row: OutlierBoardRow): TrustChip | null {
  const status = rowTrustSummary(row).calibrationStatus;
  if (!status) return null;
  if (["ready", "ok", "passed", "calibrated"].includes(status)) return { label: "Calibrated", tone: "good", title: "Calibration artifact is ready." };
  return { label: "Calibration needed", tone: "watch", title: "Calibration needed before production eligibility." };
}

function backtestChip(row: OutlierBoardRow): TrustChip | null {
  const status = rowTrustSummary(row).backtestStatus;
  if (!status) return null;
  if (["ready", "ok", "passed"].includes(status)) return { label: "Backtest ready", tone: "good", title: "Backtest artifact is ready." };
  return { label: "Backtest needed", tone: "watch", title: "Backtest needed before production eligibility." };
}

function freshnessChip(row: OutlierBoardRow): TrustChip {
  const freshness = rowFreshness(row, "Unknown");
  if (freshness.status.includes("stale") || freshness.status.includes("missing")) return { label: "Data stale", tone: "risk", title: freshness.source || "Freshness warning." };
  if (freshness.status.includes("fresh")) return { label: "Fresh", tone: "good", title: freshness.source || "Freshness is within the configured window." };
  return { label: freshness.label, tone: freshness.tone, title: freshness.source || "Freshness status." };
}

function gameMarketChip(row: OutlierBoardRow): TrustChip | null {
  const status = rowTrustSummary(row).gameMarketStatus;
  if (!status) return null;
  if (status === "matched" || status === "available") return { label: "Game markets ready", tone: "good", title: "Game market context matched." };
  return { label: "Game markets missing", tone: "watch", title: "Game market context missing; edge confidence is reduced." };
}

function identityChip(row: OutlierBoardRow): TrustChip {
  const identity = rowPropIdentity(row);
  if (identity.attributionStatus === "conflict") {
    return { label: "Possible team mismatch", tone: "risk", title: identity.identityWarnings[0] || "Player/team attribution conflicts with local evidence." };
  }
  if (identity.attributionStatus === "ambiguous") {
    return { label: "Ambiguous player", tone: "risk", title: identity.identityWarnings[0] || "Player identity could not be uniquely resolved." };
  }
  if (identity.attributionStatus === "invalid_player_label") {
    return { label: "Invalid player label", tone: "risk", title: identity.identityWarnings[0] || "Market label could not be safely treated as a player." };
  }
  if (identity.attributionCorrectionApplied || identity.attributionStatus === "corrected") {
    return { label: "Corrected", tone: "good", title: identity.attributionCorrectionReason || "Source mismatch corrected by roster evidence." };
  }
  if (Boolean(row.contextBlockedByAttribution)) {
    return { label: "Context limited", tone: "risk", title: identity.identityWarnings[0] || "Model/context join blocked by attribution confidence." };
  }
  if (identity.attributionStatus === "source_missing") {
    return { label: "Source missing team", tone: "watch", title: identity.identityWarnings[0] || "Source team or opponent was missing." };
  }
  if (identity.identityConfidence === "strong") {
    return { label: "Verified", tone: "good", title: "Player, team, opponent, market, side, and line identity are verified." };
  }
  if (identity.identityConfidence === "medium") {
    return { label: "Identity inferred", tone: "watch", title: identity.identityWarnings[0] || "Identity is inferred from board context. Research only." };
  }
  if (identity.identityConfidence === "weak") {
    return { label: "Team unverified", tone: "risk", title: identity.identityWarnings[0] || "Team or opponent identity is incomplete. Research only." };
  }
  return { label: "Identity unknown", tone: "risk", title: identity.identityWarnings[0] || "Insufficient identity information. Research only." };
}

function missingDataChip(row: OutlierBoardRow): TrustChip | null {
  const summary = rowTrustSummary(row);
  if (!summary.missingDataCount) return null;
  return { label: `Missing data ${summary.missingDataCount}`, tone: "risk", title: summary.missingDataSummary };
}

function warningChip(row: OutlierBoardRow): TrustChip | null {
  const count = rowTrustSummary(row).warningCount;
  if (!count) return null;
  return { label: `Warnings ${count}`, tone: "watch", title: `${count} trust warning${count === 1 ? "" : "s"}.` };
}

export function featureCoverageChip(row: OutlierBoardRow): TrustChip | null {
  const model = objectValue(row.trust?.model);
  const raw = model.featureCoverage ?? row.featureCoverage;
  const coverage = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(coverage)) return null;
  const percentValue = coverage <= 1 ? Math.round(coverage * 100) : Math.round(coverage);
  if (percentValue < 70) return { label: "Low Feature Coverage", tone: "risk", title: `${percentValue}% feature coverage.` };
  return { label: `Feature Coverage ${percentValue}%`, tone: "good", title: `${percentValue}% feature coverage.` };
}

export function actionNetworkTrustChip(row: OutlierBoardRow): TrustChip | null {
  const trust = objectValue(row.trust?.actionnetwork);
  const status = text(trust.status ?? row.actionnetworkStatus, "").toLowerCase();
  const eventConfirmed = Boolean(trust.eventConfirmed ?? row.eventConfirmed);
  const trainable = text(trust.trainableEligibility ?? row.trainableEligibility, "").toLowerCase();
  const collectionMode = text(trust.collectionMode ?? row.collectionMode, "").toLowerCase();
  if (eventConfirmed) return { label: "Event Confirmed", tone: "good", title: "ActionNetwork row has event-to-game confirmation." };
  if (collectionMode === "diagnostic_past" || status.includes("diagnostic")) return { label: "Date Only Diagnostic", tone: "risk", title: "Diagnostic/past ActionNetwork data is not trainable." };
  if (trainable === "not_trainable" || status.includes("not_trainable")) return { label: "Not Trainable", tone: "risk", title: "ActionNetwork row has not cleared ML eligibility gates." };
  if (status.includes("fresh")) return { label: "Snapshot Fresh", tone: "good", title: "ActionNetwork live snapshot is fresh." };
  if (status.includes("stale")) return { label: "Snapshot Stale", tone: "risk", title: "ActionNetwork snapshot is stale or missing." };
  return null;
}

export function badgeToneClass(tone: TrustTone | "positive" | "neutral" | "negative"): string {
  if (tone === "good" || tone === "positive") return "is-good";
  if (tone === "risk" || tone === "negative") return "is-risk";
  return "is-watch";
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function normalizedStatus(value: unknown): string {
  return text(value, "").toLowerCase().trim().replace(/[\s-]+/g, "_");
}

function trustScore(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function visibleUnscoredReason(row: OutlierBoardRow, trustTier: string, guardrailStatus: string, guardrails: Record<string, unknown>): string {
  const raw = normalizedStatus(row.unscoredReason ?? guardrails.unscoredReason);
  if (!raw || raw === "none") return "none";
  if (trustTier === "standard" || trustTier === "low" || trustTier === "limited") {
    return guardrailStatus === "blocked" ? raw : "none";
  }
  if (trustTier === "blocked" || trustTier === "unsupported" || trustTier === "unscored") return raw;
  return guardrailStatus === "blocked" ? raw : "none";
}

function integer(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : 0;
}

function arrayText(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => text(item, "")).filter(Boolean) : [];
}

function normalizeTone(value: unknown, fallback: TrustTone): TrustTone {
  const raw = text(value, "").toLowerCase();
  if (raw === "good" || raw === "watch" || raw === "risk" || raw === "neutral") return raw;
  if (raw === "fresh" || raw === "positive") return "good";
  if (raw === "stale" || raw === "missing" || raw === "negative") return "risk";
  if (raw === "aging" || raw === "warning") return "watch";
  return fallback;
}

function readinessToneFromLabel(label: string, status: string, canAct: boolean): TrustTone {
  const raw = `${label} ${status}`.toLowerCase();
  if (canAct || raw.includes("production ready") || raw.includes("production_ready")) return "good";
  if (raw.includes("missing") || raw.includes("no model") || raw.includes("blocked") || raw.includes("stale")) return "risk";
  return "watch";
}

function freshnessToneFromStatus(status: string, label: string): TrustTone {
  const raw = `${status} ${label}`.toLowerCase();
  if (raw.includes("fresh") || raw.includes("good")) return "good";
  if (raw.includes("stale") || raw.includes("missing") || raw.includes("failed") || raw.includes("unavailable")) return "risk";
  return "watch";
}

function statusLabel(status: string): string {
  if (status.includes("fresh") || status === "good") return "Fresh";
  if (status.includes("stale")) return "Stale";
  if (status.includes("missing")) return "Missing";
  if (status.includes("aging") || status.includes("partial") || status.includes("degraded")) return "Aging";
  return "";
}

function normalizeActionabilityStatus(value: unknown, decision: string, readiness: NormalizedReadiness, edgePercent: number): ActionabilityStatus {
  const raw = text(value, "").toLowerCase();
  if (raw === "actionable" || raw === "watchlist" || raw === "research_only" || raw === "blocked") return raw;
  const decisionRaw = decision.toLowerCase();
  if (decisionRaw.includes("no bet") || edgePercent === null || edgePercent <= 0) return "blocked";
  if (readiness.canAct && (decisionRaw.includes("potential edge") || edgePercent >= 2)) return "actionable";
  if (decisionRaw.includes("watch") || decisionRaw.includes("lean") || edgePercent > 0) return "watchlist";
  return "research_only";
}

function actionabilityLabel(status: ActionabilityStatus, decision: string): string {
  if (decision && status !== "research_only") return decision;
  if (status === "actionable") return "Model lean";
  if (status === "watchlist") return "Watchlist";
  if (status === "blocked") return "No bet";
  return "Research only";
}

function actionabilityTone(status: ActionabilityStatus): TrustTone {
  if (status === "actionable") return "good";
  if (status === "blocked") return "risk";
  return "watch";
}

function firstReason(row: OutlierBoardRow): string {
  return Array.isArray(row.reasons) ? text(row.reasons[0], "") : "";
}

