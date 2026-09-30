"""Phase 3 backtest endpoints:

* ``GET /backtest``            — chronological walk-forward evaluation + metrics
* ``GET /backtest/report``     — stored/generated report summary (json) or CSV download

Every number is computed by the walk-forward engine from the stored synthetic
dataset; nothing is hardcoded or tuned. Files are written to ``data/reports/``
with deterministic, traversal-safe names. Display rounding (4 decimals) is
applied only in this layer — report files keep full engine precision.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..config import settings
from ..schemas_backtest import (
    BacktestReportResponse,
    BacktestResponse,
)
from ..services.backtest import (
    SKIP_REASON_NOTES,
    BacktestResult,
    BacktestRow,
    run_backtest,
)
from ..services.dataset import get_dataset
from ..services.reporting import (
    data_range,
    evaluation_summary,
    event_threshold,
    load_report_json,
    mark_legacy_ai_provenance,
    methods_payload,
    report_paths,
    request_echo,
    run_and_write,
)
from .forecast import _resolve, _validate_lead

router = APIRouter()


# --------------------------------------------------------------------------------------
# Display helpers (report files keep raw precision; API responses round here)
# --------------------------------------------------------------------------------------
def _round_tree(obj, ndigits: int = 4):
    """Recursively round floats for human-facing display; ints/bools untouched."""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {key: _round_tree(value, ndigits) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_round_tree(value, ndigits) for value in obj]
    return obj


def _daily_row_dict(row: BacktestRow) -> dict:
    weights = row.weights or {}
    health = row.source_health or {}
    pred = row.predictions or {}
    return {
        "date": row.date,
        "district": row.district_name,
        "district_id": row.district_id,
        "lead_hours": row.lead_hours,
        "actual_rain_mm": row.actual_mm,
        "nwp_prediction_mm": pred.get("nwp"),
        "ensemble_prediction_mm": pred.get("ensemble"),
        "ai_prediction_mm": pred.get("ai_local"),
        "equal_weight_prediction_mm": pred.get("equal_weight"),
        "varsha_prediction_mm": pred.get("varsha_dynamic_blend"),
        "prior_history_days": row.prior_history_days,
        "regime": row.regime,
        "nwp_weight": weights.get("nwp"),
        "ensemble_weight": weights.get("ensemble"),
        "ai_weight": weights.get("ai_local"),
        "confidence_score": row.confidence_score,
        "confidence_label": row.confidence_label,
        "risk_level": row.risk_level,
        "fallback_mode": row.fallback_mode,
        "nwp_source_health": health.get("nwp_model_a"),
        "ensemble_source_health": health.get("ensemble_mean"),
        "ai_source_health": health.get("ai_local_v1"),
        "ai_source_label": row.ai_source_label,
        "ai_model_version": row.ai_model_version,
        "included_in_evaluation": row.included_in_evaluation,
        "skip_reason": row.skip_reason,
        "skip_reason_note": SKIP_REASON_NOTES.get(row.skip_reason or ""),
    }


def _build_response(
    result: BacktestResult, *, include_daily_rows: bool, csv_name: str, json_name: str
) -> BacktestResponse:
    payload = {
        "data_mode": result.data_mode,
        "disclaimer": result.disclaimer,
        "algorithm_version": result.algorithm_version,
        "config_version": result.config_version,
        "request": {**request_echo(result), "include_daily_rows": include_daily_rows},
        "data_range": data_range(result),
        "evaluation_summary": evaluation_summary(result),
        "event_threshold": event_threshold(result),
        "methods": methods_payload(result),
        "comparison_summary": result.comparison,
        "limitations": list(result.limitations),
        "report_files": {"csv": csv_name, "json": json_name},
        "ai_source_provenance": result.ai_source_provenance,
    }
    if include_daily_rows:
        payload["daily_rows"] = [_daily_row_dict(row) for row in result.rows]
    return BacktestResponse.model_validate(_round_tree(payload))


def _build_report_response(payload: dict, source: str) -> BacktestReportResponse:
    # Legacy pre-Phase-4 reports are explicitly marked with their AI-source input.
    data = {**mark_legacy_ai_provenance(payload), "report_source": source}
    return BacktestReportResponse.model_validate(_round_tree(data))


# --------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------
def _validate_range(start: date, end: date) -> int:
    """Validate the inclusive range; returns the number of requested dates."""
    if start > end:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_date_range",
                "message": "start_date must be on or before end_date.",
            },
        )
    span = (end - start).days + 1
    if span > settings.max_backtest_dates:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "backtest_range_too_large",
                "message": (
                    f"Requested range spans {span} dates; the prototype allows at "
                    f"most {settings.max_backtest_dates} dates per backtest run."
                ),
                "max_dates": settings.max_backtest_dates,
            },
        )
    return span


def _validate_minimum_history(value: Optional[int]) -> int:
    if value is None:
        return int(settings.default_minimum_history_days)
    if value < 0:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_minimum_history_days",
                "message": "minimum_history_days must be >= 0.",
            },
        )
    return int(value)


def _expected_threshold(heavy_rain_threshold_mm: Optional[float]) -> float:
    """Effective configured (24h-equivalent) threshold used to match stored reports."""
    if heavy_rain_threshold_mm is not None:
        return float(heavy_rain_threshold_mm)
    return float(settings.base_thresholds_24h_mm["heavy"])


def _stored_params_match(
    payload: dict | None,
    *,
    minimum_history_days: int,
    heavy_rain_threshold_mm: Optional[float],
) -> bool:
    """A stored report only counts when it was generated with the same parameters."""
    if not payload:
        return False
    request = payload.get("request")
    if not isinstance(request, dict):
        return False
    if int(request.get("minimum_history_days", -1)) != int(minimum_history_days):
        return False
    stored_threshold = request.get("heavy_rain_threshold_mm")
    if stored_threshold is None:
        return False
    return abs(float(stored_threshold) - _expected_threshold(heavy_rain_threshold_mm)) < 1e-9


def _prepare(
    district: str,
    lead_hours: int,
    start_date: date,
    end_date: date,
    minimum_history_days: Optional[int],
) -> tuple[str, str, int, int, int]:
    """Shared validation; returns (district_id, name, lead, min_history, total_dates)."""
    lead = _validate_lead(lead_hours)
    total = _validate_range(start_date, end_date)
    min_hist = _validate_minimum_history(minimum_history_days)
    ds = get_dataset()
    district_id, name = _resolve(ds, district)
    return district_id, name, lead, min_hist, total


def _run(
    ds,
    *,
    district_id: str,
    district_name: str,
    lead_hours: int,
    start_date: date,
    end_date: date,
    minimum_history_days: int,
    heavy_rain_threshold_mm: Optional[float],
) -> BacktestResult:
    return run_backtest(
        ds,
        district_id=district_id,
        district_name=district_name,
        lead_hours=lead_hours,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        minimum_history_days=minimum_history_days,
        heavy_rain_threshold_mm=heavy_rain_threshold_mm,
    )


def _generate(
    *,
    district_id: str,
    name: str,
    lead: int,
    start_date: date,
    end_date: date,
    min_hist: int,
    heavy_rain_threshold_mm: Optional[float],
):
    """Run the walk-forward engine and write both report files."""
    ds = get_dataset()
    result = _run(
        ds,
        district_id=district_id,
        district_name=name,
        lead_hours=lead,
        start_date=start_date,
        end_date=end_date,
        minimum_history_days=min_hist,
        heavy_rain_threshold_mm=heavy_rain_threshold_mm,
    )
    return run_and_write(result)


# --------------------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------------------
@router.get(
    "/backtest",
    response_model=BacktestResponse,
    response_model_exclude_unset=True,  # omits daily_rows entirely when not requested
    tags=["backtest"],
    summary="Chronological walk-forward backtest with regression and event metrics",
)
def backtest(
    district: str = Query(
        ..., description="District id or name.", examples=["Prayagraj"]
    ),
    lead_hours: int = Query(
        ..., description="Forecast horizon in hours — one of 6, 24 or 72.", examples=[24]
    ),
    start_date: date = Query(..., description="First date of the evaluation range (YYYY-MM-DD)."),
    end_date: date = Query(..., description="Last date of the evaluation range (inclusive)."),
    minimum_history_days: Optional[int] = Query(
        default=None,
        description=(
            "Skip dates with fewer than this many prior history days "
            f"(default {settings.default_minimum_history_days})."
        ),
    ),
    heavy_rain_threshold_mm: Optional[float] = Query(
        default=None,
        gt=0,
        description=(
            "Optional 24h-equivalent heavy-rain event threshold override "
            "(default 64.5 mm); scaled by lead_hours/24 when enabled."
        ),
    ),
    include_daily_rows: bool = Query(
        default=False,
        description="Include per-date rows in the response (always written to CSV).",
    ),
) -> BacktestResponse:
    """Walk forward day by day; each date uses only records strictly earlier than it."""
    district_id, name, lead, min_hist, _ = _prepare(
        district, lead_hours, start_date, end_date, minimum_history_days
    )
    ds = get_dataset()
    result = _run(
        ds,
        district_id=district_id,
        district_name=name,
        lead_hours=lead,
        start_date=start_date,
        end_date=end_date,
        minimum_history_days=min_hist,
        heavy_rain_threshold_mm=heavy_rain_threshold_mm,
    )
    csv_path, json_path, _payload = run_and_write(result)
    return _build_response(
        result,
        include_daily_rows=include_daily_rows,
        csv_name=csv_path.name,
        json_name=json_path.name,
    )


@router.get(
    "/backtest/report",
    response_model=BacktestReportResponse,
    tags=["backtest"],
    summary="Backtest report summary (json) or CSV file download",
)
def backtest_report(
    district: str = Query(
        ..., description="District id or name.", examples=["Prayagraj"]
    ),
    lead_hours: int = Query(
        ..., description="Forecast horizon in hours — one of 6, 24 or 72.", examples=[24]
    ),
    start_date: date = Query(..., description="First date of the evaluation range (YYYY-MM-DD)."),
    end_date: date = Query(..., description="Last date of the evaluation range (inclusive)."),
    minimum_history_days: Optional[int] = Query(
        default=None,
        description="Same history rule as /backtest (used when the report is generated).",
    ),
    heavy_rain_threshold_mm: Optional[float] = Query(
        default=None, gt=0, description="Same event-threshold override as /backtest."
    ),
    format: Literal["json", "csv"] = Query(
        default="json",
        description="json = report summary in the response; csv = file download.",
    ),
):
    """Return the matching stored report, or generate it first when missing."""
    district_id, name, lead, min_hist, _ = _prepare(
        district, lead_hours, start_date, end_date, minimum_history_days
    )
    csv_path, json_path = report_paths(
        district_id, lead, start_date.isoformat(), end_date.isoformat()
    )
    stored = load_report_json(json_path)
    params_match = _stored_params_match(
        stored,
        minimum_history_days=min_hist,
        heavy_rain_threshold_mm=heavy_rain_threshold_mm,
    )

    if format == "csv":
        if not (csv_path.exists() and params_match):
            _csv_path, _json_path, _payload = _generate(
                district_id=district_id,
                name=name,
                lead=lead,
                start_date=start_date,
                end_date=end_date,
                min_hist=min_hist,
                heavy_rain_threshold_mm=heavy_rain_threshold_mm,
            )
        if not csv_path.exists():  # pragma: no cover - writer failure guard
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "report_write_failed",
                    "message": "Report CSV could not be written.",
                },
            )
        return FileResponse(
            csv_path,
            media_type="text/csv",
            filename=csv_path.name,
            headers={
                "Content-Disposition": f'attachment; filename="{csv_path.name}"',
                # HTTP headers are latin-1 only; the full disclaimer is carried
                # inside every CSV row (disclaimer column) and in the JSON report.
                "X-Data-Mode": settings.data_mode,
            },
        )

    if params_match and stored is not None:
        return _build_report_response(stored, "stored")

    _csv_path, _json_path, fresh = _generate(
        district_id=district_id,
        name=name,
        lead=lead,
        start_date=start_date,
        end_date=end_date,
        min_hist=min_hist,
        heavy_rain_threshold_mm=heavy_rain_threshold_mm,
    )
    return _build_report_response(fresh, "generated")
