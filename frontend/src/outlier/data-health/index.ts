export const DATA_HEALTH_MODULE_BOUNDARY = "outlier-data-health";

export type ContextConsumptionStatus =
  | "used"
  | "artifact_only"
  | "joined_not_populated"
  | "available_not_used"
  | "no_safe_rows"
  | "unavailable"
  | "not_configured"
  | string;

export interface ContextConsumptionEntry {
  group: string;
  status: ContextConsumptionStatus;
  statusLabel: string;
  statusBucket: string;
  configuredForCurrentModel: boolean;
  usedByCurrentModel: boolean;
  artifactExists: boolean;
  artifactRows: number;
  rowsLoaded: number;
  rowsJoinedToScoring: number;
  populatedPercent: number;
  populatedFeatureFields: unknown[];
  missingFeatureFields: unknown[];
  modelFeatureFields: unknown[];
  reason: string;
  warnings: string[];
}

const STATUS_LABELS: Record<string, string> = {
  used: "Used by model",
  artifact_only: "Artifact only",
  joined_not_populated: "Joined, not populated",
  available_not_used: "Available, not used",
  no_safe_rows: "No safe local rows",
  unavailable: "Unavailable",
  not_configured: "Not configured",
};

const STATUS_BUCKETS: Record<string, string> = {
  used: "Used by model",
  joined_not_populated: "Configured but not used",
  artifact_only: "Artifact only / join pending",
  available_not_used: "Configured but not used",
  no_safe_rows: "No safe local rows",
  unavailable: "Unavailable / not configured",
  not_configured: "Unavailable / not configured",
};

const STATUS_ORDER: Record<string, number> = {
  used: 0,
  joined_not_populated: 1,
  available_not_used: 2,
  artifact_only: 3,
  no_safe_rows: 4,
  unavailable: 5,
  not_configured: 6,
};

export function contextStatusLabel(status: unknown): string {
  const normalized = normalizeStatus(status);
  return STATUS_LABELS[normalized] || titleize(normalized || "unknown");
}

export function getPlayerboardContextConsumption(status: unknown): ContextConsumptionEntry[] {
  const raw = objectValue(status)?.playerboard_build_health?.contextConsumption;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
  return Object.entries(raw)
    .filter(([, value]) => value && typeof value === "object" && !Array.isArray(value))
    .map(([group, value]) => normalizeEntry(group, value as Record<string, unknown>))
    .sort((a, b) => {
      const statusDelta = (STATUS_ORDER[a.status] ?? 99) - (STATUS_ORDER[b.status] ?? 99);
      return statusDelta || a.group.localeCompare(b.group);
    });
}

function normalizeEntry(group: string, value: Record<string, unknown>): ContextConsumptionEntry {
  const status = normalizeStatus(value.status);
  const modelFeatureFields = arrayValue(value.modelFeatureFields);
  const populatedFeatureFields = arrayValue(value.populatedFeatureFields);
  const missingFeatureFields = arrayValue(value.missingFeatureFields);
  return {
    group,
    status,
    statusLabel: contextStatusLabel(status),
    statusBucket: STATUS_BUCKETS[status] || "Unavailable / not configured",
    configuredForCurrentModel: Boolean(value.configuredForCurrentModel ?? modelFeatureFields.length > 0),
    usedByCurrentModel: Boolean(value.usedByCurrentModel),
    artifactExists: Boolean(value.artifactExists),
    artifactRows: numberValue(value.artifactRows),
    rowsLoaded: numberValue(value.rowsLoaded),
    rowsJoinedToScoring: numberValue(value.rowsJoinedToScoring),
    populatedPercent: numberValue(value.populatedPercent),
    populatedFeatureFields,
    missingFeatureFields,
    modelFeatureFields,
    reason: stringValue(value.reason),
    warnings: arrayValue(value.warnings).map((item) => stringValue(item)).filter(Boolean),
  };
}

function normalizeStatus(value: unknown): string {
  return stringValue(value).toLowerCase().replace(/[\s-]+/g, "_");
}

function arrayValue(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  return [];
}

function numberValue(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function objectValue(value: unknown): Record<string, any> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, any> : null;
}

function stringValue(value: unknown): string {
  return String(value ?? "").trim();
}

function titleize(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
