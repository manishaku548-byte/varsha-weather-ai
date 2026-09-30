"""Pydantic v2 schemas for the Phase 4 model endpoints (G).

Every response carries the mandatory label
``Synthetic Development Dataset — Development/Testing Only — Not Operational
Weather Data — Not an Official Weather Warning.`` via ``disclaimer``.

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ModelTrainRequest(BaseModel):
    """Body for POST /model/train."""

    lead_hours: Literal[6, 24, 72] = Field(
        ..., description="Lead horizon to train the model for.", examples=[24]
    )
    minimum_samples: Optional[int] = Field(
        default=None,
        ge=1,
        description="Minimum required training rows (overrides the configured "
        "ml_min_train_rows default). Training is skipped with a clear warning "
        "when the dataset cannot meet it — no model is fitted on inadequate data.",
        examples=[200],
    )
    force_retrain: bool = Field(
        default=False,
        description="Retrain even when a validated artifact already exists for "
        "this lead horizon.",
    )


class ModelReportResponse(BaseModel):
    """Training result (POST /model/train) and saved report (GET /model/report).

    The payload is the model report itself: split boundaries and record counts,
    per-candidate validation metrics, the validation-MAE selection rationale,
    the single held-out test evaluation, honest baseline references, artifact
    paths, feature schema, provenance, fallback status, warnings and
    limitations.
    """

    report_type: str = Field(description="local_correction_model")
    status: Literal["completed", "already_trained", "skipped_insufficient_data"]
    message: Optional[str] = None
    generated_at: str
    data_mode: str
    disclaimer: str = Field(
        description="Mandatory Phase 4 label carried by every model response."
    )
    lead_hours: int
    model_version: Optional[str] = None
    selected_model: Optional[str] = Field(
        default=None,
        description="Winner by validation MAE; None when training was skipped.",
    )
    selection_rationale: str
    split: Optional[dict] = Field(
        default=None,
        description="Chronological split method, ratio, exact date boundaries "
        "and per-split record counts.",
    )
    record_counts: Optional[dict] = None
    row_exclusions: Optional[dict] = Field(
        default=None,
        description="Rows excluded from training by feature_availability / "
        "missing target, with counts.",
    )
    feature_schema: dict = Field(
        description="Feature schema version, numeric/categorical feature lists, "
        "target column and per-feature leakage documentation."
    )
    candidates: dict = Field(
        description="Both candidates with their validation metrics (train-fitted, "
        "validation-evaluated).",
    )
    held_out_test_metrics: Optional[dict] = Field(
        default=None,
        description="The selected model's metrics on the untouched future test "
        "split — evaluated exactly once, after selection.",
    )
    test_references: Optional[dict] = Field(
        default=None,
        description="Honest reference predictors on the same test rows "
        "(naive mean, raw NWP, precomputed AI source).",
    )
    honesty: dict = Field(
        description="Selection/test-use policy flags plus "
        "ml_worse_than_baseline.",
    )
    artifacts: Optional[dict] = Field(
        default=None, description="Saved pipeline/report filenames and paths."
    )
    fallback: dict = Field(
        description="Whether the rule-based fallback source is active and why."
    )
    provenance: Optional[dict] = None
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ModelLeadStatus(BaseModel):
    """Per-lead artifact and readiness state (computed from disk)."""

    artifact_exists: bool
    model_version: Optional[str] = None
    trained_at: Optional[str] = None
    selected_model: Optional[str] = None
    held_out_test_mae_mm: Optional[float] = None
    inference_ready: bool
    artifact_error: Optional[str] = None


class ModelFallbackStatus(BaseModel):
    active: bool
    label: str = Field(
        description="trained_local_correction_model when ready, else "
        "fallback_precomputed_ai_source."
    )
    reason: str


class ModelStatusResponse(BaseModel):
    """GET /model/status — artifact existence, readiness and fallback state."""

    artifact_exists: bool
    model_version: Optional[str] = None
    trained_lead_hours: list[int] = Field(default_factory=list)
    inference_enabled: bool
    inference_ready: bool
    last_training_time: Optional[str] = None
    data_mode: str
    disclaimer: str
    models_dir: str
    per_lead: dict[str, ModelLeadStatus] = Field(default_factory=dict)
    fallback_status: ModelFallbackStatus
    note: str = Field(
        description="Training never runs automatically at startup."
    )
