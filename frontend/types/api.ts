// TypeScript interfaces mapped exactly to the VARSHA Weather AI FastAPI
// response schemas (backend/app/schemas*.py). The frontend never invents or
// rounds values - it only formats what these payloads contain.

// ---------------------------------------------------------------------------
// meta endpoints (/health, /districts, /data/summary)
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: "ok" | "degraded";
  service: string;
  version: string;
  phase: string;
  problem_statement_id: string;
  data_mode: string;
  data_label: string;
  disclaimer: string;
  dataset_loaded: boolean;
  database_status: "connected" | "error";
  records: Record<string, number>;
}

export interface District {
  district_id: string;
  district_name: string;
  state: string;
  latitude: number;
  longitude: number;
}

export interface DistrictListResponse {
  data_mode: string;
  data_label: string;
  disclaimer: string;
  count: number;
  districts: District[];
}

export interface SourceInfo {
  source_id: string;
  source_type: string;
  display_name: string;
  description: string;
}

export type SourceHealthStatus = "Healthy" | "Delayed" | "Unavailable" | "Anomalous";

export interface SourceHealth {
  source_id: string;
  source_type: string;
  status: SourceHealthStatus;
  window_days: number;
  records_in_window: number;
  unavailable_ratio: number;
  anomalous_ratio: number;
  delayed_ratio: number;
  note: string;
}

export interface RainfallBuckets {
  [bucket: string]: number;
}

export interface DistrictDataSummary {
  district_id: string;
  district_name: string;
  first_valid_date: string | null;
  last_valid_date: string | null;
  observation_records: number;
  forecast_records: number;
  rainfall_24h: RainfallBuckets;
  max_observed_24h_mm: number | null;
  mean_observed_24h_mm: number | null;
}

// Generic dataset validation summary (shape is backend-owned).
export interface ValidationSummary {
  [key: string]: unknown;
}

export interface DataSummaryResponse {
  data_mode: string;
  data_label: string;
  disclaimer: string;
  district_count: number;
  first_valid_date: string | null;
  last_valid_date: string | null;
  lead_hours: number[];
  total_observation_records: number;
  total_forecast_records: number;
  sources: SourceInfo[];
  source_record_counts: Record<string, number>;
  source_status_counts: Record<string, Record<string, number>>;
  source_health: SourceHealth[];
  rainfall_24h_overall: RainfallBuckets;
  districts: DistrictDataSummary[];
  validation: ValidationSummary;
}

// ---------------------------------------------------------------------------
// forecast endpoints (/forecast, /forecast/explain, /forecast/simulate-source-failure)
// ---------------------------------------------------------------------------

export interface DistrictRef {
  district_id: string;
  district_name: string;
}

export interface BiasMetadata {
  source_id: string;
  method: string;
  bias_available: boolean;
  bias_mm: number | null;
  raw_forecast_mm: number | null;
  corrected_forecast_mm: number | null;
  historical_record_count: number;
  reason: string;
}

export interface RegimeInfo {
  label: "Normal" | "Active Monsoon" | "Heavy-Rain Risk" | "Heatwave";
  confidence: number;
  triggered_rules: string[];
  thresholds_used: Record<string, number>;
  reason: string;
  rule_version: string;
}

export interface TrustComponent {
  source_id: string;
  source_type: string;
  display_name: string;
  eligible: boolean;
  health_status: string;
  health_score: number;
  historical_mae_mm: number | null;
  historical_record_count: number;
  historical_skill: number;
  recent_mae_mm: number | null;
  recent_record_count: number;
  recent_skill: number;
  agreement: number;
  context_factor: number;
  trust_score: number;
  weight: number;
  reason: string;
  ineligible_reason: string | null;
}

