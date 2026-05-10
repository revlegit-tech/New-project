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
}

export interface NormalizedModelEdge {
  edgePercent: number;
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
  };
}

export function rowModelEdge(row: OutlierBoardRow): NormalizedModelEdge {
  const modelEdge = objectValue(row.trust?.modelEdge);
  const edge = number(modelEdge.edgePercent ?? row.finalEdgePercent ?? row.edgePercent ?? row.edge ?? row.modelEdgePercent, 0);
  const explicitTone = text(modelEdge.tone, "");
  return {
    edgePercent: edge,
    modelProbabilityPercent: modelEdge.modelProbabilityPercent ?? row.modelProbabilityPercent ?? row.modelProbability ?? row.probabilityPercent ?? row.probability ?? row.prob,
    impliedProbabilityPercent: modelEdge.impliedProbabilityPercent ?? row.impliedProbabilityPercent ?? row.sportsbookImpliedPercent ?? row.impliedProbability ?? row.impliedPercent,
    tone: explicitTone === "positive" || explicitTone === "neutral" || explicitTone === "negative" ? explicitTone : edge > 0 ? "positive" : edge < 0 ? "negative" : "neutral",
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
  const stakeUnits = typeof actionability.stakeUnits === "number" ? actionability.stakeUnits : status === "actionable" ? 0.25 : 0;
  return {
    label,
    status,
    tone: actionabilityTone(status),
    suggestedStake: text(actionability.suggestedStake ?? row.suggestedStake ?? (status === "actionable" ? "0.25u capped" : "Research only"), "Research only"),
    stakeUnits,
    reason: text(actionability.reason ?? firstReason(row) ?? "", ""),
  };
}

export function rowTrustCopy(row: OutlierBoardRow): string {
  const readiness = rowReadiness(row);
  const actionability = rowActionability(row);
  if (actionability.status === "actionable" && readiness.canAct) {
    return "This prop clears model-readiness gates, but line movement and limits still need a final book check.";
  }
  if (actionability.status === "watchlist") {
    return "This prop has a positive model lean, but it should stay on the watchlist until the readiness gates are complete.";
  }
  return "This prop is visible for research but should stay 0u until data and model gates are satisfied.";
}

export function badgeToneClass(tone: TrustTone | "positive" | "neutral" | "negative"): string {
  if (tone === "good" || tone === "positive") return "is-good";
  if (tone === "risk" || tone === "negative") return "is-risk";
  return "is-watch";
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
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
  if (decisionRaw.includes("no bet") || edgePercent <= 0) return "blocked";
  if (readiness.canAct && (decisionRaw.includes("potential edge") || edgePercent >= 2)) return "actionable";
  if (decisionRaw.includes("watch") || decisionRaw.includes("lean") || edgePercent > 0) return "watchlist";
  return "research_only";
}

function actionabilityLabel(status: ActionabilityStatus, decision: string): string {
  if (decision && status !== "research_only") return decision;
  if (status === "actionable") return "Actionable";
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

