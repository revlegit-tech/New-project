export function text(value: unknown, fallback = "--"): string {
  const raw = value === null || value === undefined ? "" : String(value).trim();
  return raw || fallback;
}

export function number(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function percent(value: unknown, fallback = "--"): string {
  const parsed = number(value, Number.NaN);
  if (!Number.isFinite(parsed)) return fallback;
  const scaled = Math.abs(parsed) <= 1 ? parsed * 100 : parsed;
  return `${scaled.toFixed(Math.abs(scaled) % 1 ? 1 : 0)}%`;
}

export function signedPercent(value: unknown): string {
  const parsed = number(value, Number.NaN);
  if (!Number.isFinite(parsed)) return "--";
  const scaled = Math.abs(parsed) <= 1 ? parsed * 100 : parsed;
  return `${scaled >= 0 ? "+" : ""}${scaled.toFixed(1)}%`;
}

export function formatOdds(value: unknown): string {
  const raw = text(value, "");
  if (!raw) return "--";
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return raw;
  return parsed > 0 ? `+${parsed}` : String(parsed);
}

export function todayIso(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}
