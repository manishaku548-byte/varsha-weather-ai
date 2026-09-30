"""Pydantic v2 data contracts for the VARSHA Weather AI API.

Every response model carries the mandatory decision-support disclaimer and the
dataset label so no screen or payload can silently look official/operational.

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SourceHealthStatus = Literal["Healthy", "Delayed", "Unavailable", "Anomalous"]


class District(BaseModel):
    """District metadata used for filtering, mapping and display."""

    district_id: str = Field(description="Stable slug, e.g. 'prayagraj'")
    district_name: str = Field(description="Display name, e.g. 'Prayagraj'")
    state: str = Field(description="State name")
    latitude: float = Field(description="District centroid latitude (prototype placeholder)")
    longitude: float = Field(description="District centroid longitude (prototype placeholder)")

    model_config = {"json_schema_extra": {"example": {
        "district_id": "prayagraj",
        "district_name": "Prayagraj",
        "state": "Uttar Pradesh",
        "latitude": 25.4358,
        "longitude": 81.8463,
    }}}


class SourceInfo(BaseModel):
    """Registered forecast source metadata (SRS FR-SRC-01/02)."""

    source_id: str
    source_type: str = Field(description="NWP | Ensemble | AI_ML | Observation")
    display_name: str
    description: str = ""


class SourceHealth(BaseModel):
    """Health of one source over the recent evaluation window."""

    source_id: str
    source_type: str
    status: SourceHealthStatus
    window_days: int
    records_in_window: int
    unavailable_ratio: float = Field(description="Share of unavailable records in window")
    delayed_ratio: float = Field(description="Share of delayed records in window")
    anomalous_ratio: float = Field(description="Share of anomalous records in window")
    reason: str = Field(description="Human-readable reason for the assigned status")


class ValidationSummary(BaseModel):
    """Data-quality report: structural contract vs. record-level quality flags."""

    structure_ok: bool = Field(description="True when all required columns/units/keys are valid")
    blocking_issues: list[str] = Field(
        default_factory=list, description="Contract violations that must be fixed"
    )
    quality_flags: dict[str, int] = Field(
        default_factory=dict,
        description="Record-level quality counters (implausible/missing/unexpected values)",
    )
    checked_forecast_rows: int
    checked_observation_rows: int


class RainfallBuckets(BaseModel):
    """Counts of 24-hour observed rainfall days per category (configurable thresholds)."""

    dry: int = Field(description="0 to <0.1 mm")
    light: int = Field(description="0.1 to 15.5 mm")
    moderate: int = Field(description="15.6 to 64.4 mm")
    heavy: int = Field(description="64.5 to 115.5 mm")
    very_heavy: int = Field(description="115.6 to 204.4 mm")
    extreme: int = Field(description="above 204.4 mm")


class DistrictDataSummary(BaseModel):
    """Per-district dataset summary."""

    district_id: str
    district_name: str
    first_valid_date: Optional[str] = None
    last_valid_date: Optional[str] = None
    observation_records: int
    forecast_records: int
    rainfall_24h: RainfallBuckets
    max_observed_24h_mm: Optional[float] = None
    mean_observed_24h_mm: Optional[float] = None


class DataSummaryResponse(BaseModel):
    """Overview of the loaded replay dataset (never a forecast)."""

    data_mode: str = Field(description="synthetic | historical_replay")
    data_label: str
    disclaimer: str
    district_count: int
    first_valid_date: Optional[str] = None
    last_valid_date: Optional[str] = None
    lead_hours: list[int]
    total_observation_records: int
    total_forecast_records: int
    sources: list[SourceInfo]
    source_record_counts: dict[str, int]
    source_status_counts: dict[str, dict[str, int]] = Field(
        description="source_id -> status -> row count"
    )
    source_health: list[SourceHealth]
    rainfall_24h_overall: RainfallBuckets
    districts: list[DistrictDataSummary]
    validation: ValidationSummary


class DistrictListResponse(BaseModel):
    data_mode: str
    data_label: str
    disclaimer: str
    count: int
    districts: list[District]


class HealthResponse(BaseModel):
    """Service health plus dataset/dependency status."""

    status: Literal["ok", "degraded"]
    service: str
    version: str
    phase: str
    problem_statement_id: str
    data_mode: str
    data_label: str
    disclaimer: str
    dataset_loaded: bool
    database_status: Literal["connected", "error"]
    records: dict[str, int] = Field(
        default_factory=dict, description="Row counts when the dataset is loaded"
    )
