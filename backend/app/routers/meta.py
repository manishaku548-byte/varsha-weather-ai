"""Phase 1 meta endpoints: /health, /districts, /data/summary.

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..database import database_status
from ..schemas import (
    DataSummaryResponse,
    District,
    DistrictListResponse,
    HealthResponse,
)
from ..services.dataset import (
    get_dataset,
    DatasetUnavailableError,
)
from ..services.summary import build_summary

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["meta"],
    summary="Service health and dataset availability",
)
def health() -> HealthResponse:
    """Liveness/status probe. Works even when the dataset is unavailable."""
    records: dict[str, int] = {}
    dataset_loaded = True
    try:
        ds = get_dataset()
        records = {
            "districts": int(len(ds.districts)),
            "forecast_records": int(len(ds.forecasts)),
            "observation_records": int(len(ds.observations)),
        }
    except DatasetUnavailableError:
        dataset_loaded = False

    return HealthResponse(
        status="ok" if dataset_loaded else "degraded",
        service=settings.app_name,
        version=settings.version,
        phase=settings.phase,
        problem_statement_id=settings.problem_statement_id,
        data_mode=settings.data_mode,
        data_label=settings.synthetic_data_label,
        disclaimer=settings.decision_support_disclaimer,
        dataset_loaded=dataset_loaded,
        database_status=database_status(),  # type: ignore[arg-type]
        records=records,
    )


@router.get(
    "/districts",
    response_model=DistrictListResponse,
    tags=["meta"],
    summary="Configured MVP districts",
)
def districts() -> DistrictListResponse:
    """List the five configured Uttar Pradesh districts with centroids."""
    ds = get_dataset()  # raises DatasetUnavailableError -> 503 handler
    records = [
        District(
            district_id=str(row["district_id"]),
            district_name=str(row["district_name"]),
            state=str(row["state"]),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
        )
        for row in ds.districts.to_dict("records")
    ]
    return DistrictListResponse(
        data_mode=settings.data_mode,
        data_label=settings.synthetic_data_label,
        disclaimer=settings.decision_support_disclaimer,
        count=len(records),
        districts=records,
    )


@router.get(
    "/data/summary",
    response_model=DataSummaryResponse,
    tags=["meta"],
    summary="Dataset summary, validation report and source health",
)
def data_summary(
    district: str | None = Query(
        default=None,
        description="Optional district id or name filter, e.g. 'Prayagraj'.",
        examples=["Prayagraj"],
    ),
) -> DataSummaryResponse:
    """Descriptive summary of the loaded replay dataset (never a forecast)."""
    ds = get_dataset()
    try:
        return build_summary(ds, district)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from None
