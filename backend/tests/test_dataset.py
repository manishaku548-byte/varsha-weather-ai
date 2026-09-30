"""Integration tests for the synthetic development dataset.

⚠️ Synthetic Development Dataset — Not Operational Weather Data.
These tests assert structure, plausibility and deterministic regeneration.
"""

from __future__ import annotations

import shutil

import numpy as np
import pandas as pd

from app.config import SOURCE_DEFINITIONS, settings
from app.data.synthetic_generator import generate_dataset

VALID_DAYS = 120
DISTRICTS = ["prayagraj", "lucknow", "varanasi", "kanpur-nagar", "gorakhpur"]


# --------------------------------------------------------------------------------------
# Files and schema
# --------------------------------------------------------------------------------------
def test_required_files_exist() -> None:
    for name in (
        settings.districts_file,
        settings.forecasts_file,
        settings.observations_file,
    ):
        path = settings.data_dir / name
        assert path.is_file(), f"missing dataset file: {path}"


def test_provider_description_carries_synthetic_label(dataset) -> None:
    description = dataset.provider_description
    assert description["data_mode"] == "synthetic"
    assert "Synthetic Development Dataset" in description["label"]
    assert "NOT IMD" in description["provenance_note"]


def test_district_file_matches_mvp_scope(dataset) -> None:
    ids = dataset.districts["district_id"].tolist()
    assert ids == DISTRICTS
    assert dataset.districts["district_name"].tolist() == [
        "Prayagraj",
        "Lucknow",
        "Varanasi",
        "Kanpur Nagar",
        "Gorakhpur",
    ]


def test_forecast_schema_and_contract(dataset) -> None:
    fc = dataset.forecasts
    assert set(
        [
            "district_id",
            "valid_date",
            "lead_hours",
            "source_id",
            "issue_time",
            "forecast_rain_mm",
            "unit",
            "status",
            "quality_flag",
            "ensemble_spread_mm",
            "ensemble_p10_mm",
            "ensemble_p90_mm",
        ]
    ) <= set(fc.columns)

    assert len(fc) == len(DISTRICTS) * VALID_DAYS * 3 * len(SOURCE_DEFINITIONS)
    assert set(fc["lead_hours"]) == {6, 24, 72}
    assert set(fc["unit"]) == {settings.forecast_unit}
    assert set(fc["source_id"]) == set(SOURCE_DEFINITIONS)
    assert set(fc["district_id"]) == set(DISTRICTS)
    assert set(fc["status"]) <= set(settings.valid_forecast_statuses)


def test_observation_schema_and_coverage(dataset) -> None:
    obs = dataset.observations
    assert len(obs) == len(DISTRICTS) * VALID_DAYS * 3
    assert set(obs["lead_hours"]) == {6, 24, 72}
    assert set(obs["unit"]) == {settings.forecast_unit}

    per_district = obs[obs["lead_hours"] == 24].groupby("district_id").size()
    assert (per_district >= settings.min_daily_records_per_district).all()


def test_every_district_has_full_date_range(dataset) -> None:
    obs = dataset.observations
    dates = obs.groupby("district_id")["valid_date"].nunique()
    assert (dates == VALID_DAYS).all()
    assert obs["valid_date"].min() == "2025-06-01"
    assert obs["valid_date"].max() == "2025-09-28"


# --------------------------------------------------------------------------------------
# Physical / temporal consistency
# --------------------------------------------------------------------------------------
def test_issue_time_plus_lead_equals_valid_time(dataset) -> None:
    """No temporal leakage in the data contract: issue + lead == valid."""
    fc = dataset.forecasts
    issue = pd.to_datetime(fc["issue_time"], utc=True, errors="coerce")
    valid = pd.to_datetime(fc["valid_date"], utc=True, errors="coerce")
    assert issue.notna().all() and valid.notna().all()
    aligned = issue + pd.to_timedelta(fc["lead_hours"], unit="h")
    assert (aligned == valid).all()


def test_rainfall_distribution_contains_all_categories(dataset) -> None:
    obs24 = dataset.observations[dataset.observations["lead_hours"] == 24]
    for d_id in DISTRICTS:
        values = obs24.loc[obs24["district_id"] == d_id, "observed_rain_mm"]
        assert (values == 0).sum() >= 30, f"{d_id}: too few dry days"
        assert (values >= 64.5).sum() >= 8, f"{d_id}: too few heavy days"
        assert (values >= 115.6).sum() >= 6, f"{d_id}: too few very-heavy days"
        assert values.max() >= 150, f"{d_id}: no really heavy event"
        assert values.max() <= settings.max_plausible_rain_mm