export interface ForecastSource {
  source_id: string;
  source_type: string;
  display_name: string;
  available: boolean;
  record_found: boolean;
  status: string;
  quality_flag: string;
  raw_forecast_mm: number | null;
  corrected_forecast_mm: number | null;
  bias: BiasMetadata;
  trust: TrustComponent;
  weight: number;
  ensemble?: { spread_mm?: number | null; p10_mm?: number | null; p90_mm?: number | null } | null;
  unavailable_reason: string | null;
  // Phase 4 ML provenance (ai_local_v1 only)
  model_inference_available?: boolean | null;
  source_label?: string | null;
  model_version?: string | null;
  model_report_reference?: string | null;
  model_inference_reason?: string | null;
}

export interface BlendContribution {
  source_id: string;
  weight: number;
  corrected_mm: number;
  contribution_mm: number;
}

export interface BlendInfo {
  final_rainfall_mm: number;
  formula: string;
  fallback_mode: "normal" | "degraded" | "single_source";
  fallback_note: string;
  available_source_count: number;
  contributions: BlendContribution[];
  unavailable_sources: string[];
}

export interface ConfidenceInfo {
  score: number;
  label: "Low" | "Medium" | "High";
  bands: string;
  factors: Record<string, number>;
  explanation: string[];
  uncertainty_lower_mm: number | null;
  uncertainty_upper_mm: number | null;
  uncertainty_half_width_mm: number | null;
  uncertainty_basis: string;
}

export type RiskLevel = "Low" | "Moderate" | "High" | "Critical";

export interface RiskInfo {
  event_type: string;
  risk_level: RiskLevel;
  predicted_rainfall_mm: number;
  validity_start: string;
  validity_end: string;
  confidence_score: number;
  confidence_label: string;
  regime: string;
  escalated: boolean;
  reasons: string[];
  preparedness_actions: string[];
  thresholds_used: Record<string, number>;
  disclaimer: string;
}

export interface MlModelInfo {
  source_label?: string | null;
  model_inference_available?: boolean | null;
  model_version?: string | null;
  model_report_reference?: string | null;
  held_out_test_mae_mm?: number | null;
  ai_local_model_prediction_mm?: number | null;
  feature_availability?: unknown;
  reason?: string | null;
  [key: string]: unknown;
}

export interface ForecastResponse {
  disclaimer: string;
  data_mode: string;
  data_label: string;
  algorithm_version: string;
  config_version: string;
  district: DistrictRef;
  valid_date: string;
  lead_hours: 6 | 24 | 72;
  issue_time: string;
  validity_start: string;
  validity_end: string;
  simulate_failure_source: string | null;
  data_availability: Record<string, unknown>;
  prior_context: Record<string, unknown>;
  weather_regime: RegimeInfo;
  source_health: SourceHealth[];
  sources: ForecastSource[];
  blend: BlendInfo;
  fallback_mode: "normal" | "degraded" | "single_source";
  confidence: ConfidenceInfo;
  risk: RiskInfo;
  ml_model: MlModelInfo;
}

export interface ExplainSourceLine {
  source_id: string;
  display_name: string;
  health_status: string;
  corrected_forecast_mm: number | null;
  weight: number;
  reason: string;
}

export interface ForecastExplainResponse {
  disclaimer: string;
  data_mode: string;
  data_label: string;
  algorithm_version: string;
  config_version: string;
  district: DistrictRef;
  valid_date: string;
  lead_hours: 6 | 24 | 72;
  headline: string;
  final_rainfall_mm: number;
  regime: RegimeInfo;
  confidence: ConfidenceInfo;
  risk: RiskInfo;
  top_weighted_source: ExplainSourceLine;
  sources: ExplainSourceLine[];
  source_health_note: string;
  fallback_mode: "normal" | "degraded" | "single_source";
  fallback_note: string;
  why_this_forecast_title: string;
  why_this_forecast: string[];
  ml_model: MlModelInfo;
}

export interface ForecastSummary {
  final_rainfall_mm: number;
  confidence_score: number;
  confidence_label: string;
  fallback_mode: "normal" | "degraded" | "single_source";
  weights: Record<string, number>;
  available_sources: string[];
  regime: string;
  risk_level: string;
}

export interface WeightChange {
  source_id: string;
  display_name: string;
  weight_before: number;
  weight_after: number;
  delta: number;
  trust_score_before: number;
  trust_score_after: number;
}

