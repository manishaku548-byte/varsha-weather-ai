"""Phase 5 expert-review endpoints.

* ``POST /overrides`` — record an expert override of the system risk decision
  for one district/date/horizon. The *system's own output* (computed here by
  the same Forecast Intelligence Engine, never supplied by the caller) is
  always preserved next to the expert decision (SRS FR-OVR-02, FR-AUD-01/02).
* ``GET  /audit-logs`` — newest-first local timeline of override and system
  events from the SQLite audit tables.

This is a prototype local review log, NOT an official authorization record,
and there is no authentication provider (SRS NFR-REL-05 storage only).

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import AuditLog, OverrideDecision
from ..schemas_audit import (
    AuditLogEntry,
    AuditLogsResponse,
    OverrideCreateRequest,
    OverrideCreateResponse,
    OverrideRecord,
)
from ..services.dataset import get_dataset
from .forecast import _resolve, _run, _validate_lead

router = APIRouter()

OVERRIDE_NOTE = (
    "Prototype local review log — not an official authorization record."
)


def _utc_iso(value) -> str:
    """Serialize a stored UTC datetime as ISO-8601 (SQLite may return naive)."""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse_date(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_date",
                "message": f"Invalid date '{value}'; expected YYYY-MM-DD.",
            },
        ) from None
    return parsed.date().isoformat()


def _override_dict(row: OverrideDecision) -> dict:
    try:
        original_output = json.loads(row.original_output_json or "{}")
    except ValueError:
        original_output = {}
    return {
        "id": int(row.id),
        "created_at": _utc_iso(row.created_at),
        "actor": row.actor,
        "role": row.role,
        "district_id": row.district_id,
        "district_name": str(_district_display_name(row.district_id)),
        "valid_date": row.valid_date,
        "lead_hours": int(row.lead_hours),
        "original_risk_level": row.original_risk_level,
        "original_forecast_mm": row.original_forecast_mm,
        "overridden_risk_level": row.overridden_risk_level,
        "reason": row.reason,
        "original_output": original_output,
    }


def _audit_dict(row: AuditLog) -> dict:
    try:
        details = json.loads(row.details or "{}")
    except ValueError:
        details = {}
    return {
        "id": int(row.id),
        "kind": "system",
        "created_at": _utc_iso(row.created_at),
        "actor": row.actor,
        "role": row.role,
        "action": row.action,
        "district_id": row.district_id,
        "district_name": (
            _district_display_name(row.district_id) if row.district_id else None
        ),
        "valid_date": None,
        "lead_hours": None,
        "original_risk_level": None,
        "original_forecast_mm": None,
        "overridden_risk_level": None,
        "reason": None,
        "details": details,
    }


def _district_display_name(district_id: str) -> str:
    """Resolve a stored district id back to its display name (best effort)."""
    from ..services.dataset import get_dataset

    try:
        ds = get_dataset()
        names = {
            str(r["district_id"]): str(r["district_name"])
            for r in ds.districts.to_dict("records")
        }
        return names.get(district_id, district_id)
    except Exception:  # pragma: no cover - dataset unavailable fallback
        return district_id


@router.post(
    "/overrides",
    response_model=OverrideCreateResponse,
    tags=["audit"],
    summary="Record a local expert override (reason mandatory, system output preserved)",
)
def create_override(
    body: OverrideCreateRequest,
    db: Session = Depends(get_db),
) -> OverrideCreateResponse:
    """Create an append-only override record.

    The original system risk/forecast is recomputed by the engine for the same
    district/date/horizon so the stored decision is always self-consistent —
    the caller never supplies the "original" values.
    """
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "reason_required",
                "message": "A non-empty review reason is mandatory for an override "
                "(SRS FR-OVR-02).",
            },
        )

    date_str = _parse_date(body.date)
    lead = _validate_lead(body.lead_hours)
    ds = get_dataset()
    district_id, district_name = _resolve(ds, body.district)

    # Recompute the current system output for this exact point.
    result = _run(
        ds,
        district_id=district_id,
        district_name=district_name,
        valid_date=date_str,
        lead_hours=lead,
        simulate_failure_source=None,
    )
    assert result.risk is not None and result.blend is not None
    assert result.confidence is not None and result.regime is not None

    original_mm = result.blend.final_rainfall_mm
    original_output = {
        "risk_level": result.risk.risk_level,
        "final_rainfall_mm": (
            round(float(original_mm), 4) if original_mm is not None else None
        ),
        "confidence_score": result.confidence.score,
        "confidence_label": result.confidence.label,
        "weather_regime": result.regime.label,
        "fallback_mode": result.blend.fallback_mode,
        "algorithm_version": result.algorithm_version,
        "config_version": result.config_version,
        "ai_source_label": result.ai_source_provenance.get("source_label"),
    }

    actor = (body.reviewer_name or "").strip() or body.role

    override = OverrideDecision(
        actor=actor,
        role=body.role,
        district_id=district_id,
        valid_date=date_str,
        lead_hours=lead,
        original_risk_level=str(result.risk.risk_level),
        original_forecast_mm=(
            round(float(original_mm), 4) if original_mm is not None else None
        ),
        overridden_risk_level=body.selected_risk_level,
        reason=reason,
        original_output_json=json.dumps(original_output, default=str),
    )
    db.add(override)
    db.flush()  # assign id without committing

    audit = AuditLog(
        actor=actor,
        role=body.role,
        action="override.created",
        district_id=district_id,
        forecast_reference=f"{district_id}|{date_str}|{lead}h",
        details=json.dumps(
            {
                "override_id": int(override.id),
                "district_name": district_name,
                "valid_date": date_str,
                "lead_hours": lead,
                "original_risk_level": override.original_risk_level,
                "overridden_risk_level": override.overridden_risk_level,
                "reason": reason,
            },
            default=str,
        ),
    )
    db.add(audit)
    db.commit()
    db.refresh(override)

    record = OverrideRecord.model_validate(
        {
            **_override_dict(override),
            "district_name": district_name,
        }
    )
    return OverrideCreateResponse(
        data_mode=settings.data_mode,
        disclaimer=settings.decision_support_disclaimer,
        note=OVERRIDE_NOTE,
        record=record,
    )


@router.get(
    "/audit-logs",
    response_model=AuditLogsResponse,
    tags=["audit"],
    summary="Local review/audit timeline (newest first)",
)
def audit_logs(
    kind: Optional[Literal["override", "system", "all"]] = Query(
        default="all",
        description="Filter the timeline by entry kind.",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of entries to return (newest first).",
    ),
    db: Session = Depends(get_db),
) -> AuditLogsResponse:
    """Return the newest override and system audit entries from local SQLite."""
    override_rows = (
        db.query(OverrideDecision)
        .order_by(OverrideDecision.created_at.desc(), OverrideDecision.id.desc())
        .limit(limit)
        .all()
    )
    system_rows = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )

    entries: list[dict] = []
    if kind in ("all", "override"):
        for row in override_rows:
            item = _override_dict(row)
            item["kind"] = "override"
            entries.append(item)
    if kind in ("all", "system"):
        for row in system_rows:
            entries.append(_audit_dict(row))

    # Newest first, stable by id.
    entries.sort(key=lambda e: (e["created_at"], e["id"]), reverse=True)
    entries = entries[:limit]

    records = [AuditLogEntry.model_validate(item) for item in entries]
    return AuditLogsResponse(
        data_mode=settings.data_mode,
        disclaimer=settings.decision_support_disclaimer,
        note=OVERRIDE_NOTE,
        count=len(records),
        entries=records,
    )