def test_heatwave_days_exist(dataset) -> None:
    obs24 = dataset.observations[dataset.observations["lead_hours"] == 24]
    heat = obs24[obs24["observed_temp_c"] >= 40.0]
    assert len(heat) >= 5
    # heatwave days are dry
    assert (heat["observed_rain_mm"] == 0).all()


def test_unavailable_rows_have_no_value(dataset) -> None:
    unavailable = dataset.forecasts[dataset.forecasts["status"] == "unavailable"]
    assert len(unavailable) > 0, "dataset should contain unavailable source records"
    assert unavailable["forecast_rain_mm"].isna().all()


def test_anomalous_rows_are_implausible(dataset) -> None:
    anomalous = dataset.forecasts[dataset.forecasts["status"] == "anomalous"]
    assert len(anomalous) > 0
    # explicit: every anomalous row is either negative or above the plausible cap
    implausible = (anomalous["forecast_rain_mm"] < 0) | (
        anomalous["forecast_rain_mm"] > settings.max_plausible_rain_mm
    )
    assert implausible.all()


def test_quality_flags_are_reported_not_silent(dataset) -> None:
    flags = dataset.validation.quality_flags
    assert flags["implausible_value"] > 0  # anomalous rows are flagged, not hidden
    assert flags["unexpected_value"] == 0  # unavailable rows never carry a value
    assert dataset.validation.structure_ok is True
    assert dataset.validation.blocking_issues == []


# --------------------------------------------------------------------------------------
# Simulated source behaviour
# --------------------------------------------------------------------------------------
def _merged(dataset) -> pd.DataFrame:
    fc = dataset.forecasts.drop(columns=["unit"])
    obs = dataset.observations.drop(columns=["unit"])
    return fc.merge(obs, on=["district_id", "valid_date", "lead_hours"], how="inner")


def test_nwp_underpredicts_heavy_rainfall(dataset) -> None:
    merged = _merged(dataset)
    heavy = merged[
        (merged["lead_hours"] == 24)
        & (merged["observed_rain_mm"] >= 64.5)
        & (merged["status"] == "ok")
        & (merged["source_id"] == "nwp_model_a")
    ]
    bias = (heavy["forecast_rain_mm"] - heavy["observed_rain_mm"]).mean()
    assert bias < 0, "NWP should systematically underpredict heavy rainfall events"


def test_ensemble_provides_spread_and_percentiles(dataset) -> None:
    ensemble = dataset.forecasts[
        (dataset.forecasts["source_id"] == "ensemble_mean")
        & (dataset.forecasts["status"] == "ok")
    ]
    assert ensemble["ensemble_spread_mm"].notna().all()
    assert (ensemble["ensemble_spread_mm"] > 0).all()
    assert (ensemble["ensemble_p10_mm"] <= ensemble["forecast_rain_mm"]).all()
    assert (ensemble["ensemble_p90_mm"] >= ensemble["forecast_rain_mm"]).all()

    others = dataset.forecasts[dataset.forecasts["source_id"] != "ensemble_mean"]
    assert others["ensemble_spread_mm"].isna().all()


def test_sources_differ_from_each_other(dataset) -> None:
    merged = _merged(dataset)
    ok = merged[merged["status"] == "ok"]
    pivoted = ok.pivot_table(
        index=["district_id", "valid_date", "lead_hours"],
        columns="source_id",
        values="forecast_rain_mm",
    ).dropna()
    # unavailable rows legitimately leave holes; most keys must still be complete
    assert len(pivoted) >= 0.80 * (len(DISTRICTS) * VALID_DAYS * 3)
    spread = pivoted.max(axis=1) - pivoted.min(axis=1)
    assert (spread > 0).mean() > 0.9, "sources should rarely produce identical values"


# --------------------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------------------
def test_generator_is_deterministic(tmp_path) -> None:
    shutil.copy(settings.data_dir / settings.districts_file, tmp_path / "districts.csv")
    counts = generate_dataset(tmp_path, seed=42)
    assert counts["forecast_records"] == len(DISTRICTS) * VALID_DAYS * 3 * len(SOURCE_DEFINITIONS)
    assert counts["observation_records"] == len(DISTRICTS) * VALID_DAYS * 3

    for filename in (settings.forecasts_file, settings.observations_file):
        committed = pd.read_csv(settings.data_dir / filename)
        regenerated = pd.read_csv(tmp_path / filename)
        pd.testing.assert_frame_equal(committed, regenerated)


def test_generator_requires_district_metadata(tmp_path) -> None:
    try:
        generate_dataset(tmp_path)
    except FileNotFoundError as exc:
        assert settings.districts_file in str(exc)
    else:  # pragma: no cover
        raise AssertionError("generator should require districts.csv")


def test_numpy_seed_reproducibility() -> None:
    a = np.random.default_rng(42).random(3)
    b = np.random.default_rng(42).random(3)
    assert np.allclose(a, b)