export interface SimulateFailureResponse {
  disclaimer: string;
  data_mode: string;
  data_label: string;
  algorithm_version: string;
  config_version: string;
  district: DistrictRef;
  valid_date: string;
  lead_hours: 6 | 24 | 72;
  failed_source: "nwp" | "ensemble" | "ai";
  failed_source_id: string;
  normal: ForecastSummary;
  degraded: ForecastSummary;
  weight_changes: WeightChange[];
  confidence_change: {
    normal: number;
    degraded: number;
    delta: number;
  };
  rainfall_change_mm: number;
  fallback_mode_change: {
    normal: "normal" | "degraded" | "single_source";
    degraded: "normal" | "degraded" | "single_source";
  };
  explanation: string[];
}

// ---------------------------------------------------------------------------
// backtest endpoints (/backtest, /backtest/report)
// ---------------------------------------------------------------------------

export interface RegressionMetricsModel {
  sample_count: number;
  mae_mm: number | null;
  rmse_mm: number | null;
  mean_bias_error_mm: number | null;
  median_absolute_error_mm: number | null;
  max_absolute_error_mm: number | null;
  note: string | null;
}

export interface EventMetricsModel {
  threshold_mm: number;
  sample_count: number;
  event_count: number | null;
  predicted_event_count: number | null;
  true_positives: number | null;
  false_positives: number | null;
  true_negatives: number | null;
  false_negatives: number | null;
  precision: number | null;
  recall: number | null;
  f1_score: number | null;
  false_alarm_rate: number | null;
  note: string | null;
}

export interface MethodEvaluation {
  display_name: string;
  regression_metrics: RegressionMetricsModel;
  event_metrics: EventMetricsModel;
}

export interface MethodSet {
  nwp: MethodEvaluation;
  ensemble: MethodEvaluation;
  ai_local: MethodEvaluation;
  equal_weight: MethodEvaluation;
  varsha_dynamic_blend: MethodEvaluation;
}

export interface BacktestRequestEcho {
  district: string;
  district_id: string;
  lead_hours: 6 | 24 | 72;
  start_date: string;
  end_date: string;
  minimum_history_days: number;
  heavy_rain_threshold_mm: number;
  include_daily_rows: boolean;
}

export interface BacktestDataRange {
  dataset_first_valid_date: string;
  dataset_last_valid_date: string;
  requested_start_date: string;
  requested_end_date: string;
  dates_in_dataset_range: number;
}

export interface EvaluationSummary {
  total_requested_dates: number;
  evaluated_dates: number;
  skipped_dates: number;
  skipped_reason_counts: Record<string, number>;
  sufficient_sample_warning: string | null;
}

export interface EventThresholdInfo {
  configured_threshold_mm: number;
  effective_threshold_mm: number;
  lead_hours: number;
  scaling_applied: boolean;
  basis: string;
}

export interface ComparisonSummary {
  delta_definition: string;
  outcome_basis: string;
  best_method_by_metric: Record<string, string | null>;
  best_single_source: string | null;
  varsha_vs_equal_weight_mae_delta_mm: number | null;
  varsha_vs_best_single_source_mae_delta_mm: number | null;
  varsha_vs_equal_weight_recall_delta: number | null;
  varsha_vs_best_single_source_recall_delta: number | null;
  sufficient_sample: boolean;
  note: string | null;
  outcome_summary: string[];
}

