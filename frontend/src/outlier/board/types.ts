export type TrustTone = "good" | "watch" | "risk" | "neutral";
export type FreshnessStatus = "fresh" | "aging" | "stale" | "missing" | "unknown";
export type ActionabilityStatus = "actionable" | "watchlist" | "research_only" | "blocked";

export interface PropIdentityTrust {
  player?: string;
  team?: string;
  opponent?: string;
  market?: string;
  line?: string | number;
  side?: string;
  book?: string;
  identityConfidence?: string;
  identityWarnings?: string[];
  playerTeamVerified?: boolean;
  opponentVerified?: boolean;
  attributionStatus?: string;
  attributionCorrectionApplied?: boolean;
  attributionCorrectionReason?: string;
  playerTeamEvidenceStatus?: string;
}

export interface ModelEdgeTrust {
  edgePercent?: number | string | null;
  modelProbabilityPercent?: number | string | null;
  impliedProbabilityPercent?: number | string | null;
  tone?: "positive" | "neutral" | "negative";
}

export interface ReadinessTrust {
  label?: string;
  status?: string;
  tone?: TrustTone;
  canShowConfidentPick?: boolean;
  warnings?: string[];
}

export interface ActionabilityTrust {
  label?: string;
  status?: ActionabilityStatus | string;
  suggestedStake?: string;
  stakeUnits?: number;
  reason?: string;
}

export interface RowTrustPayload {
  propIdentity?: PropIdentityTrust;
  modelEdge?: ModelEdgeTrust;
  readiness?: ReadinessTrust;
  actionability?: ActionabilityTrust;
  productionGate?: Record<string, unknown>;
  model?: Record<string, unknown>;
  actionnetwork?: Record<string, unknown>;
  runtime?: Record<string, unknown>;
}

export interface RowFreshnessPayload {
  label?: string;
  status?: FreshnessStatus | string;
  tone?: TrustTone;
  ageSeconds?: number;
  source?: string;
  reason?: string;
}

export type OutlierBoardRow = Record<string, unknown> & {
  trust?: RowTrustPayload;
  freshness?: RowFreshnessPayload;
};

