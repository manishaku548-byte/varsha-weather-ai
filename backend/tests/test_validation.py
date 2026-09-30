"""Unit tests for the data-quality validation service."""

from __future__ import annotations

import pandas as pd

from app.services.validation import (
    DISTRICT_REQUIRED_COLUMNS,
    FORECAST_REQUIRED_COLUMNS,
    OBSERVATION_REQUIRED_COLUMNS,
    validate_dataset,
)

DISTRICTS = pd.DataFrame(
    [
        {
            "district_id": "prayagraj",
            "district_name": "Prayagraj",
            "state": "Uttar Pradesh",
            "latitude": 25.4358,
            "longitude": 81.8463,
        }
    ]
)


def forecast_row(**overrides) -> dict:
    row = {
        "district_id": "prayagraj",
        "valid_date": "2025-06-02",
        "lead_hours": 24,
        "source_id": "nwp_model_a",
        "issue_time": "2025-06-01T00:00:00Z",
        "forecast_rain_mm": 12.4,
        "unit": "mm",
        "status": "ok",
        "quality_flag": "good",
    }
    row.update(overrides)
    return row


def observation_row(**overrides) -> dict:
    row = {
        "district_id": "prayagraj",
        "valid_date": "2025-06-02",
        "lead_hours": 24,
        "observed_rain_mm": 10.0,
        "unit": "mm",
    }
    row.update(overrides)
    return row


def frames(forecasts: list[dict], observations: list[dict]):
    fc = pd.DataFrame(forecasts, columns=FORECAST_REQUIRED_COLUMNS)
    obs = pd.DataFrame(observations, columns=OBSERVATION_REQUIRED_COLUMNS)
    return fc, obs


def test_valid_dataset_passes() -> None:
    fc, obs = frames([forecast_row()], [observation_row()])
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.structure_ok is True
    assert report.blocking_issues == []
    assert report.quality_flags == {
        "implausible_value": 0,
        "missing_value": 0,
        "unexpected_value": 0,
    }
    assert report.checked_forecast_rows == 1
    assert report.checked_observation_rows == 1


def test_missing_column_is_blocking() -> None:
    fc, obs = frames([forecast_row()], [observation_row()])
    fc = fc.drop(columns=["forecast_rain_mm"])
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.structure_ok is False
    assert any("missing required column" in issue for issue in report.blocking_issues)
    assert any("forecast_rain_mm" in issue for issue in report.blocking_issues)


def test_unknown_district_is_blocking() -> None:
    fc, obs = frames([forecast_row(district_id="atlantis")], [observation_row()])
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.structure_ok is False
    assert any("unknown district_id" in issue for issue in report.blocking_issues)


def test_bad_date_is_blocking() -> None:
    fc, obs = frames([forecast_row(valid_date="not-a-date")], [observation_row()])
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.structure_ok is False
    assert any("unparseable valid_date" in issue for issue in report.blocking_issues)


def test_bad_issue_time_is_blocking() -> None:
    fc, obs = frames([forecast_row(issue_time="yesterday")], [observation_row()])
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.structure_ok is False
    assert any("unparseable issue_time" in issue for issue in report.blocking_issues)


def test_unsupported_lead_time_is_blocking() -> None:
    fc, obs = frames([forecast_row(lead_hours=12)], [observation_row()])
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.structure_ok is False
    assert any("lead_hours" in issue for issue in report.blocking_issues)


def test_wrong_unit_is_blocking() -> None:
    fc, obs = frames([forecast_row(unit="inches")], [observation_row()])
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.structure_ok is False
    assert any("unit" in issue for issue in report.blocking_issues)


def test_unsupported_status_is_blocking() -> None:
    fc, obs = frames([forecast_row(status="weird")], [observation_row()])
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.structure_ok is False
    assert any("unsupported status" in issue for issue in report.blocking_issues)


def test_negative_and_extreme_values_are_quality_flags() -> None:
    fc, obs = frames(
        [
            forecast_row(forecast_rain_mm=-4.0),
            forecast_row(forecast_rain_mm=999.0),
        ],
        [observation_row(observed_rain_mm=-1.0)],
    )
    report = validate_dataset(DISTRICTS, fc, obs)
    # record-level quality issues are flagged, not blocking
    assert report.structure_ok is True
    assert report.quality_flags["implausible_value"] == 3


def test_missing_value_when_expected_is_flagged() -> None:
    fc, obs = frames(
        [forecast_row(forecast_rain_mm=float("nan"), status="ok")],
        [observation_row()],
    )
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.quality_flags["missing_value"] == 1


def test_unavailable_row_without_value_is_clean() -> None:
    fc, obs = frames(
        [forecast_row(forecast_rain_mm=float("nan"), status="unavailable")],
        [observation_row()],
    )
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.quality_flags["missing_value"] == 0


def test_unavailable_row_with_value_is_flagged() -> None:
    fc, obs = frames(
        [forecast_row(forecast_rain_mm=12.0, status="unavailable")],
        [observation_row()],
    )
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.quality_flags["unexpected_value"] == 1


def test_missing_observation_value_is_flagged() -> None:
    fc, obs = frames(
        [forecast_row()],
        [observation_row(observed_rain_mm=float("nan"))],
    )
    report = validate_dataset(DISTRICTS, fc, obs)
    assert report.quality_flags["missing_value"] == 1


def test_district_frame_missing_columns_is_blocking() -> None:
    broken = pd.DataFrame({"district_id": ["prayagraj"]})
    fc, obs = frames([forecast_row()], [observation_row()])
    report = validate_dataset(broken, fc, obs)
    assert report.structure_ok is False
    assert any(
        "districts.csv is missing required column" in issue
        for issue in report.blocking_issues
    )
    # required column lists stay in sync with the contracts
    assert "latitude" in DISTRICT_REQUIRED_COLUMNS
    assert "observed_rain_mm" in OBSERVATION_REQUIRED_COLUMNS
