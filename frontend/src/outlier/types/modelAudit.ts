export interface PromotionCommandPreview {
  enabled?: boolean;
  informationalOnly?: boolean;
  command?: string;
  message?: string;
}

export interface GateCheck {
  key?: string;
  name?: string;
  label?: string;
  status?: string;
  passed?: boolean;
  required?: boolean;
  reason?: string;
  message?: string;
  details?: string;
  value?: unknown;
}

export interface GateSummary {
  status?: string;
  passedCount?: number;
  failedCount?: number;
  warningCount?: number;
  manualGovernanceRequired?: boolean;
  hardBlockerCount?: number;
  softWarningCount?: number;
  totalChecks?: number;
}

export interface ShadowMarketSummary {
  market: string;
  modelStage?: string;
  modelKey?: string;
  version?: string;
  artifactStatus?: string;
  freshnessStatus?: string;
  artifactAgeHours?: number | null;
  maxAllowedAgeHours?: number | null;
  latestValidationDate?: string;
  sourcePath?: string;
  fallbackUsed?: boolean;
  registryShadowPointerPresent?: boolean;
  evaluatedRows?: number | null;
  positiveRows?: number | null;
  negativeRows?: number | null;
  auc?: number | null;
  brierScore?: number | null;
  logLoss?: number | null;
  expectedCalibrationError?: number | null;
  validationDates?: string[];
  generatedAt?: string;
  readinessLabel?: string;
  action?: string;
  stakeUnits?: number;
  betActionAllowed?: boolean;
  freshness?: ShadowFreshnessMarket;
  warnings?: string[];
}

export interface ShadowFreshnessMarket {
  market: string;
  modelStage?: string;
  modelKey?: string;
  version?: string;
  artifactStatus?: string;
  freshnessStatus?: string;
  artifactAgeHours?: number | null;
  maxAllowedAgeHours?: number | null;
  latestValidationDate?: string;
  sourcePath?: string;
  backtestPath?: string;
  calibrationPath?: string;
  manifestPath?: string;
  fallbackUsed?: boolean;
  registryShadowPointerPresent?: boolean;
  blockers?: string[];
  recommendedNextStep?: string;
  generatedAt?: string;
  readinessLabel?: string;
  action?: string;
  stakeUnits?: number;
  betActionAllowed?: boolean;
  warnings?: string[];
}

export interface ShadowReadinessMarket {
  market: string;
  modelStage?: string;
  modelKey?: string;
  version?: string;
  artifactStatus?: string;
  freshnessStatus?: string;
  artifactAgeHours?: number | null;
  maxAllowedAgeHours?: number | null;
  latestValidationDate?: string;
  sourcePath?: string;
  fallbackUsed?: boolean;
  registryShadowPointerPresent?: boolean;
  evaluatedRows?: number | null;
  positiveRows?: number | null;
  negativeRows?: number | null;
  auc?: number | null;
  brierScore?: number | null;
  logLoss?: number | null;
  expectedCalibrationError?: number | null;
  validationDates?: string[];
  generatedAt?: string;
  productionGateStatus?: string;
  productionEligible?: boolean;
  blockers?: string[];
  hardBlockers?: string[];
  softWarnings?: string[];
  warnings?: string[];
  gateChecks?: GateCheck[];
  gateSummary?: GateSummary;
  recommendedNextStep?: string;
  readinessLabel?: string;
  action?: string;
  stakeUnits?: number;
  betActionAllowed?: boolean;
  freshness?: ShadowFreshnessMarket;
  promotionCommandPreview?: PromotionCommandPreview;
  shadow?: Record<string, unknown>;
  baseline?: Record<string, unknown>;
  metricDeltas?: Record<string, unknown>;
}

export interface MlModelsStatusResponse {
  modelCounts?: Record<string, number>;
  experimental?: number;
  candidate?: number;
  shadow?: number;
  [key: string]: unknown;
}

export interface ShadowSummaryResponse {
  schemaVersion?: string;
  modelStage?: string;
  modelKey?: string;
  marketCount?: number;
  readyMarketCount?: number;
  markets?: ShadowMarketSummary[];
  promotionCommandPreview?: PromotionCommandPreview;
  [key: string]: unknown;
}

export interface ShadowReadinessResponse {
  schemaVersion?: string;
  marketCount?: number;
  readyMarketCount?: number;
  blockedMarketCount?: number;
  markets?: ShadowReadinessMarket[];
  promotionCommandPreview?: PromotionCommandPreview;
  [key: string]: unknown;
}

export interface ShadowFreshnessResponse {
  schemaVersion?: string;
  marketCount?: number;
  freshMarketCount?: number;
  staleMarketCount?: number;
  missingMarketCount?: number;
  unknownMarketCount?: number;
  markets?: ShadowFreshnessMarket[];
  [key: string]: unknown;
}

export interface ProductionGatesResponse {
  schemaVersion?: string;
  marketCount?: number;
  readyMarketCount?: number;
  blockedMarketCount?: number;
  markets?: ShadowReadinessMarket[];
  promotionCommandPreview?: PromotionCommandPreview;
  [key: string]: unknown;
}
