"""Pydantic response models for Phase 3 backtesting endpoints.

Display rounding is applied by the router before these models are built; the
underlying report files keep full engine precision.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class RegressionMetricsModel(BaseModel):
    """Error statistics in mm (null when a method has no evaluated rows)."""

    sample_count: int = Field(description="Number of (prediction, actual) pairs used.")
    mae_mm: Optional[float] = Field(None, description="Mean absolute error, mm.")
    rmse_mm: Optional[float] = Field(None, description="Root mean squared error, mm.")
    mean_bias_error_mm: Optional[float] = Field(
        None, description="mean(prediction - actual), mm; positive = over-prediction."
    )
    median_absolute_error_mm: Optional[float] = Field(None, description="Median |error|, mm.")
    max_absolute_error_mm: Optional[float] = Field(None, description="Max |error|, mm.")
    note: Optional[str] = Field(None, description="Why metrics are null, when applicable.")


class EventMetricsModel(BaseModel):
    """Heavy-rain event confusion matrix and scores at one threshold."""

    threshold_mm: float = Field(description="Effective event threshold used for both actual and predicted.")
    sample_count: int
    event_count: Optional[int] = Field(None, description="Observed events (TP + FN).")
    predicted_event_count: Optional[int] = None
    true_positives: Optional[int] = None
    false_positives: Optional[int] = None
    true_negatives: Optional[int] = None
    false_negatives: Optional[int] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    false_alarm_rate: Optional[float] = Field(
        None, description="FP / (FP + TN)."
    )
    missed_event_rate: Optional[float] = Field(None, description="FN / (TP + FN) = 1 - recall.")
    notes: list[str] = Field(default_factory=list, description="Zero-division explanations.")
    low_event_sample_warning: Optional[str] = Field(
        None, description="Set when the event count is too small for reliable scores."
    )


class MethodEvaluation(BaseModel):
    display_name: str
    regression_metrics: RegressionMetricsModel
    event_metrics: EventMetricsModel


class MethodSet(BaseModel):
    nwp: MethodEvaluation
    ensemble: MethodEvaluation
    ai_local: MethodEvaluation
    equal_weight: MethodEvaluation
    varsha_dynamic_blend: MethodEvaluation


class BacktestRequestEcho(BaseModel):
    district: str
    district_id: str
    lead_hours: Literal[6, 24, 72]
    start_date: str
    end_date: str
    minimum_history_days: int
    heavy_rain_threshold_mm: float = Field(
        description="Configured event threshold (24h-equivalent) used for the run."
    )
    include_daily_rows: bool = False


class BacktestDataRange(BaseModel):
    dataset_first_valid_date: str
    dataset_last_valid_date: str
    requested_start_date: str
    requested_end_date: str
    dates_in_dataset_range: int


class EvaluationSummary(BaseModel):
    total_requested_dates: int
    evaluated_dates: int
    skipped_dates: int
    skipped_reason_counts: dict[str, int]
    sufficient_sample_warning: Optional[str] = None


class EventThresholdInfo(BaseModel):
    configured_threshold_mm: float
    effective_threshold_mm: float
    lead_hours: int
    scaling_applied: bool
    basis: str


class ComparisonSummary(BaseModel):
    delta_definition: str
    outcome_basis: str
    best_method_by_metric: dict[str, Optional[str]]
    best_single_source: Optional[str]
    varsha_vs_equal_weight_mae_delta_mm: Optional[float]
    varsha_vs_best_single_source_mae_delta_mm: Optional[float]
    varsha_vs_equal_weight_recall_delta: Optional[float]
    varsha_vs_best_single_source_recall_delta: Optional[float]
    sufficient_sample: bool
    note: Optional[str]
    outcome_summary: list[str]


class BacktestDailyRow(BaseModel):
    """One walk-forward date (included or skipped) for include_daily_rows=true."""

    date: str
    district: str
    district_id: str
    lead_hours: int
    actual_rain_mm: Optional[float] = None
    nwp_prediction_mm: Optional[float] = None
    ensemble_prediction_mm: Optional[float] = None
    ai_prediction_mm: Optional[float] = None
    equal_weight_prediction_mm: Optional[float] = None
    varsha_prediction_mm: Optional[float] = None
    prior_history_days: int
    regime: Optional[str] = None
    nwp_weight: Optional[float] = None
    ensemble_weight: Optional[float] = None
    ai_weight: Optional[float] = None
    confidence_score: Optional[float] = None
    confidence_label: Optional[str] = None
    risk_level: Optional[str] = None
    fallback_mode: Optional[str] = None
    nwp_source_health: Optional[str] = None
    ensemble_source_health: Optional[str] = None
    ai_source_health: Optional[str] = None
    ai_source_label: Optional[str] = Field(
        default=None,
        description="Phase 4: trained_local_correction_model | "
        "fallback_precomputed_ai_source for this row's ai_local input.",
    )
    ai_model_version: Optional[str] = None
    included_in_evaluation: bool
    skip_reason: Optional[str] = None
    skip_reason_note: Optional[str] = None


class BacktestResponse(BaseModel):
    """GET /backtest — walk-forward evaluation over a date range."""

    data_mode: str
    disclaimer: str = Field(
        description="Mandatory Phase 3 label carried by every backtest response."
    )
    algorithm_version: str
    config_version: str
    request: BacktestRequestEcho
    data_range: BacktestDataRange
    evaluation_summary: EvaluationSummary
    event_threshold: EventThresholdInfo
    methods: MethodSet
    comparison_summary: ComparisonSummary
    daily_rows: Optional[list[BacktestDailyRow]] = Field(
        None, description="Present only when include_daily_rows=true."
    )
    limitations: list[str]
    report_files: dict[str, str] = Field(
        description="Deterministic CSV/JSON report filenames written under data/reports/."
    )
    ai_source_provenance: dict = Field(
        description="Phase 4: whether this run's ai_local predictions came from "
        "the trained local correction model or the precomputed fallback source."
    )


class BacktestReportResponse(BaseModel):
    """GET /backtest/report?format=json — stored or freshly generated summary."""

    report_type: str
    report_source: Literal["stored", "generated"]
    generated_at: str
    algorithm_version: str
    config_version: str
    data_mode: str
    disclaimer: str
    request: dict
    data_range: dict
    evaluation_summary: dict
    event_threshold: dict
    methods: dict
    metrics_table: list[dict]
    comparison_summary: dict
    row_counts: dict
    files: dict[str, str]
    limitations: list[str]
    ai_source_provenance: Optional[dict] = Field(
        default=None,
        description="Phase 4 AI-source provenance; legacy pre-Phase-4 reports "
        "are marked as fallback_precomputed_ai_source when served.",
    )
