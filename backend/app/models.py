"""Database models: audit trail and expert overrides.

Both tables are append-only from the API's point of view; the original system
output is always preserved alongside the expert decision (SRS FR-OVR-02,
FR-AUD-01/02, NFR-AI-04).

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """Immutable activity record: ingestion, forecast, review, override."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow, index=True)
    actor = Column(String(120), nullable=False, default="system")
    role = Column(String(40), nullable=False, default="system")
    action = Column(String(60), nullable=False)  # e.g. forecast.generated, override.created
    district_id = Column(String(60), nullable=True)
    forecast_reference = Column(String(120), nullable=True)  # district|date|lead key
    details = Column(Text, nullable=False, default="{}")  # JSON string payload

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AuditLog {self.id} {self.action} {self.created_at}>"


class OverrideDecision(Base):
    """Expert override of a system recommendation (reason is mandatory)."""

    __tablename__ = "override_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow, index=True)
    actor = Column(String(120), nullable=False)
    role = Column(String(40), nullable=False, default="forecaster")
    district_id = Column(String(60), nullable=False)
    valid_date = Column(String(20), nullable=False)  # YYYY-MM-DD
    lead_hours = Column(Integer, nullable=False, default=24)
    original_risk_level = Column(String(20), nullable=False)
    original_forecast_mm = Column(Float, nullable=True)
    overridden_risk_level = Column(String(20), nullable=False)
    reason = Column(Text, nullable=False)  # enforced non-empty at the API layer
    original_output_json = Column(Text, nullable=False, default="{}")  # preserved system output

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<OverrideDecision {self.id} {self.district_id} {self.valid_date}>"
