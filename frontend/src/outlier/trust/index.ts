export interface FreshnessSeverity {
  tone: "fresh" | "aging" | "stale" | "unavailable";
  label: string;
  copy: string;
}

export {
  badgeToneClass,
  rowActionability,
  rowAttributionChip,
  rowFreshness,
  rowModelEdge,
  rowPropIdentity,
  rowReadiness,
  rowIsTrustedMarket,
  rowTrustSummary,
  rowTrustChips,
  rowTrustCopy,
  trustStatusLabel,
  uniqueTrustValues,
} from "./rowTrust";

export function freshnessSeverity(payload: any): FreshnessSeverity {
  const raw = String(payload?.tone || payload?.staleDataSeverity || payload?.dataFreshness?.severity || payload?.dataConfidence || payload?.freshness?.status || payload?.status || "").toLowerCase();
  const age = Number(payload?.ageSeconds);
  if (Number.isFinite(age) && age > 900) return { tone: "stale", label: "Stale", copy: "Data stale; review after the next collector run." };
  if (Number.isFinite(age) && age > 300) return { tone: "aging", label: "Aging", copy: "Usable for research; verify lines." };
  if (raw.includes("stale") || raw.includes("red") || raw.includes("missing")) return { tone: "stale", label: "Stale", copy: "Data stale; review after the next collector run." };
  if (raw.includes("aging") || raw.includes("partial") || raw.includes("warn") || raw.includes("amber")) return { tone: "aging", label: "Aging", copy: "Usable for research; verify lines." };
  if (raw.includes("good") || raw.includes("fresh") || raw.includes("green")) return { tone: "fresh", label: "Fresh", copy: "Within configured freshness window." };
  return { tone: "unavailable", label: "Unavailable", copy: "Source freshness is not available." };
}
