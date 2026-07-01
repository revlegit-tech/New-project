import { number, text } from "../../shared/formatting";
import { OutlierBoardRow } from "./types";
export type { OutlierBoardRow } from "./types";

export function rowPlayer(row: OutlierBoardRow): string {
  return text(row.trust?.propIdentity?.player ?? row.player ?? row.playerName ?? row.team, "MLB");
}

export function rowMarketKey(row: OutlierBoardRow): string {
  return text(row.trust?.propIdentity?.market ?? row.market ?? row.baseMarket, "");
}

export function rowLine(row: OutlierBoardRow): unknown {
  return row.trust?.propIdentity?.line ?? row.line ?? row.propLine;
}

export function rowOdds(row: OutlierBoardRow): unknown {
  return row.americanOdds ?? row.odds;
}

export function rowSelectedBook(row: OutlierBoardRow): string {
  return text(row.selectedBook ?? row.book ?? row.bestBook, "");
}

export function rowBestBook(row: OutlierBoardRow): string {
  return text(row.bestBook ?? row.book, "");
}

export function rowSelectedOdds(row: OutlierBoardRow): unknown {
  return row.selectedBookAmericanOdds ?? row.americanOdds ?? row.odds;
}

export function rowBestOdds(row: OutlierBoardRow): unknown {
  return row.bestAmericanOdds ?? row.americanOdds ?? row.odds;
}

export function rowQuoteCount(row: OutlierBoardRow): number {
  const parsed = Number(row.quoteCount ?? row.bookCount ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function rowAvailableBooks(row: OutlierBoardRow): string[] {
  const value = row.availableBooks;
  if (Array.isArray(value)) return value.map((book) => text(book, "")).filter(Boolean);
  return [];
}

export function rowModelProbability(row: OutlierBoardRow): unknown {
  return row.trust?.modelEdge?.modelProbabilityPercent ?? row.modelProbabilityPercent ?? row.modelProbability ?? row.probability ?? row.prob;
}

export function rowImpliedProbability(row: OutlierBoardRow): unknown {
  return row.trust?.modelEdge?.impliedProbabilityPercent ?? row.impliedProbabilityPercent ?? row.impliedProbability ?? row.sportsbookImpliedPercent ?? row.impliedPercent;
}

export function rowSelectedImpliedProbability(row: OutlierBoardRow): unknown {
  return row.selectedBookImpliedProbability ?? row.impliedProbability ?? row.impliedProbabilityPercent ?? row.sportsbookImpliedPercent;
}

export function rowBestImpliedProbability(row: OutlierBoardRow): unknown {
  return row.bestImpliedProbability ?? row.impliedProbability ?? row.impliedProbabilityPercent ?? row.sportsbookImpliedPercent;
}

export function matchup(row: OutlierBoardRow): string {
  const away = text(row.away ?? row.team, "");
  const home = text(row.home ?? row.opponent, "");
  return away && home ? `${away} @ ${home}` : text(row.game ?? row.matchup, "Matchup pending");
}

export function edgeValue(row: OutlierBoardRow): number | null {
  const value = row.trust?.modelEdge?.edgePercent ?? row.edgePercent;
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function edgeTone(row: OutlierBoardRow): string {
  const edge = edgeValue(row);
  if (edge === null) return "is-risk";
  if (edge >= 5) return "is-good";
  if (edge >= 0) return "is-watch";
  return "is-risk";
}

export function readiness(row: OutlierBoardRow): string {
  const modelCard = row.modelCard && typeof row.modelCard === "object" ? (row.modelCard as Record<string, unknown>) : null;
  return text(row.trust?.readiness?.label ?? modelCard?.status ?? row.readinessLabel ?? row.readiness ?? row.confidence, "Research only");
}

export function readinessTone(row: OutlierBoardRow): string {
  const raw = readiness(row).toLowerCase();
  if (raw.includes("ready") || raw.includes("production")) return "is-good";
  if (raw.includes("missing") || raw.includes("stale")) return "is-risk";
  return "is-watch";
}

export function trustCopy(row: OutlierBoardRow): string {
  return row.trust?.actionability?.status === "actionable" || readinessTone(row) === "is-good"
    ? "This prop has model-readiness context. Still verify sportsbook lines before acting."
    : "This prop is visible for research but should stay 0u until data and model gates are satisfied.";
}

export function rowPropKey(row: OutlierBoardRow): string {
  return text(row.propKey ?? row.id ?? row.key, "");
}
