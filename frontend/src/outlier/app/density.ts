export type DensityMode = "compact" | "research";

const ROW_HEIGHTS: Record<DensityMode, number> = {
  compact: 52,
  research: 72,
};

export function normalizeDensity(value: unknown): DensityMode {
  return value === "research" ? "research" : "compact";
}

export function densityRowHeight(value: unknown): number {
  return ROW_HEIGHTS[normalizeDensity(value)];
}

export function applyDensity(value: unknown): DensityMode {
  const density = normalizeDensity(value);
  document.body.dataset.obDensity = density;
  return density;
}

