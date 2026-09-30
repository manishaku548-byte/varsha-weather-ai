// Shared UI constants. None of these are forecast values, weights, confidence
// or risk data - every computed value displayed by the dashboard comes from the
// backend API. These are only display labels, palettes and selector options.

export const API_BASE_URL =
  (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001").replace(/\/+$/, "");

export const LEAD_OPTIONS = [6, 24, 72] as const;
export type LeadHours = 6 | 24 | 72;

export type Role = "viewer" | "forecaster" | "administrator";

export const ROLE_OPTIONS: { id: Role; label: string; description: string }[] = [
  { id: "viewer", label: "Viewer", description: "Read-only dashboard" },
  { id: "forecaster", label: "Forecaster", description: "Can record expert overrides" },
  { id: "administrator", label: "Administrator", description: "Forecaster + model controls" },
];

export type ScenarioId = "normal" | "nwp" | "ensemble" | "ai";

export const SCENARIOS: { id: ScenarioId; label: string; description: string }[] = [
  { id: "normal", label: "Normal replay", description: "All configured sources contribute." },
  { id: "nwp", label: "NWP source failure", description: "Simulate the NWP model feed failing." },
  { id: "ensemble", label: "Ensemble source failure", description: "Simulate the ensemble feed failing." },
  { id: "ai", label: "AI source failure", description: "Simulate the AI local-correction feed failing." },
];

export const SOURCE_DISPLAY: Record<
  string,
  { id: string; short: string; full: string; type: string; color: string }
> = {
  nwp_model_a: {
    id: "nwp_model_a",
    short: "NWP",
    full: "NWP Model A (synthetic)",
    type: "NWP",
    color: "#4a7fb8",
  },
  ensemble_mean: {
    id: "ensemble_mean",
    short: "Ensemble",
    full: "Ensemble Mean (synthetic)",
    type: "Ensemble",
    color: "#2a5f9e",
  },
  ai_local_v1: {
    id: "ai_local_v1",
    short: "AI Local",
    full: "AI Local Correction v1 (synthetic)",
    type: "AI/ML",
    color: "#0d9488",
  },
};

export const SOURCE_ORDER = ["nwp_model_a", "ensemble_mean", "ai_local_v1"];

export const FAILURE_SOURCE_ALIAS: Record<string, string> = {
  nwp: "nwp_model_a",
  ensemble: "ensemble_mean",
  ai: "ai_local_v1",
};

export const RISK_META: Record<
  string,
  { label: string; badge: string; dot: string; bar: string; text: string }
> = {
  Low: {
    label: "Low",
    badge: "border-slate-300 bg-slate-100 text-slate-700",
    dot: "bg-slate-500",
    bar: "bg-slate-500",
    text: "text-slate-700",
  },
  Moderate: {
    label: "Moderate",
    badge: "border-amber-300 bg-amber-50 text-amber-800",
    dot: "bg-amber-500",
    bar: "bg-amber-500",
    text: "text-amber-800",
  },
  High: {
    label: "High",
    badge: "border-orange-300 bg-orange-50 text-orange-800",
    dot: "bg-orange-500",
    bar: "bg-orange-500",
    text: "text-orange-800",
  },
  Critical: {
    label: "Critical",
    badge: "border-red-300 bg-red-50 text-red-800",
    dot: "bg-red-600",
    bar: "bg-red-600",
    text: "text-red-800",
  },
};

export const STATUS_META: Record<string, { label: string; className: string }> = {
  Healthy: { label: "Healthy", className: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  Delayed: { label: "Delayed", className: "border-amber-200 bg-amber-50 text-amber-700" },
  Anomalous: { label: "Anomalous", className: "border-orange-200 bg-orange-50 text-orange-700" },
  Unavailable: { label: "Unavailable", className: "border-red-200 bg-red-50 text-red-700" },
};

export const FALLBACK_LABEL: Record<string, string> = {
  normal: "Normal",
  degraded: "Degraded",
  single_source: "Single Source",
};

export const ML_SOURCE_LABEL: Record<string, string> = {
  trained_local_correction_model: "Trained Local-Correction Model",
  fallback_precomputed_ai_source: "Fallback Precomputed AI Source",
};

export const RESULT_METHODS: { key: string; label: string }[] = [
  { key: "nwp", label: "NWP" },
  { key: "ensemble", label: "Ensemble" },
  { key: "ai_local", label: "AI Local Correction" },
  { key: "equal_weight", label: "Equal-Weight Average" },
  { key: "varsha_dynamic_blend", label: "VARSHA Dynamic Blend" },
];

export const FOOTER_LINE =
  "VARSHA Weather AI | SIH26081 | Synthetic Development Dataset | " +
  "Decision-Support Prototype - Not an Official Weather Warning.";

export const MAP_DISCLAIMER =
  "Prototype district overview - not an official warning map.";

export const REVIEW_NOTE =
  "Prototype local review log - not an official authorization record.";

/**
 * Stable demo scenario (existing synthetic data, verified against the running
 * backend): Prayagraj, 2025-09-03, 24 h lead -> Critical / Heavy-Rain Risk.
 * Values must always be READ from the live API; none are hardcoded here.
 * See docs/demo_scenario.md for the full walkthrough.
 */
export const DEMO_SCENARIO = {
  districtId: "prayagraj",
  districtName: "Prayagraj",
  date: "2025-09-03",
  lead: 24,
  scenario: "normal" as ScenarioId,
};