"""Backtest report export: deterministic CSV + JSON metadata files (Phase 3).

Every backtest run writes two files into ``data/reports/``:

* ``backtest_<district_slug>_<lead>h_<start>_<end>.csv``   — per-date rows
* ``backtest_<district_slug>_<lead>h_<start>_<end>.json``  — summary metadata

Filenames are deterministic (same request parameters → same file). Paths are
built from a sanitized slug and re-checked against the reports directory, so
directory traversal is impossible.

Files keep **full engine precision**; rounding happens only when a payload is
served as a human-facing API response.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..config import Settings, settings as default_settings
from .backtest import BacktestResult, BacktestRow
from .metrics import METHOD_DISPLAY, METHOD_KEYS

#: Columns required by the Phase 3 CSV contract, in order.
CSV_COLUMNS: list[str] = [
    "date",
    "district",
    "lead_hours",
    "actual_rain_mm",
    "nwp_prediction_mm",
    "ensemble_prediction_mm",
    "ai_prediction_mm",
    "equal_weight_prediction_mm",
    "varsha_prediction_mm",
    "regime",
    "nwp_weight",
    "ensemble_weight",
    "ai_weight",
    "confidence_score",
    "confidence_label",
    "risk_level",
    "fallback_mode",
    "included_in_evaluation",
    "skip_reason",
    "nwp_source_health",
    "ensemble_source_health",
    "ai_source_health",
    "ai_source_label",
    "prior_history_days",
    "data_mode",
    "disclaimer",
]

_FILENAME_RE = re.compile(
    r"^backtest_[a-z0-9_]+_[0-9]{1,3}h_"
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}-[0-9]{2}-[0-9]{2}\.(csv|json)$"
)


class ReportPathError(ValueError):
    """Raised when a report filename would escape the reports directory."""


def slugify_district(district_id: str) -> str:
    """Filesystem-safe slug for a district id (``kanpur-nagar`` -> ``kanpur_nagar``)."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(district_id).lower()).strip("_")
    return slug or "district"


def report_stem(district_id: str, lead_hours: int, start_date: str, end_date: str) -> str:
    """Deterministic report filename stem shared by the CSV and JSON files."""
    stem = (
        f"backtest_{slugify_district(district_id)}_{int(lead_hours)}h_"
        f"{start_date}_{end_date}"
    )
    if not _FILENAME_RE.fullmatch(stem + ".csv"):
        raise ReportPathError(
            f"Refusing unsafe report filename '{stem}' (directory traversal guard)."
        )
    return stem


def report_paths(
    district_id: str,
    lead_hours: int,
    start_date: str,
    end_date: str,
    cfg: Settings | None = None,
) -> tuple[Path, Path]:
    """Return ``(csv_path, json_path)`` inside the configured reports directory."""
    s = cfg or default_settings
    stem = report_stem(district_id, lead_hours, start_date, end_date)

    reports_dir = Path(s.reports_dir).expanduser()
    reports_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir = reports_dir.resolve()

    csv_path = (resolved_dir / f"{stem}.csv").resolve()
    json_path = (resolved_dir / f"{stem}.json").resolve()
    for path in (csv_path, json_path):
        if path.parent != resolved_dir or path.name != f"{stem}{path.suffix}":
            raise ReportPathError(
                f"Refusing to write outside the reports directory: {path}"
            )
    return csv_path, json_path


# --------------------------------------------------------------------------------------
# Shared payload fragments (used by the API responses and the JSON metadata file)
# --------------------------------------------------------------------------------------
def request_echo(result: BacktestResult) -> dict:
    return {
        "district": result.district_name,
        "district_id": result.district_id,
        "lead_hours": result.lead_hours,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "minimum_history_days": result.minimum_history_days,
        "heavy_rain_threshold_mm": result.configured_threshold_mm,
    }


def data_range(result: BacktestResult) -> dict:
    return {
        "dataset_first_valid_date": result.dataset_first_date,
        "dataset_last_valid_date": result.dataset_last_date,
        "requested_start_date": result.start_date,
        "requested_end_date": result.end_date,
        "dates_in_dataset_range": result.dates_in_dataset_range,
    }


def evaluation_summary(result: BacktestResult) -> dict:
    return {
        "total_requested_dates": result.total_requested_dates,
        "evaluated_dates": result.evaluated_dates,
        "skipped_dates": result.skipped_dates,
        "skipped_reason_counts": dict(result.skipped_reason_counts),
        "sufficient_sample_warning": result.sufficient_sample_warning,
    }


def event_threshold(result: BacktestResult) -> dict:
    return {
        "configured_threshold_mm": result.configured_threshold_mm,
        "effective_threshold_mm": result.event_threshold_mm,
        "lead_hours": result.lead_hours,
        "scaling_applied": result.threshold_scaling_applied,
        "basis": (
            "Event threshold = configured 24h threshold x (lead_hours / 24) when "
            "scale_thresholds_by_lead is enabled; the same effective threshold "
            "defines observed and predicted events."
            if result.threshold_scaling_applied
            else "Event threshold = configured threshold (lead scaling disabled); "
            "the same effective threshold defines observed and predicted events."
        ),
    }


def methods_payload(result: BacktestResult) -> dict:
    """Per-method metrics at raw precision (regression + event)."""
    payload: dict[str, dict] = {}
    for method in METHOD_KEYS:
        payload[method] = {
            "display_name": METHOD_DISPLAY[method],
            "regression_metrics": asdict(result.regression[method]),
            "event_metrics": asdict(result.events[method]),
        }
    return payload


