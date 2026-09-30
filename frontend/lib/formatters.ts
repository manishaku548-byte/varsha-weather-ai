// Number/date formatters. Display-only: these never compute forecast values,
// they only shape values that arrived from the backend API.

export function isPresent(value: unknown): value is number {
  return (
    typeof value === "number" && !Number.isNaN(value) && Number.isFinite(value)
  );
}

const NA = "N/A";

/** Rainfall: 1 decimal + "mm". Null/unavailable -> "N/A" (never a misleading 0). */
export function fmtMm(value: number | null | undefined): string {
  if (value === null || value === undefined || !isPresent(value)) return NA;
  return `${value.toFixed(1)} mm`;
}

/** Generic metric: 3 decimals by default (2 for compact tables). */
export function fmtMetric(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !isPresent(value)) return NA;
  return value.toFixed(digits);
}

/** Weights arrive as 0-1 fractions from the API; show as a percent (1 decimal). */
export function fmtWeight(value: number | null | undefined): string {
  if (value === null || value === undefined || !isPresent(value)) return NA;
  return `${(value * 100).toFixed(1)}%`;
}

/** Confidence: integer 0-100 with the 0-100 scale explicit. */
export function fmtConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || !isPresent(value)) return NA;
  return `${Math.round(value)} / 100`;
}

/** 0-1 confidence fraction (e.g. regime confidence) as a percent. */
export function fmtFractionPct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !isPresent(value)) return NA;
  return `${(value * 100).toFixed(digits)}%`;
}

/** YYYY-MM-DD -> "15 Sep 2025". */
export function fmtDate(value: string | null | undefined): string {
  if (!value) return NA;
  const d = new Date(`${value}T00:00:00`);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** ISO datetime (with optional timezone) -> "30 Sep 2026, 12:34 UTC". */
export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return NA;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return (
    d.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    }) +
    ", " +
    d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) +
    " UTC"
  );
}

export function fmtCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !isPresent(value)) return NA;
  return String(Math.round(value));
}

/** Add whole days to a YYYY-MM-DD string. */
export function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00`);
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Clamp an ISO date inside [min, max] (both inclusive, YYYY-MM-DD). */
export function clampDate(
  isoDate: string,
  min: string | null | undefined,
  max: string | null | undefined,
): string {
  if (min && isoDate < min) return min;
  if (max && isoDate > max) return max;
  return isoDate;
}

/** Human label for a backend status string when the backend has none. */
export function titleCase(value: string | null | undefined): string {
  if (!value) return NA;
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}