export interface BacktestResponse {
  data_mode: string;
  disclaimer: string;
  algorithm_version: string;
  config_version: string;
  request: BacktestRequestEcho;
  data_range: BacktestDataRange;
  evaluation_summary: EvaluationSummary;
  event_threshold: EventThresholdInfo;
  methods: MethodSet;
  comparison_summary: ComparisonSummary;
  daily_rows?: unknown[] | null;
  limitations: string[];
  report_files: Record<string, string>;
  ai_source_provenance: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// model endpoints (/model/status, /model/report)
// ---------------------------------------------------------------------------

export interface ModelLeadStatus {
  artifact_exists: boolean;
  model_version: string | null;
  trained_at: string | null;
  selected_model: string | null;
  held_out_test_mae_mm: number | null;
  inference_ready: boolean;
  artifact_error: string | null;
}

export interface ModelFallbackStatus {
  active: boolean;
  label: string;
  reason: string;
}

export interface ModelStatusResponse {
  artifact_exists: boolean;
  model_version: string | null;
  trained_lead_hours: number[];
  inference_enabled: boolean;
  inference_ready: boolean;
  last_training_time: string | null;
  data_mode: string;
  disclaimer: string;
  models_dir: string;
  per_lead: Record<string, ModelLeadStatus>;
  fallback_status: ModelFallbackStatus;
  note: string;
}

export interface ModelReportResponse {
  report_type: string;
  status: "completed" | "already_trained" | "skipped_insufficient_data";
  message: string | null;
  generated_at: string;
  data_mode: string;
  disclaimer: string;
  lead_hours: number;
  model_version: string | null;
  selected_model: string | null;
  selection_rationale: string;
  split: Record<string, unknown> | null;
  record_counts: Record<string, unknown> | null;
  row_exclusions: Record<string, unknown> | null;
  feature_schema: Record<string, unknown>;
  candidates: Record<string, unknown>;
  held_out_test_metrics: {
    model_name?: string;
    sample_count?: number;
    mae_mm?: number | null;
    rmse_mm?: number | null;
    mean_bias_error_mm?: number | null;
    [key: string]: unknown;
  } | null;
  test_references: {
    naive_train_mean?: { mae_mm?: number | null };
    raw_nwp?: { mae_mm?: number | null };
    precomputed_ai_source?: { mae_mm?: number | null };
    [key: string]: unknown;
  } | null;
  honesty: Record<string, unknown> & {
    ml_worse_than_baseline?: boolean;
    worse_than_references?: string[];
    summary_sentences?: string[];
  };
  artifacts: Record<string, unknown> | null;
  fallback: Record<string, unknown>;
  provenance: Record<string, unknown> | null;
  warnings: string[];
  limitations: string[];
}

// ---------------------------------------------------------------------------
// audit endpoints (/overrides, /audit-logs)
// ---------------------------------------------------------------------------

export interface OverrideCreateBody {
  district: string;
  date: string;
  lead_hours: number;
  selected_risk_level: RiskLevel;
  reason: string;
  reviewer_name?: string | null;
  role?: "forecaster" | "administrator";
}

export interface OverrideRecord {
  id: number;
  created_at: string;
  actor: string;
  role: string;
  district_id: string;
  district_name: string;
  valid_date: string;
  lead_hours: number;
  original_risk_level: string;
  original_forecast_mm: number | null;
  overridden_risk_level: string;
  reason: string;
  original_output: Record<string, unknown>;
}

export interface OverrideCreateResponse {
  data_mode: string;
  disclaimer: string;
  note: string;
  record: OverrideRecord;
}

export interface AuditLogEntry {
  id: number;
  kind: "override" | "system";
  created_at: string;
  actor: string;
  role: string;
  action: string | null;
  district_id: string | null;
  district_name: string | null;
  valid_date: string | null;
  lead_hours: number | null;
  original_risk_level: string | null;
  original_forecast_mm: number | null;
  overridden_risk_level: string | null;
  reason: string | null;
  details: Record<string, unknown>;
}

export interface AuditLogsResponse {
  data_mode: string;
  disclaimer: string;
  note: string;
  count: number;
  entries: AuditLogEntry[];
}

// ---------------------------------------------------------------------------
// request parameter shapes used by the typed API client
// ---------------------------------------------------------------------------

export interface ForecastParams {
  district: string;
  date: string;
  lead_hours: number;
  simulate_failure_source?: "nwp" | "ensemble" | "ai" | null;
}

export interface BacktestParams {
  district: string;
  lead_hours: number;
  start_date: string;
  end_date: string;
}

export interface SimulateFailureBody {
  district: string;
  date: string;
  lead_hours: number;
  failed_source: "nwp" | "ensemble" | "ai";
}