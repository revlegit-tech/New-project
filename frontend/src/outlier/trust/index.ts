export interface FreshnessSeverity {
  tone: "fresh" | "aging" | "stale" | "unavailable";
  label: string;
  copy: string;
}

export function rowFreshnessLabel(row: any, fallback = "Research") {
  const source = row?.freshness?.status || row?.freshnessStatus || row?.dataFreshness || fallback;
  return String(source || fallback);
}

export function rowFreshnessTone(row: any) {
  const raw = rowFreshnessLabel(row, "").toLowerCase();
  if (raw.includes("fresh")) return "is-good";
  if (raw.includes("missing") || raw.includes("stale") || raw.includes("degraded")) return "is-risk";
  return "is-watch";
}

export function freshnessSeverity(payload: any): FreshnessSeverity {
  const raw = String(payload?.staleDataSeverity || payload?.dataFreshness?.severity || payload?.dataConfidence || "").toLowerCase();
  if (raw.includes("stale") || raw.includes("red") || raw.includes("missing")) return { tone: "stale", label: "Stale", copy: "Do not trust for live betting." };
  if (raw.includes("aging") || raw.includes("partial") || raw.includes("warn") || raw.includes("amber")) return { tone: "aging", label: "Aging", copy: "Usable for research; verify lines." };
  if (raw.includes("good") || raw.includes("fresh") || raw.includes("green")) return { tone: "fresh", label: "Fresh", copy: "Within configured freshness window." };
  return { tone: "unavailable", label: "Unavailable", copy: "Source freshness is not available." };
}
