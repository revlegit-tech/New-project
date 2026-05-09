import { number, text } from "../../shared/formatting";

export type OutlierBoardRow = Record<string, unknown>;

export function rowPlayer(row: OutlierBoardRow): string {
  return text(row.player ?? row.playerName ?? row.team, "MLB");
}

export function rowMarketKey(row: OutlierBoardRow): string {
  return text(row.market ?? row.baseMarket, "");
}

export function rowLine(row: OutlierBoardRow): unknown {
  return row.line ?? row.propLine;
}

export function rowOdds(row: OutlierBoardRow): unknown {
  return row.americanOdds ?? row.odds;
}

export function rowModelProbability(row: OutlierBoardRow): unknown {
  return row.modelProbability ?? row.probability ?? row.prob;
}

export function rowImpliedProbability(row: OutlierBoardRow): unknown {
  return row.impliedProbability ?? row.sportsbookImpliedPercent ?? row.impliedPercent;
}

export function matchup(row: OutlierBoardRow): string {
  const away = text(row.away ?? row.team, "");
  const home = text(row.home ?? row.opponent, "");
  return away && home ? `${away} @ ${home}` : text(row.game ?? row.matchup, "Matchup pending");
}

export function edgeValue(row: OutlierBoardRow): number {
  return number(row.finalEdgePercent ?? row.edge ?? row.edgePercent, 0);
}

export function edgeTone(row: OutlierBoardRow): string {
  const edge = edgeValue(row);
  if (edge >= 5) return "is-good";
  if (edge >= 0) return "is-watch";
  return "is-risk";
}

export function readiness(row: OutlierBoardRow): string {
  const modelCard = row.modelCard && typeof row.modelCard === "object" ? (row.modelCard as Record<string, unknown>) : null;
  return text(modelCard?.status ?? row.readinessLabel ?? row.readiness ?? row.confidence, "Research only");
}

export function readinessTone(row: OutlierBoardRow): string {
  const raw = readiness(row).toLowerCase();
  if (raw.includes("ready") || raw.includes("production")) return "is-good";
  if (raw.includes("missing") || raw.includes("stale")) return "is-risk";
  return "is-watch";
}

export function trustCopy(row: OutlierBoardRow): string {
  return readinessTone(row) === "is-good"
    ? "This prop has model-readiness context. Still verify sportsbook lines before acting."
    : "This prop is visible for research but should stay 0u until data and model gates are satisfied.";
}

export function rowPropKey(row: OutlierBoardRow): string {
  return text(row.propKey ?? row.id ?? row.key, "");
}
