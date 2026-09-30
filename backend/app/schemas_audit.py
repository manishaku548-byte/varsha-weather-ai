"""Pydantic contracts for the Phase 5 expert-review endpoints.

* ``POST /overrides``   — record an expert override of the system risk decision.
* ``GET  /audit-logs``  — local review/audit timeline (override + system events).

These are a *prototype local review log*, not an official authorization record,
and there is no authentication provider. The original system output is always
preserved next to the expert decision (SRS FR-OVR-02, FR-AUD-01/02, NFR-AI-04).

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

RiskLevel = Literal["Low", "Moderate", "High", "Critical"]


class OverrideCreateRequest(BaseModel):
    """Body for POST /overrides (reason is mandatory)."""

    district: str = Field(..., examples=["Prayagraj"])
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", examples=["2025-09-15"])
    lead_hours: Literal[6, 24, 72] = Field(..., examples=[24])
    selected_risk_level: RiskLevel = Field(
        ..., description="Expert-chosen risk level for this forecast point."
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Mandatory plain-language reason for the override.",
        examples=["District control room reports ponding; escalate to High for "
                  "preparedness drills."],
    )
    reviewer_name: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Optional display name of the reviewing expert.",
        examples=["A. Kumar"],
    )
    role: Literal["forecaster", "administrator"] = Field(
        default="forecaster",
        description="Local role label used for the demo only — not authorization.",
    )


class OverrideRecord(BaseModel):
    """One stored expert override with the preserved original system output."""

    id: int
    created_at: str = Field(description="ISO-8601 UTC timestamp.")
    actor: str = Field(description="Reviewer display name (or role when unnamed).")
    role: str
    district_id: str
    district_name: str
    valid_date: str
    lead_hours: int
    original_risk_level: str = Field(
        description="System risk decision before the override (preserved)."
    )
    original_forecast_mm: Optional[float] = None
    overridden_risk_level: str
    reason: str
    original_output: dict = Field(
        default_factory=dict,
        description="Compact preserved system output at the time of the override.",
    )


class OverrideCreateResponse(BaseModel):
    """POST /overrides acknowledgement."""

    data_mode: str
    disclaimer: str
    note: str = Field(
        description="Prototype local review log — not an official authorization record."
    )
    record: OverrideRecord


class AuditLogEntry(BaseModel):
    """One entry of the local review/audit timeline."""

    id: int
    kind: Literal["override", "system"]
    created_at: str
    actor: str
    role: str
    action: Optional[str] = Field(
        None, description="System action label (system entries only)."
    )
    district_id: Optional[str] = None
    district_name: Optional[str] = None
    valid_date: Optional[str] = None
    lead_hours: Optional[int] = None
    original_risk_level: Optional[str] = None
    original_forecast_mm: Optional[float] = None
    overridden_risk_level: Optional[str] = None
    reason: Optional[str] = None
    details: dict = Field(default_factory=dict)


class AuditLogsResponse(BaseModel):
    """GET /audit-logs — newest first, overrides and system events merged."""

    data_mode: str
    disclaimer: str
    note: str = Field(
        description="Prototype local review log — not an official authorization record."
    )
    count: int
    entries: list[AuditLogEntry] = Field(default_factory=list)