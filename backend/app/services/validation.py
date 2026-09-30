"""Data-quality validation (SRS FR-DQ-01..06, FR-SRC-04).

Two levels of findings are reported:

* ``blocking_issues`` — contract violations (missing columns, unknown districts,
  unparseable dates, wrong units/leads/statuses). These mean the dataset cannot
  be trusted structurally.
* ``quality_flags`` — record-level issues (implausible, missing or unexpected
  values). These are expected in real/simulated feeds and are handled later by
  the trust engine (poor-quality records must not get normal weight).

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

import pandas as pd

from ..config import Settings, settings as default_settings
from ..schemas import ValidationSummary

DISTRICT_REQUIRED_COLUMNS = [
    "district_id",
    "district_name",
    "state",
    "latitude",
    "longitude",
]

FORECAST_REQUIRED_COLUMNS = [
    "district_id",
    "valid_date",
    "lead_hours",
    "source_id",
    "issue_time",
    "forecast_rain_mm",
    "unit",
    "status",
    "quality_flag",
]

OBSERVATION_REQUIRED_COLUMNS = [
    "district_id",
    "valid_date",
    "lead_hours",
    "observed_rain_mm",
    "unit",
]

MAX_ISSUES_LISTED = 25


def _require_columns(
    frame: pd.DataFrame, required: list[str], frame_name: str, blocking: list[str]
) -> bool:
    missing = [c for c in required if c not in frame.columns]
    if missing:
        blocking.append(
            f"{frame_name} is missing required column(s): {', '.join(missing)}"
        )
        return False
    return True


def validate_dataset(
    districts: pd.DataFrame,
    forecasts: pd.DataFrame,
    observations: pd.DataFrame,
    cfg: Settings | None = None,
) -> ValidationSummary:
    """Validate schema, units, timestamps, districts, leads and value plausibility."""
    s = cfg or default_settings
    blocking: list[str] = []
    flags = {"implausible_value": 0, "missing_value": 0, "unexpected_value": 0}

    # --- districts ---------------------------------------------------------------
    known_districts: set[str] = set()
    if _require_columns(districts, DISTRICT_REQUIRED_COLUMNS, "districts.csv", blocking):
        known_districts = set(districts["district_id"].astype(str))

    # --- forecasts ---------------------------------------------------------------
    forecast_rows = len(forecasts)
    if _require_columns(
        forecasts, FORECAST_REQUIRED_COLUMNS, s.forecasts_file, blocking
    ):
        unknown = sorted(
            set(forecasts.loc[
                ~forecasts["district_id"].astype(str).isin(known_districts),
                "district_id",
            ].astype(str))
        )
        if unknown:
            blocking.append(
                f"{s.forecasts_file}: {len(forecasts)} rows reference unknown "
                f"district_id value(s): {', '.join(unknown)}"
            )

        valid_dates = pd.to_datetime(forecasts["valid_date"], errors="coerce")
        bad_dates = int(valid_dates.isna().sum())
        if bad_dates:
            blocking.append(
                f"{s.forecasts_file}: {bad_dates} row(s) have an unparseable valid_date"
            )

        issue_times = pd.to_datetime(forecasts["issue_time"], errors="coerce", utc=True)
        bad_issues = int(issue_times.isna().sum())
        if bad_issues:
            blocking.append(
                f"{s.forecasts_file}: {bad_issues} row(s) have an unparseable issue_time"
            )

        leads = pd.to_numeric(forecasts["lead_hours"], errors="coerce")
        bad_leads = int((~leads.isin(list(s.allowed_lead_hours))).sum())
        if bad_leads:
            blocking.append(
                f"{s.forecasts_file}: {bad_leads} row(s) have lead_hours outside "
                f"the allowed set {list(s.allowed_lead_hours)}"
            )

        bad_units = int((forecasts["unit"].astype(str) != s.forecast_unit).sum())
        if bad_units:
            blocking.append(
                f"{s.forecasts_file}: {bad_units} row(s) have a unit other than "
                f"'{s.forecast_unit}'"
            )

        statuses = forecasts["status"].astype(str)
        bad_status = int((~statuses.isin(list(s.valid_forecast_statuses))).sum())
        if bad_status:
            blocking.append(
                f"{s.forecasts_file}: {bad_status} row(s) have an unsupported status; "
                f"allowed: {', '.join(s.valid_forecast_statuses)}"
            )

        values = pd.to_numeric(forecasts["forecast_rain_mm"], errors="coerce")
        implausible = values.notna() & (
            (values < 0) | (values > s.max_plausible_rain_mm)
        )
        flags["implausible_value"] += int(implausible.sum())
        flags["missing_value"] += int(
            (values.isna() & (statuses != "unavailable")).sum()
        )
        flags["unexpected_value"] += int(
            (values.notna() & (statuses == "unavailable")).sum()
        )

    # --- observations -------------------------------------------------------------
    observation_rows = len(observations)
    if _require_columns(
        observations, OBSERVATION_REQUIRED_COLUMNS, s.observations_file, blocking
    ):
        unknown = sorted(
            set(observations.loc[
                ~observations["district_id"].astype(str).isin(known_districts),
                "district_id",
            ].astype(str))
        )
        if unknown:
            blocking.append(
                f"{s.observations_file}: rows reference unknown district_id value(s): "
                f"{', '.join(unknown)}"
            )

        valid_dates = pd.to_datetime(observations["valid_date"], errors="coerce")
        bad_dates = int(valid_dates.isna().sum())
        if bad_dates:
            blocking.append(
                f"{s.observations_file}: {bad_dates} row(s) have an unparseable valid_date"
            )

        leads = pd.to_numeric(observations["lead_hours"], errors="coerce")
        bad_leads = int((~leads.isin(list(s.allowed_lead_hours))).sum())
        if bad_leads:
            blocking.append(
                f"{s.observations_file}: {bad_leads} row(s) have lead_hours outside "
                f"the allowed set {list(s.allowed_lead_hours)}"
            )

        bad_units = int((observations["unit"].astype(str) != s.forecast_unit).sum())
        if bad_units:
            blocking.append(
                f"{s.observations_file}: {bad_units} row(s) have a unit other than "
                f"'{s.forecast_unit}'"
            )

        values = pd.to_numeric(observations["observed_rain_mm"], errors="coerce")
        flags["implausible_value"] += int(
            (values.notna() & ((values < 0) | (values > s.max_plausible_rain_mm))).sum()
        )
        flags["missing_value"] += int(values.isna().sum())

    return ValidationSummary(
        structure_ok=len(blocking) == 0,
        blocking_issues=blocking[:MAX_ISSUES_LISTED],
        quality_flags=flags,
        checked_forecast_rows=forecast_rows,
        checked_observation_rows=observation_rows,
    )
