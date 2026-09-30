"""Phase 4 model endpoints — controlled training, report and status (G).

* ``POST /model/train`` — the ONLY way to train (never at startup): chronological
  split, both candidates, validation-MAE selection, single held-out test
  evaluation, artifact persistence.
* ``GET /model/report`` — the saved model report (feature schema, splits,
  candidate results, selection rationale, held-out test metrics, provenance,
  fallback status, disclaimer, limitations).
* ``GET /model/status`` — artifact existence, trained horizons, inference
  readiness, last training time, data mode and fallback state.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..schemas_model import (
    ModelReportResponse,
    ModelStatusResponse,
    ModelTrainRequest,
)
from ..services.model_store import latest_trained_lead, load_artifact, model_status, report_path
from ..services.ml_training import train_local_correction_model
from ..services.reporting import load_report_json
from .backtest import _round_tree
from .forecast import _validate_lead

router = APIRouter()


def _load_report_payload(lead_hours: int) -> dict:
    path = report_path(lead_hours, settings)
    payload = load_report_json(path)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "model_report_unreadable",
                "message": (
                    f"No readable model report for {lead_hours}h lead "
                    f"({path.name}). Train with POST /model/train."
                ),
            },
        )
    return payload


@router.post(
    "/model/train",
    response_model=ModelReportResponse,
    tags=["model"],
    summary="Train the local rainfall-correction model (controlled, on demand)",
)
def train_model(body: ModelTrainRequest) -> ModelReportResponse:
    """Train, select (validation MAE only), evaluate once on the held-out test
    split and persist the local correction model for one lead horizon.

    Never runs automatically — only through this endpoint (or the
    ``python -m app.train_model`` CLI). Returns HTTP 200 with
    ``status='skipped_insufficient_data'`` and a clear warning when the
    dataset cannot meet the split/sample requirements (the deterministic
    fallback source stays active).
    """
    ds = _dataset()
    try:
        report = train_local_correction_model(
            ds,
            lead_hours=body.lead_hours,
            minimum_samples=body.minimum_samples,
            force_retrain=body.force_retrain,
            cfg=settings,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_model_parameters",
                "message": str(exc),
            },
        ) from None
    return ModelReportResponse.model_validate(_round_tree(report))


@router.get(
    "/model/report",
    response_model=ModelReportResponse,
    tags=["model"],
    summary="Latest saved model report (splits, metrics, provenance)",
)
def model_report(
    lead_hours: Optional[int] = Query(
        default=None,
        description="Lead horizon (6, 24 or 72). Defaults to the most recently "
        "trained horizon.",
        examples=[24],
    ),
) -> ModelReportResponse:
    """Return the saved report for one lead horizon (404 when never trained)."""
    if lead_hours is not None:
        lead = _validate_lead(lead_hours)
        if not report_path(lead, settings).is_file():
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "model_not_trained",
                    "message": (
                        f"No model report for {lead}h lead. Train with "
                        "POST /model/train."
                    ),
                    "lead_hours": lead,
                },
            )
    else:
        lead = latest_trained_lead(settings)
        if lead is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "model_not_trained",
                    "message": (
                        "No model report exists yet. Train with POST /model/train."
                    ),
                },
            )
    payload = _load_report_payload(lead)
    # Surface load-time integrity problems explicitly (never serve a stale pairing).
    loaded, reason = load_artifact(lead, settings)
    if loaded is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "model_artifact_invalid",
                "message": reason or "Artifact failed validation.",
                "lead_hours": lead,
            },
        )
    return ModelReportResponse.model_validate(_round_tree(payload))


@router.get(
    "/model/status",
    response_model=ModelStatusResponse,
    tags=["model"],
    summary="Model artifact existence, readiness and fallback state",
)
def model_status_endpoint() -> ModelStatusResponse:
    """Always available — reports honestly whether inference would use the
    trained model or the disclosed precomputed fallback."""
    return ModelStatusResponse.model_validate(_round_tree(model_status(settings)))


def _dataset():
    from ..services.dataset import get_dataset

    return get_dataset()