def metrics_table(result: BacktestResult) -> list[dict]:
    """Flat metrics table for quick reading (raw precision)."""
    table: list[dict] = []
    for method in METHOD_KEYS:
        reg = result.regression[method]
        evt = result.events[method]
        table.append(
            {
                "method": method,
                "display_name": METHOD_DISPLAY[method],
                "sample_count": reg.sample_count,
                "mae_mm": reg.mae_mm,
                "rmse_mm": reg.rmse_mm,
                "mean_bias_error_mm": reg.mean_bias_error_mm,
                "median_absolute_error_mm": reg.median_absolute_error_mm,
                "max_absolute_error_mm": reg.max_absolute_error_mm,
                "precision": evt.precision,
                "recall": evt.recall,
                "f1_score": evt.f1_score,
                "false_alarm_rate": evt.false_alarm_rate,
                "missed_event_rate": evt.missed_event_rate,
                "event_count": evt.event_count,
            }
        )
    return table


def build_report_payload(result: BacktestResult, generated_at: str, csv_name: str, json_name: str) -> dict:
    """Raw-precision metadata payload written to (and served from) the JSON file."""
    return {
        "report_type": "backtest",
        "generated_at": generated_at,
        "algorithm_version": result.algorithm_version,
        "config_version": result.config_version,
        "data_mode": result.data_mode,
        "disclaimer": result.disclaimer,
        "request": request_echo(result),
        "data_range": data_range(result),
        "evaluation_summary": evaluation_summary(result),
        "event_threshold": event_threshold(result),
        "methods": methods_payload(result),
        "metrics_table": metrics_table(result),
        "comparison_summary": result.comparison,
        "ai_source_provenance": result.ai_source_provenance,
        "row_counts": {
            "total": result.total_requested_dates,
            "evaluated": result.evaluated_dates,
            "skipped": result.skipped_dates,
        },
        "files": {"csv": csv_name, "json": json_name},
        "limitations": list(result.limitations),
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------------------
# CSV export
# --------------------------------------------------------------------------------------
def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "" if value != value else str(value)  # NaN -> empty
    return str(value)


def row_to_record(row: BacktestRow, data_mode: str, disclaimer: str) -> dict[str, str]:
    """Map one walk-forward row onto the required CSV columns."""
    weights = row.weights or {}
    health = row.source_health or {}
    pred = row.predictions or {}
    return {
        "date": row.date,
        "district": row.district_name,
        "lead_hours": str(row.lead_hours),
        "actual_rain_mm": _cell(row.actual_mm),
        "nwp_prediction_mm": _cell(pred.get("nwp")),
        "ensemble_prediction_mm": _cell(pred.get("ensemble")),
        "ai_prediction_mm": _cell(pred.get("ai_local")),
        "equal_weight_prediction_mm": _cell(pred.get("equal_weight")),
        "varsha_prediction_mm": _cell(pred.get("varsha_dynamic_blend")),
        "regime": _cell(row.regime),
        "nwp_weight": _cell(weights.get("nwp")),
        "ensemble_weight": _cell(weights.get("ensemble")),
        "ai_weight": _cell(weights.get("ai_local")),
        "confidence_score": _cell(row.confidence_score),
        "confidence_label": _cell(row.confidence_label),
        "risk_level": _cell(row.risk_level),
        "fallback_mode": _cell(row.fallback_mode),
        "included_in_evaluation": _cell(row.included_in_evaluation),
        "skip_reason": _cell(row.skip_reason),
        "nwp_source_health": _cell(health.get("nwp_model_a")),
        "ensemble_source_health": _cell(health.get("ensemble_mean")),
        "ai_source_health": _cell(health.get("ai_local_v1")),
        "ai_source_label": _cell(row.ai_source_label),
        "prior_history_days": _cell(row.prior_history_days),
        "data_mode": data_mode,
        "disclaimer": disclaimer,
    }


def write_csv(result: BacktestResult, csv_path: Path) -> Path:
    """Write the per-date CSV (all requested dates, included and skipped)."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in result.rows:
            writer.writerow(row_to_record(row, result.data_mode, result.disclaimer))
    return csv_path


def write_report_json(payload: dict, json_path: Path) -> Path:
    """Write the raw-precision JSON metadata file."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    return json_path


def load_report_json(json_path: Path) -> dict | None:
    """Read a stored report summary; None when missing or unreadable."""
    try:
        with json_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def mark_legacy_ai_provenance(payload: dict) -> dict:
    """Mark reports generated before the Phase 4 ML integration (rule H).

    Such reports were built with the precomputed synthetic AI input, so they
    are explicitly labelled ``fallback_precomputed_ai_source`` instead of
    leaving the AI-source provenance unknown.
    """
    if "ai_source_provenance" in payload:
        return payload
    evaluated = (payload.get("row_counts") or {}).get("evaluated")
    return {
        **payload,
        "ai_source_provenance": {
            "source_label": "fallback_precomputed_ai_source",
            "model_inference_available": False,
            "labels_used": {"fallback_precomputed_ai_source": evaluated},
            "rows_using_trained_model": 0,
            "rows_using_fallback_source": evaluated,
            "mixed_inputs": False,
            "model_versions": [],
            "note": (
                "Legacy report generated before the Phase 4 ML integration: its "
                "AI-source input was the precomputed synthetic ai_rain_mm "
                "fallback source (no trained model existed when this report "
                "was written)."
            ),
        },
    }


def run_and_write(
    result: BacktestResult, cfg: Settings | None = None
) -> tuple[Path, Path, dict]:
    """Write both report files for a completed run; returns paths + raw payload."""
    csv_path, json_path = report_paths(
        result.district_id,
        result.lead_hours,
        result.start_date,
        result.end_date,
        cfg=cfg,
    )
    write_csv(result, csv_path)
    payload = build_report_payload(result, now_iso(), csv_path.name, json_path.name)
    write_report_json(payload, json_path)
    return csv_path, json_path, payload
