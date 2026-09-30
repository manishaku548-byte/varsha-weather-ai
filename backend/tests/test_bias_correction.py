"""Phase 2 tests: bias correction uses strictly prior records (SRS FR-BC-01..06).

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from app.config import settings
from app.services import bias as bias_mod

DATE = "2025-09-15"
DISTRICT = "prayagraj"
LEAD = 24


def _compute(ds, *, source_id: str, raw: float, date: str = DATE) -> bias_mod.BiasResult:
    return bias_mod.compute_bias(
        ds.forecasts,
        ds.observations,
        district_id=DISTRICT,
        lead_hours=LEAD,
        source_id=source_id,
        as_of_date=date,
        raw_forecast_mm=raw,
    )


def _manual_mean(ds, *, source_id: str, date: str = DATE) -> float:
    """Independent re-implementation: mean(observed - forecast) over prior ok rows."""
    fc = ds.forecasts[
        (ds.forecasts["district_id"].astype(str) == DISTRICT)
        & (pd.to_numeric(ds.forecasts["lead_hours"], errors="coerce") == LEAD)
        & (ds.forecasts["source_id"].astype(str) == source_id)
    ].copy()
    fc["_d"] = pd.to_datetime(fc["valid_date"], errors="coerce")
    fc = fc[fc["_d"] < pd.to_datetime(date)]

    obs = ds.observations[
        (ds.observations["district_id"].astype(str) == DISTRICT)
        & (pd.to_numeric(ds.observations["lead_hours"], errors="coerce") == LEAD)
    ][["valid_date", "observed_rain_mm"]]

    merged = fc.merge(obs, on="valid_date", how="inner")
    f = pd.to_numeric(merged["forecast_rain_mm"], errors="coerce")
    o = pd.to_numeric(merged["observed_rain_mm"], errors="coerce")
    usable = (
        (merged["status"].astype(str) == "ok")
        & f.notna()
        & o.notna()
        & (f >= 0)
        & (f <= settings.max_plausible_rain_mm)
        & (o >= 0)
        & (o <= settings.max_plausible_rain_mm)
    )
    return float((o[usable] - f[usable]).mean())


def test_prior_history_is_strictly_earlier_than_selected_date(dataset):
    history = bias_mod.prior_history(
        dataset.forecasts,
        dataset.observations,
        district_id=DISTRICT,
        lead_hours=LEAD,
        source_id="nwp_model_a",
        as_of_date=DATE,
    )
    assert history.count > 0
    assert (history.frame["valid_date"] < pd.Timestamp(DATE)).all()
    assert (history.frame["valid_date"] >= pd.Timestamp("2025-06-01")).all()


def test_bias_ignores_selected_date_and_future_observations(dataset):
    """Perturbing observations at/after the selected date must not move the bias."""
    baseline = _compute(dataset, source_id="nwp_model_a", raw=25.0)

    obs = dataset.observations.copy()
    mask = pd.to_datetime(obs["valid_date"]) >= pd.Timestamp(DATE)
    obs.loc[mask, "observed_rain_mm"] = 999.0
    polluted = dataclasses.replace(dataset, observations=obs)
    after = _compute(polluted, source_id="nwp_model_a", raw=25.0)

    assert baseline.bias_available is True
    assert baseline.bias_mm == after.bias_mm
    assert baseline.historical_record_count == after.historical_record_count


def test_bias_matches_manual_mean_of_residuals(dataset):
    result = _compute(dataset, source_id="nwp_model_a", raw=25.0)
    manual = _manual_mean(dataset, source_id="nwp_model_a")
    assert result.bias_available is True
    assert result.bias_mm == pytest.approx(manual, rel=1e-12, abs=1e-12)
    assert result.historical_record_count > settings.min_bias_history_records


def test_bias_correction_arithmetic(dataset):
    result = _compute(dataset, source_id="nwp_model_a", raw=25.0)
    assert result.corrected_forecast_mm == pytest.approx(
        max(0.0, 25.0 + result.bias_mm), abs=1e-12
    )


def test_corrected_value_never_negative(dataset):
    for source_id in ("nwp_model_a", "ensemble_mean", "ai_local_v1"):
        result = _compute(dataset, source_id=source_id, raw=0.0)
        if result.bias_available:
            assert result.corrected_forecast_mm >= 0.0
            assert result.corrected_forecast_mm == pytest.approx(
                max(0.0, 0.0 + result.bias_mm), abs=1e-12
            )


def test_insufficient_prior_history_keeps_raw_value(dataset):
    first_date = str(pd.to_datetime(dataset.forecasts["valid_date"]).min().date())
    result = _compute(dataset, source_id="nwp_model_a", raw=12.0, date=first_date)
    assert result.bias_available is False
    assert result.reason == "Insufficient prior history"
    assert result.bias_mm is None
    assert result.corrected_forecast_mm == 12.0
    assert result.historical_record_count < settings.min_bias_history_records


def test_bias_history_excludes_bad_records(dataset):
    """Only status=='ok', plausible rows enter the history."""
    history = bias_mod.prior_history(
        dataset.forecasts,
        dataset.observations,
        district_id=DISTRICT,
        lead_hours=LEAD,
        source_id="ai_local_v1",
        as_of_date="2025-09-10",  # inside the AI anomalous burst window
    )
    assert history.count > 0
    assert history.mae() is not None

    # The same window filtered with the raw dataframe must contain non-ok rows,
    # proving the history filter actually removed them.
    raw_rows = dataset.forecasts[
        (dataset.forecasts["district_id"].astype(str) == DISTRICT)
        & (pd.to_numeric(dataset.forecasts["lead_hours"], errors="coerce") == LEAD)
        & (dataset.forecasts["source_id"].astype(str) == "ai_local_v1")
        & (pd.to_datetime(dataset.forecasts["valid_date"]) < pd.Timestamp("2025-09-10"))
    ]
    assert (raw_rows["status"].astype(str) != "ok").any()


def test_missing_raw_forecast_reports_unavailable(dataset):
    result = _compute(dataset, source_id="nwp_model_a", raw=float("nan"))
    assert result.bias_available is False
    assert result.bias_mm is None
    assert "No usable raw forecast" in result.reason
