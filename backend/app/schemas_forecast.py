"""Pydantic v2 contracts for the Phase 2 Forecast Intelligence endpoints.

Every response model carries the mandatory disclaimer and dataset label so no
payload can silently look official/operational.

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .schemas import SourceHealth

FailureSourceAlias = Literal["nwp", "ensemble", "ai"]


class DistrictRef(BaseModel):
    district_id: str
    district_name: str


class BiasMetadata(BaseModel):
    """Bias-correction audit trail for one source (SRS FR-BC-01..06)."""

    source_id: str
    method: str = Field(description="e.g. 'mean_bias_prior_only'")
    bias_available: bool = Field(
        description="False when there is insufficient strictly-prior history"
    )
    bias_mm: Optional[float] = Field(
        default=None, description="mean(observed - forecast) over prior records"
    )
    raw_forecast_mm: Optional[float] = None
    corrected_forecast_mm: Optional[float] = None
    historical_record_count: int = Field(
        description="Prior usable records used (strictly earlier than the date)"
    )
    reason: str


class RegimeInfo(BaseModel):
    """Transparent rule-based regime classification (SRS FR-REG-01..05)."""

    label: Literal["Normal", "Active Monsoon", "Heavy-Rain Risk", "Heatwave"]
    confidence: float = Field(ge=0.0, le=1.0)
    triggered_rules: list[str] = Field(default_factory=list)
    thresholds_used: dict[str, float] = Field(default_factory=dict)
    reason: str
    rule_version: str = "regime-rules-v1"
    certification_note: str = (
        "Prototype rule set — no meteorological operational certification claimed."
    )


class TrustComponent(BaseModel):
    """Score components for one source (SRS FR-DTE-01..06)."""

    source_id: str
    source_type: str
    display_name: str
    eligible: bool
    health_status: str
    health_score: float = Field(description="Healthy 1.0 / Delayed / Anomalous / Unavailable 0.0")
    historical_mae_mm: Optional[float] = None
    historical_record_count: int = 0
    historical_skill: float = Field(description="1 / (1 + MAE / scale), 0-1")
    recent_mae_mm: Optional[float] = None
    recent_record_count: int = 0
    recent_skill: float
    agreement: float = Field(description="Proximity to the peer median, 0-1")
    context_factor: float = Field(description="Regime x lead-time multiplicative factor")
    trust_score: float = Field(ge=0.0, description="Combined score before normalization")
    weight: float = Field(ge=0.0, le=1.0, description="Normalized dynamic weight")
    reason: str = Field(description="Source-specific plain-language reason")
    ineligible_reason: Optional[str] = None


class ForecastSource(BaseModel):
    """Raw + corrected prediction, bias metadata, trust and weight per source."""

    source_id: str
    source_type: str
    display_name: str
    available: bool = Field(description="True when the source contributes (weight > 0)")
    record_found: bool
    status: str = Field(description="Record status: ok | delayed | anomalous | unavailable | missing | model_inference")
    quality_flag: str
    raw_forecast_mm: Optional[float] = None
    corrected_forecast_mm: Optional[float] = None
    bias: BiasMetadata
    trust: TrustComponent
    weight: float = Field(ge=0.0, le=1.0)
    ensemble: Optional[dict] = Field(
        default=None, description="spread/p10/p90 for the ensemble source"
    )
    unavailable_reason: Optional[str] = None
    # --- Phase 4 ML provenance (populated for ai_local_v1 only) ----------------
    model_inference_available: Optional[bool] = Field(
        default=None,
        description="True when this AI-source value came from the trained local "
        "correction model; False when it is the disclosed precomputed fallback.",
    )
    source_label: Optional[str] = Field(
        default=None,
        description="trained_local_correction_model | fallback_precomputed_ai_source "
        "(AI source only; other sources are None).",
    )
    model_version: Optional[str] = None
    model_report_reference: Optional[str] = None
    model_inference_reason: Optional[str] = None


class BlendContribution(BaseModel):
    source_id: str
    weight: float
    corrected_mm: float
    contribution_mm: float


class BlendInfo(BaseModel):
    """Weighted blend of bias-corrected forecasts (SRS FR-BLD-01..06)."""

    final_rainfall_mm: float
    formula: str = "final_rainfall_mm = sum(weight x corrected_forecast)"
    fallback_mode: Literal["normal", "degraded", "single_source"]
    fallback_note: str
    available_source_count: int
    contributions: list[BlendContribution]
    unavailable_sources: list[str]


class ConfidenceInfo(BaseModel):
    """Confidence score 0-100 with factors and prototype uncertainty range."""

    score: float = Field(ge=0.0, le=100.0)
    label: Literal["Low", "Medium", "High"]
    bands: str = "Low 0-39 | Medium 40-69 | High 70-100"
    factors: dict[str, float] = Field(
        default_factory=dict, description="Each factor normalized to 0-1"
    )
    explanation: list[str] = Field(default_factory=list)
    uncertainty_lower_mm: Optional[float] = None
    uncertainty_upper_mm: Optional[float] = None
    uncertainty_half_width_mm: Optional[float] = None
    uncertainty_basis: str = ""


class RiskInfo(BaseModel):
    """Rainfall risk guidance (SRS FR-RISK-01..06), non-binding."""

    event_type: str
    risk_level: Literal["Low", "Moderate", "High", "Critical"]
    predicted_rainfall_mm: float
    validity_start: str
    validity_end: str
    confidence_score: float
    confidence_label: str
    regime: str
    escalated: bool = Field(
        description="True when the Heavy-Rain Risk regime raised the base level"
    )
    reasons: list[str] = Field(default_factory=list)
    preparedness_actions: list[str] = Field(
        default_factory=list, description="Non-binding preparedness suggestions"
    )
    thresholds_used: dict[str, float] = Field(default_factory=dict)
    disclaimer: str


class ForecastResponse(BaseModel):
    """Full forecast package returned by GET /forecast."""

    disclaimer: str
    data_mode: str
    data_label: str
    algorithm_version: str = Field(description="Audit-friendly blending algorithm version")
    config_version: str = Field(description="Audit-friendly threshold/config version")
    district: DistrictRef
    valid_date: str
    lead_hours: Literal[6, 24, 72]
    issue_time: str
    validity_start: str
    validity_end: str
    simulate_failure_source: Optional[FailureSourceAlias] = None
    data_availability: dict
    prior_context: dict = Field(
        description="Observational context used by regime rules (strictly prior dates)"
    )
    weather_regime: RegimeInfo
    source_health: list[SourceHealth]
    sources: list[ForecastSource]
    blend: BlendInfo
    fallback_mode: Literal["normal", "degraded", "single_source"]
    confidence: ConfidenceInfo
    risk: RiskInfo
    ml_model: dict = Field(
        default_factory=dict,
        description="Phase 4 AI-source provenance: source_label "
        "(trained_local_correction_model | fallback_precomputed_ai_source), "
        "model_inference_available, model_version, report reference, "
        "ai_local_model_prediction_mm and the fallback reason.",
    )


class ExplainSourceLine(BaseModel):
    source_id: str
    display_name: str
    health_status: str
    corrected_forecast_mm: Optional[float] = None
    weight: float
    reason: str


class ForecastExplainResponse(BaseModel):
    """Compact plain-language explanation returned by GET /forecast/explain."""

    disclaimer: str
    data_mode: str
    data_label: str
    algorithm_version: str
    config_version: str
    district: DistrictRef
    valid_date: str
    lead_hours: Literal[6, 24, 72]
    headline: str
    final_rainfall_mm: float
    regime: RegimeInfo
    confidence: ConfidenceInfo
    risk: RiskInfo
    top_weighted_source: ExplainSourceLine
    sources: list[ExplainSourceLine]
    source_health_note: str
    fallback_mode: Literal["normal", "degraded", "single_source"]
    fallback_note: str
    why_this_forecast_title: str = "Why this forecast?"
    why_this_forecast: list[str] = Field(
        description="Bullet list computed from the same numbers as /forecast"
    )
    ml_model: dict = Field(
        default_factory=dict,
        description="Phase 4 AI-source provenance (same block as GET /forecast).",
    )


class ForecastSummary(BaseModel):
    """Compact summary used by the failure-simulation comparison."""

    final_rainfall_mm: float
    confidence_score: float
    confidence_label: str
    fallback_mode: Literal["normal", "degraded", "single_source"]
    weights: dict[str, float]
    available_sources: list[str]
    regime: str
    risk_level: str


class WeightChange(BaseModel):
    source_id: str
    display_name: str
    weight_before: float
    weight_after: float
    delta: float
    trust_score_before: float
    trust_score_after: float


class SimulateFailureResponse(BaseModel):
    """Normal vs degraded comparison from POST /forecast/simulate-source-failure."""

    disclaimer: str
    data_mode: str
    data_label: str
    algorithm_version: str
    config_version: str
    district: DistrictRef
    valid_date: str
    lead_hours: Literal[6, 24, 72]
    failed_source: FailureSourceAlias
    failed_source_id: str
    normal: ForecastSummary
    degraded: ForecastSummary
    weight_changes: list[WeightChange]
    confidence_change: dict
    rainfall_change_mm: float
    fallback_mode_change: dict
    explanation: list[str]
