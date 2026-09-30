"""Phase 3 walk-forward backtest tests.

Covers chronological integrity, skip reasons, metric null-safety, dataset
immutability, API contract, event-threshold scaling, validation errors and
honest best-method selection straight from computed API values.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.config import settings
from app.services.backtest import (
    SKIP_INSUFFICIENT_HISTORY,
    SKIP_INVALID_DATA,
    SKIP_MISSING_FORECAST,
    SKIP_MISSING_OBSERVATION,
    SKIP_NO_VALID_SOURCE,
    run_backtest,
)
from app.services.dataset import Dataset
from app.services.forecast_engine import run_forecast
from app.services.metrics import (
    INSUFFICIENT_SAMPLE_NOTE,
    METHOD_KEYS,
)

PRAYAGRAJ = dict(district_id="prayagraj", district_name="Prayagraj")


def _clone(ds: Dataset) -> Dataset:
    return Dataset(
        data_dir=ds.data_dir,
        adapter_name=ds.adapter_name,
        data_mode=ds.data_mode,
        provider_description=ds.provider_description,
        districts=ds.districts.copy(deep=True),
        forecasts=ds.forecasts.copy(deep=True),
        observations=ds.observations.copy(deep=True),
        validation=ds.validation,
    )


def _obs_mask(frame: pd.DataFrame, date: str, lead: int = 24) -> pd.Series:
    return (
        (frame["district_id"].astype(str) == "prayagraj")
        & (pd.to_numeric(frame["lead_hours"], errors="coerce") == lead)
        & (pd.to_datetime(frame["valid_date"], errors="coerce") == pd.Timestamp(date))
    )


def _row_for(ds: Dataset, date: str, lead: int = 24, **kwargs):
    result = run_backtest(
        ds,
        **PRAYAGRAJ,
        lead_hours=lead,
        start_date=date,
        end_date=date,
        **kwargs,
    )
    assert result.total_requested_dates == 1
    return result.rows[0]


# --------------------------------------------------------------------------------------
# G1. Chronological integrity — no leakage from same-day or future observations
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("eval_date", ["2025-07-15", "2025-08-10"])
def test_future_observations_do_not_change_prediction(dataset, eval_date):
    base = _row_for(dataset, eval_date)
    assert base.included_in_evaluation, "baseline row must be evaluated"
    assert base.actual_mm is not None
    assert base.actual_mm != 123.4  # ensure the perturb value is distinguishable

    # Perturb every observation on or after the evaluation date.
    perturbed_ds = _clone(dataset)
    obs = perturbed_ds.observations
    mask = (
        (obs["district_id"].astype(str) == "prayagraj")
        & (pd.to_numeric(obs["lead_hours"], errors="coerce") == 24)
        & (pd.to_datetime(obs["valid_date"], errors="coerce") >= pd.Timestamp(eval_date))
    )
    assert mask.sum() >= 1
    obs.loc[mask, "observed_rain_mm"] = 123.4
    obs.loc[mask, "observed_temp_c"] = 5.0
    obs.loc[mask, "observed_humidity_pct"] = 10.0
    # Prove the perturbation actually applied to the evaluated date itself...
    same_day = obs[
        (obs["district_id"].astype(str) == "prayagraj")
        & (pd.to_numeric(obs["lead_hours"], errors="coerce") == 24)
        & (pd.to_datetime(obs["valid_date"], errors="coerce") == pd.Timestamp(eval_date))
    ]
    assert float(same_day["observed_rain_mm"].iloc[0]) == 123.4

    perturbed = _row_for(perturbed_ds, eval_date)
    assert perturbed.included_in_evaluation

    # ...yet every prediction input for that date is unchanged (no leakage).
    assert perturbed.predictions == base.predictions
    assert perturbed.weights == base.weights
    assert perturbed.confidence_score == base.confidence_score
    assert perturbed.confidence_label == base.confidence_label
    assert perturbed.regime == base.regime
    assert perturbed.risk_level == base.risk_level
    assert perturbed.fallback_mode == base.fallback_mode
    assert perturbed.source_health == base.source_health
    # The observation of the evaluated date is only the verification truth.
    assert perturbed.actual_mm == pytest.approx(123.4)


def test_backtest_does_not_mutate_stored_forecast_data(dataset):
    before = dataset.forecasts.copy(deep=True)
    run_backtest(
        dataset, **PRAYAGRAJ, lead_hours=24, start_date="2025-07-01", end_date="2025-07-05"
    )
    pd.testing.assert_frame_equal(before, dataset.forecasts)


# --------------------------------------------------------------------------------------
# Method predictions cross-checked against the Phase 2 engine
# --------------------------------------------------------------------------------------
def test_method_predictions_match_phase2_engine(dataset):
    date = "2025-07-15"
    row = _row_for(dataset, date)
    engine = run_forecast(dataset, **PRAYAGRAJ, valid_date=date, lead_hours=24)

    usable = [
        sf.corrected_forecast_mm
        for sf in engine.sources
        if sf.value_usable and sf.corrected_forecast_mm is not None
    ]
    nwp = next(sf for sf in engine.sources if sf.source_id == "nwp_model_a")

    assert row.predictions["equal_weight"] == pytest.approx(sum(usable) / len(usable))
    assert row.predictions["varsha_dynamic_blend"] == pytest.approx(
        engine.blend.final_rainfall_mm
    )
    assert row.predictions["nwp"] == (
        nwp.corrected_forecast_mm if nwp.value_usable else None
    )
    # actual = observation of that date (evaluation truth only)
    obs = dataset.observations[_obs_mask(dataset.observations, date)]
    assert row.actual_mm == pytest.approx(float(obs["observed_rain_mm"].iloc[0]))


# --------------------------------------------------------------------------------------
# G5. Skip reasons
# --------------------------------------------------------------------------------------
def test_skip_missing_observation(dataset):
    ds2 = _clone(dataset)
    mask = _obs_mask(ds2.observations, "2025-07-15")
    assert mask.sum() == 1
    ds2.observations = ds2.observations[~mask]

    row = _row_for(ds2, "2025-07-15")
    assert row.included_in_evaluation is False
    assert row.skip_reason == SKIP_MISSING_OBSERVATION


def test_skip_missing_forecast(dataset):
    ds2 = _clone(dataset)
    mask = _obs_mask(ds2.forecasts, "2025-07-15")
    assert mask.sum() == 3  # one row per source
    ds2.forecasts = ds2.forecasts[~mask]

    row = _row_for(ds2, "2025-07-15")
    assert row.included_in_evaluation is False
    assert row.skip_reason == SKIP_MISSING_FORECAST


def test_skip_invalid_data(dataset):
    ds2 = _clone(dataset)
    mask = _obs_mask(ds2.observations, "2025-07-15")
    ds2.observations.loc[mask, "observed_rain_mm"] = 9999.0  # implausible

    row = _row_for(ds2, "2025-07-15")
    assert row.included_in_evaluation is False
    assert row.skip_reason == SKIP_INVALID_DATA


def test_skip_insufficient_history(dataset):
    # Dataset starts 2025-06-01, so 2025-06-10 has only 9 prior history days.
    row = _row_for(dataset, "2025-06-10")
    assert row.included_in_evaluation is False
    assert row.skip_reason == SKIP_INSUFFICIENT_HISTORY
    assert row.prior_history_days == 9

    # The very next date passing the default 14-day rule is 2025-06-15.
    assert _row_for(dataset, "2025-06-15").included_in_evaluation is True


def test_skip_no_valid_source(dataset):
    ds2 = _clone(dataset)
    mask = _obs_mask(ds2.forecasts, "2025-07-15")
    ds2.forecasts.loc[mask, "status"] = "unavailable"
    ds2.forecasts.loc[mask, "forecast_rain_mm"] = None

    row = _row_for(ds2, "2025-07-15")
    assert row.included_in_evaluation is False
    assert row.skip_reason == SKIP_NO_VALID_SOURCE


# --------------------------------------------------------------------------------------
# G4. Empty / insufficient data — null metrics plus a clear warning, never a crash
# --------------------------------------------------------------------------------------
def test_all_skipped_range_returns_null_metrics(dataset):
    result = run_backtest(
        dataset,
        **PRAYAGRAJ,
        lead_hours=24,
        start_date="2025-06-01",
        end_date="2025-06-10",
    )
    assert result.total_requested_dates == 10
    assert result.evaluated_dates == 0
    assert result.skipped_dates == 10
    assert result.skipped_reason_counts[SKIP_INSUFFICIENT_HISTORY] == 10

    for method in METHOD_KEYS:
        reg = result.regression[method]
        assert reg.sample_count == 0
        assert reg.mae_mm is None and reg.rmse_mm is None
        assert reg.note is not None
        evt = result.events[method]
        assert evt.true_positives is None and evt.precision is None

    assert result.sufficient_sample_warning == INSUFFICIENT_SAMPLE_NOTE
    assert result.comparison["sufficient_sample"] is False
    assert result.comparison["outcome_summary"] == [INSUFFICIENT_SAMPLE_NOTE]


# --------------------------------------------------------------------------------------
# API contract (F) + validation
# --------------------------------------------------------------------------------------
def test_backtest_endpoint_contract(client):
    params = {
        "district": "Prayagraj",
        "lead_hours": 24,
        "start_date": "2025-07-01",
        "end_date": "2025-07-05",
        "include_daily_rows": True,
    }
    resp = client.get("/backtest", params=params)
    assert resp.status_code == 200
    body = resp.json()

    # mandatory labels
    assert body["disclaimer"] == settings.backtest_disclaimer
    assert "Development/Testing Only" in body["disclaimer"]
    assert body["data_mode"] == settings.data_mode

    # request / range / summary
    assert body["request"]["district"] == "Prayagraj"
    assert body["request"]["district_id"] == "prayagraj"
    assert body["request"]["lead_hours"] == 24
    assert body["request"]["include_daily_rows"] is True
    assert body["request"]["minimum_history_days"] == settings.default_minimum_history_days
    assert body["data_range"]["requested_start_date"] == "2025-07-01"
    summary = body["evaluation_summary"]
    assert summary["total_requested_dates"] == 5
    assert summary["evaluated_dates"] == 5
    assert summary["skipped_dates"] == 0
    assert set(summary["skipped_reason_counts"]) == {
        "missing_observation",
        "missing_forecast",
        "invalid_data",
        "insufficient_history",
        "no_valid_source",
    }
    # 5 dates < min_comparison_sample(20) -> exact insufficient-sample warning
    assert summary["sufficient_sample_warning"] == INSUFFICIENT_SAMPLE_NOTE

    # event threshold definition (24h: no scaling change)
    thr = body["event_threshold"]
    assert thr["configured_threshold_mm"] == 64.5
    assert thr["effective_threshold_mm"] == 64.5
    assert thr["scaling_applied"] is True

    # methods
    assert set(body["methods"]) == set(METHOD_KEYS)
    for method, payload in body["methods"].items():
        reg = payload["regression_metrics"]
        evt = payload["event_metrics"]
        assert reg["sample_count"] >= 1, method
        assert isinstance(reg["mae_mm"], float)
        assert isinstance(reg["rmse_mm"], float)
        assert isinstance(reg["mean_bias_error_mm"], float)
        assert evt["threshold_mm"] == 64.5
        assert evt["true_positives"] is not None
        assert isinstance(evt["precision"], (float, type(None)))

    # comparison + daily rows + limitations + report files
    comp = body["comparison_summary"]
    assert comp["varsha_vs_equal_weight_mae_delta_mm"] is not None
    assert comp["best_method_by_metric"]["mae_mm"] is not None
    assert comp["sufficient_sample"] is False
    assert comp["note"] == INSUFFICIENT_SAMPLE_NOTE
    assert len(body["daily_rows"]) == 5
    required_row_keys = {
        "date", "actual_rain_mm", "varsha_prediction_mm", "nwp_weight",
        "confidence_score", "risk_level", "fallback_mode", "included_in_evaluation",
        "skip_reason", "nwp_source_health", "prior_history_days",
    }
    assert required_row_keys <= set(body["daily_rows"][0])
    assert body["daily_rows"][0]["included_in_evaluation"] is True
    assert len(body["limitations"]) >= 5
    assert any("not an official-warning verification" in lim for lim in body["limitations"])
    assert body["report_files"]["csv"].startswith("backtest_prayagraj_24h_")
    assert body["report_files"]["json"].endswith(".json")


def test_daily_rows_omitted_by_default(client):
    resp = client.get(
        "/backtest",
        params={
            "district": "Prayagraj",
            "lead_hours": 24,
            "start_date": "2025-07-06",
            "end_date": "2025-07-08",
        },
    )
    assert resp.status_code == 200
    assert "daily_rows" not in resp.json()


def test_event_threshold_scales_with_lead(client):
    resp = client.get(
        "/backtest",
        params={
            "district": "Prayagraj",
            "lead_hours": 6,
            "start_date": "2025-07-06",
            "end_date": "2025-07-08",
        },
    )
    assert resp.status_code == 200
    thr = resp.json()["event_threshold"]
    assert thr["configured_threshold_mm"] == 64.5
    assert thr["effective_threshold_mm"] == pytest.approx(64.5 * 6 / 24)
    assert thr["scaling_applied"] is True


def test_event_threshold_override_respected(client):
    resp = client.get(
        "/backtest",
        params={
            "district": "Prayagraj",
            "lead_hours": 24,
            "start_date": "2025-07-06",
            "end_date": "2025-07-08",
            "heavy_rain_threshold_mm": 100,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["event_threshold"]["configured_threshold_mm"] == 100
    assert body["event_threshold"]["effective_threshold_mm"] == pytest.approx(100)
    assert body["request"]["heavy_rain_threshold_mm"] == 100


def test_dates_outside_dataset_are_skipped_not_crashed(client):
    resp = client.get(
        "/backtest",
        params={
            "district": "Prayagraj",
            "lead_hours": 24,
            "start_date": "2024-01-01",
            "end_date": "2024-01-03",
        },
    )
    assert resp.status_code == 200
    summary = resp.json()["evaluation_summary"]
    assert summary["evaluated_dates"] == 0
    assert summary["skipped_reason_counts"]["missing_observation"] == 3
    assert resp.json()["methods"]["nwp"]["regression_metrics"]["mae_mm"] is None


def test_honest_best_method_is_recomputed_from_returned_metrics(client):
    resp = client.get(
        "/backtest",
        params={
            "district": "Prayagraj",
            "lead_hours": 24,
            "start_date": "2025-07-01",
            "end_date": "2025-07-20",
            "include_daily_rows": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    maes = {
        key: body["methods"][key]["regression_metrics"]["mae_mm"] for key in METHOD_KEYS
    }
    comparable = [key for key in METHOD_KEYS if maes[key] is not None]
    expected_best = min(comparable, key=lambda key: maes[key])
    # The reported winner must equal the argmin of the returned metrics —
    # it is selected from computed values, never assumed to be VARSHA.
    assert body["comparison_summary"]["best_method_by_metric"]["mae_mm"] == expected_best

    summary = body["comparison_summary"]
    assert summary["varsha_vs_equal_weight_mae_delta_mm"] == pytest.approx(
        maes["varsha_dynamic_blend"] - maes["equal_weight"], abs=1e-4
    )
    best_single_mae = min(maes[key] for key in ("nwp", "ensemble", "ai_local"))
    assert summary["varsha_vs_best_single_source_mae_delta_mm"] == pytest.approx(
        maes["varsha_dynamic_blend"] - best_single_mae, abs=1e-4
    )
    assert any(
        "for this selected synthetic evaluation period" in line
        for line in summary["outcome_summary"]
    )
    # 20 evaluated dates meets min_comparison_sample -> real verdicts, no warning
    assert summary["sufficient_sample"] is True
    assert summary["note"] is None


def test_backtest_validation_errors(client):
    base = {
        "district": "Prayagraj",
        "start_date": "2025-07-01",
        "end_date": "2025-07-05",
    }

    bad_lead = client.get("/backtest", params={**base, "lead_hours": 12})
    assert bad_lead.status_code == 422
    assert bad_lead.json()["detail"]["error"] == "invalid_lead_hours"

    reversed_range = client.get(
        "/backtest", params={**base, "lead_hours": 24, "start_date": "2025-07-10"}
    )
    assert reversed_range.status_code == 422
    assert reversed_range.json()["detail"]["error"] == "invalid_date_range"

    huge = client.get(
        "/backtest",
        params={**base, "lead_hours": 24, "start_date": "2000-01-01", "end_date": "2010-01-01"},
    )
    assert huge.status_code == 422
    assert huge.json()["detail"]["error"] == "backtest_range_too_large"

    unknown = client.get(
        "/backtest",
        params={
            "district": "../../etc/passwd",
            "lead_hours": 24,
            "start_date": "2025-07-01",
            "end_date": "2025-07-05",
        },
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["error"] == "unknown_district"

    negative_history = client.get(
        "/backtest", params={**base, "lead_hours": 24, "minimum_history_days": -1}
    )
    assert negative_history.status_code == 422
    assert negative_history.json()["detail"]["error"] == "invalid_minimum_history_days"

    zero_threshold = client.get(
        "/backtest", params={**base, "lead_hours": 24, "heavy_rain_threshold_mm": 0}
    )
    assert zero_threshold.status_code == 422
