"""Phase 4 — feature engineering integrity (spec G1, G2, G8).

The three things these tests protect:

1. **No future-data leakage** — a feature row for date D must be byte-identical
   no matter what the observations/forecasts on or after D contain. Proven by
   perturbing the future and comparing the composed feature dicts.
2. **Strictly-prior inputs** — the rolling/lagged observation features are
   verified against values computed by hand from dates strictly before D.
3. **Honest availability** — every row carries a `feature_availability` flag
   that depends only on feature-side inputs (never on the observed target), so
   inference behaves identically whatever the observation turns out to be.
"""

from __future__ import annotations

import copy
import math

import pandas as pd
import pytest

from app.config import settings
from app.services.features import (
    CATEGORICAL_FEATURES,
    FEATURE_AVAILABILITY_INSUFFICIENT_HISTORY,
    FEATURE_AVAILABILITY_MISSING_FORECAST,
    FEATURE_AVAILABILITY_OK,
    FEATURE_COLUMNS,
    FEATURE_DOCS,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    build_feature_frame,
    build_feature_row,
    season_for_month,
)

DISTRICT = "prayagraj"
MID_DATE = "2025-08-15"
EARLY_DATE = "2025-06-03"
LEAD = 24
FUTURE_RAIN = 123.4
FUTURE_TEMP = 41.5
FUTURE_WIND = 3.0


# ----------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------
def _with_observations_after(ds, date_str, *, include_date: bool):
    """Dataset copy whose observations on/after ``date_str`` are overwritten."""
    perturbed = copy.copy(ds)
    obs = ds.observations.copy(deep=True)
    cutoff = pd.to_datetime(date_str)
    dates = pd.to_datetime(obs["valid_date"], errors="coerce")
    mask = dates >= cutoff if include_date else dates > cutoff
    obs.loc[mask, "observed_rain_mm"] = FUTURE_RAIN
    obs.loc[mask, "observed_temp_c"] = FUTURE_TEMP
    obs.loc[mask, "observed_wind_kmph"] = FUTURE_WIND
    perturbed.observations = obs
    return perturbed


def _with_forecasts_after(ds, date_str):
    """Dataset copy whose forecasts strictly after ``date_str`` are overwritten."""
    perturbed = copy.copy(ds)
    fc = ds.forecasts.copy(deep=True)
    mask = pd.to_datetime(fc["valid_date"], errors="coerce") > pd.to_datetime(date_str)
    fc.loc[mask, "forecast_rain_mm"] = FUTURE_RAIN
    fc.loc[mask, "ensemble_spread_mm"] = FUTURE_WIND
    perturbed.forecasts = fc
    return perturbed


def _features_equal(left: dict, right: dict) -> bool:
    """NaN-aware, type-aware feature-dict comparison."""
    if set(left) != set(right):
        return False
    for key, a in left.items():
        b = right[key]
        if isinstance(a, str) or isinstance(b, str):
            if a != b:
                return False
            continue
        a_nan = a is None or (isinstance(a, float) and math.isnan(a))
        b_nan = b is None or (isinstance(b, float) and math.isnan(b))
        if a_nan or b_nan:
            if not (a_nan and b_nan):
                return False
            continue
        if float(a) != float(b):
            return False
    return True


def _prior_observations(ds, district_id: str, valid_date: str, days: int | None = None):
    """Lead-24 observation series strictly before ``valid_date`` (oldest first)."""
    obs = ds.observations[
        (ds.observations["district_id"].astype(str) == district_id)
        & (pd.to_numeric(ds.observations["lead_hours"], errors="coerce") == 24)
    ].copy()
    obs["_date"] = pd.to_datetime(obs["valid_date"], errors="coerce")
    obs = obs[obs["_date"] < pd.to_datetime(valid_date)].sort_values("_date")
    obs = obs[obs["observed_rain_mm"].between(0, settings.max_plausible_rain_mm)]
    if days is not None:
        obs = obs.tail(days)
    return obs


@pytest.fixture(scope="module")
def frame_24():
    """Feature frame for the 24h horizon (built once — it is not a cheap call)."""
    from app.services.dataset import get_dataset

    return build_feature_frame(get_dataset(), lead_hours=24, cfg=settings)


# ----------------------------------------------------------------------------------
# schema / documentation
# ----------------------------------------------------------------------------------
def test_schema_documents_every_feature():
    assert FEATURE_COLUMNS == NUMERIC_FEATURES + CATEGORICAL_FEATURES
    assert len(NUMERIC_FEATURES) == 14
    assert CATEGORICAL_FEATURES == ["district", "season"]
    documented = {doc["feature"] for doc in FEATURE_DOCS}
    assert documented == set(FEATURE_COLUMNS)
    for doc in FEATURE_DOCS:
        assert doc["type"] in ("numeric", "categorical")
        assert doc["source"].strip()
        assert doc["timing"].strip()
        assert doc["leakage_safeguard"].strip()


def test_target_column_is_never_a_feature():
    assert TARGET_COLUMN not in FEATURE_COLUMNS
    assert TARGET_COLUMN == "target_observed_rain_mm"


def test_season_feature_is_a_pure_calendar_mapping():
    assert season_for_month(6) == "Monsoon"
    assert season_for_month(9) == "Monsoon"
    assert season_for_month(11) == "Post-monsoon"
    assert season_for_month(1) == "Winter"
    assert season_for_month(4) == "Pre-monsoon"


# ----------------------------------------------------------------------------------
# G1 — no future-to-past leakage
# ----------------------------------------------------------------------------------
def test_same_day_observation_never_enters_the_feature_row(dataset):
    row = build_feature_row(
        dataset, district_id=DISTRICT, valid_date=MID_DATE, lead_hours=LEAD, cfg=settings
    )
    perturbed = build_feature_row(
        _with_observations_after(dataset, MID_DATE, include_date=True),
        district_id=DISTRICT,
        valid_date=MID_DATE,
        lead_hours=LEAD,
        cfg=settings,
    )
    assert row.target_mm != perturbed.target_mm, "perturbation did not apply (vacuous test)"
    assert _features_equal(row.features, perturbed.features)
    assert row.feature_availability == perturbed.feature_availability


def test_later_observations_never_change_earlier_feature_rows(dataset):
    for date_str in ("2025-06-20", "2025-08-15", "2025-09-28"):
        base = build_feature_row(
            dataset,
            district_id=DISTRICT,
            valid_date=date_str,
            lead_hours=LEAD,
            cfg=settings,
        )
        perturbed = build_feature_row(
            _with_observations_after(dataset, date_str, include_date=False),
            district_id=DISTRICT,
            valid_date=date_str,
            lead_hours=LEAD,
            cfg=settings,
        )
        assert _features_equal(base.features, perturbed.features), date_str
        assert base.target_mm == perturbed.target_mm, date_str


def test_later_forecasts_never_change_earlier_feature_rows(dataset):
    base = build_feature_row(
        dataset, district_id=DISTRICT, valid_date=MID_DATE, lead_hours=LEAD, cfg=settings
    )
    perturbed = build_feature_row(
        _with_forecasts_after(dataset, MID_DATE),
        district_id=DISTRICT,
        valid_date=MID_DATE,
        lead_hours=LEAD,
        cfg=settings,
    )
    assert _features_equal(base.features, perturbed.features)


# ----------------------------------------------------------------------------------
# G2 — strictly-prior inputs, verified by hand
# ----------------------------------------------------------------------------------
def test_forecast_features_equal_the_raw_csv_values(dataset):
    row = build_feature_row(
        dataset, district_id=DISTRICT, valid_date=MID_DATE, lead_hours=LEAD, cfg=settings
    )
    raw = dataset.forecasts[
        (dataset.forecasts["district_id"].astype(str) == DISTRICT)
        & (pd.to_numeric(dataset.forecasts["lead_hours"], errors="coerce") == LEAD)
        & (pd.to_datetime(dataset.forecasts["valid_date"], errors="coerce")
           == pd.to_datetime(MID_DATE))
    ]
    by_source = {str(r["source_id"]): r for r in raw.to_dict("records")}
    assert row.features["nwp_rain_mm"] == pytest.approx(
        float(by_source["nwp_model_a"]["forecast_rain_mm"])
    )
    assert row.features["ensemble_mean_mm"] == pytest.approx(
        float(by_source["ensemble_mean"]["forecast_rain_mm"])
    )
    assert row.features["ensemble_spread_mm"] == pytest.approx(
        float(by_source["ensemble_mean"]["ensemble_spread_mm"])
    )
    # raw only: the feature is never the bias-corrected or blended value
    assert row.features["nwp_rain_mm"] == pytest.approx(
        float(by_source["nwp_model_a"]["forecast_rain_mm"])
    )
    assert row.features["district"] == DISTRICT
    assert row.features["season"] == season_for_month(8)
    assert row.features["month"] == 8.0
    assert row.features["lead_hours"] == float(LEAD)


def test_lagged_and_rolling_observation_features_use_only_prior_dates(dataset):
    row = build_feature_row(
        dataset, district_id=DISTRICT, valid_date=MID_DATE, lead_hours=LEAD, cfg=settings
    )
    prior = _prior_observations(dataset, DISTRICT, MID_DATE)
    last = prior.iloc[-1]
    w3, w7 = _prior_observations(dataset, DISTRICT, MID_DATE, 3), _prior_observations(
        dataset, DISTRICT, MID_DATE, 7
    )
    assert row.prior_observation_days == int(prior["_date"].nunique())
    assert row.features["prior_rain_1d_mm"] == pytest.approx(
        float(last["observed_rain_mm"])
    )
    assert row.features["prior_rain_3d_total_mm"] == pytest.approx(
        float(w3["observed_rain_mm"].sum())
    )
    assert row.features["prior_rain_3d_mean_mm"] == pytest.approx(
        float(w3["observed_rain_mm"].mean())
    )
    assert row.features["prior_rain_7d_total_mm"] == pytest.approx(
        float(w7["observed_rain_mm"].sum())
    )
    assert row.features["prior_rain_7d_mean_mm"] == pytest.approx(
        float(w7["observed_rain_mm"].mean())
    )
    assert row.features["prior_temp_c"] == pytest.approx(
        float(last["observed_temp_c"])
    )
    assert row.features["prior_wind_kmph"] == pytest.approx(
        float(last["observed_wind_kmph"])
    )


def test_prior_status_ratios_use_only_forecast_status_before_the_date(dataset):
    row = build_feature_row(
        dataset, district_id=DISTRICT, valid_date=MID_DATE, lead_hours=LEAD, cfg=settings
    )
    as_of = pd.to_datetime(MID_DATE)
    window_days = int(settings.source_health_window_days)
    for source_id, feature in (
        ("nwp_model_a", "nwp_prior_ok_ratio"),
        ("ensemble_mean", "ensemble_prior_ok_ratio"),
    ):
        mask = (
            (dataset.forecasts["source_id"].astype(str) == source_id)
            & (pd.to_datetime(dataset.forecasts["valid_date"], errors="coerce") < as_of)
            & (
                pd.to_datetime(dataset.forecasts["valid_date"], errors="coerce")
                >= as_of - pd.Timedelta(days=window_days)
            )
        )
        statuses = dataset.forecasts[mask]["status"].astype(str)
        expected = float((statuses == "ok").sum()) / float(len(statuses))
        assert row.features[feature] == pytest.approx(expected)


def test_target_is_the_observation_of_the_same_date_and_lead(dataset):
    row = build_feature_row(
        dataset, district_id=DISTRICT, valid_date=MID_DATE, lead_hours=LEAD, cfg=settings
    )
    obs = dataset.observations[
        (dataset.observations["district_id"].astype(str) == DISTRICT)
        & (pd.to_numeric(dataset.observations["lead_hours"], errors="coerce") == LEAD)
        & (pd.to_datetime(dataset.observations["valid_date"], errors="coerce")
           == pd.to_datetime(MID_DATE))
    ]
    assert row.target_mm == pytest.approx(float(obs.iloc[0]["observed_rain_mm"]))


# ----------------------------------------------------------------------------------
# availability flags
# ----------------------------------------------------------------------------------
def test_usable_row_is_complete_and_flagged_ok(dataset):
    row = build_feature_row(
        dataset, district_id=DISTRICT, valid_date=MID_DATE, lead_hours=LEAD, cfg=settings
    )
    assert row.is_usable is True
    assert row.feature_availability == FEATURE_AVAILABILITY_OK
    assert row.feature_skip_reason is None
    assert set(row.features) == set(FEATURE_COLUMNS)
    assert row.target_mm is not None


def test_insufficient_history_is_flagged_with_an_explicit_reason(dataset):
    row = build_feature_row(
        dataset, district_id=DISTRICT, valid_date=EARLY_DATE, lead_hours=LEAD, cfg=settings
    )
    assert row.is_usable is False
    assert row.feature_availability == FEATURE_AVAILABILITY_INSUFFICIENT_HISTORY
    assert row.features == {}
    assert row.prior_observation_days < int(settings.ml_min_feature_history_days)
    assert str(settings.ml_min_feature_history_days) in row.feature_skip_reason
    assert "2025-06-03" in row.feature_skip_reason


def test_absent_forecast_horizon_is_flagged_missing_forecast(dataset):
    row = build_feature_row(
        dataset, district_id=DISTRICT, valid_date=MID_DATE, lead_hours=12, cfg=settings
    )
    assert row.is_usable is False
    assert row.feature_availability == FEATURE_AVAILABILITY_MISSING_FORECAST
    assert "nwp_model_a" in row.feature_skip_reason
    assert "ensemble_mean" in row.feature_skip_reason


def test_unavailable_forecast_status_is_treated_as_missing(dataset):
    patched = copy.copy(dataset)
    fc = dataset.forecasts.copy(deep=True)
    mask = (
        (fc["district_id"].astype(str) == DISTRICT)
        & (pd.to_numeric(fc["lead_hours"], errors="coerce") == LEAD)
        & (pd.to_datetime(fc["valid_date"], errors="coerce") == pd.to_datetime(MID_DATE))
    )
    fc.loc[mask, "status"] = "unavailable"
    patched.forecasts = fc
    row = build_feature_row(
        patched, district_id=DISTRICT, valid_date=MID_DATE, lead_hours=LEAD, cfg=settings
    )
    assert row.is_usable is False
    assert row.feature_availability == FEATURE_AVAILABILITY_MISSING_FORECAST


def test_availability_never_depends_on_the_observed_value(dataset):
    base = build_feature_row(
        dataset, district_id=DISTRICT, valid_date=MID_DATE, lead_hours=LEAD, cfg=settings
    )
    perturbed = build_feature_row(
        _with_observations_after(dataset, MID_DATE, include_date=True),
        district_id=DISTRICT,
        valid_date=MID_DATE,
        lead_hours=LEAD,
        cfg=settings,
    )
    assert base.feature_availability == perturbed.feature_availability
    assert base.is_usable == perturbed.is_usable


# ----------------------------------------------------------------------------------
# feature frame (training input)
# ----------------------------------------------------------------------------------
def test_frame_is_complete_chronological_and_flagged(frame_24, dataset):
    dates = sorted(set(frame_24["valid_date"].astype(str)))
    districts = sorted(set(frame_24["district_id"].astype(str)))
    assert len(frame_24) == len(dates) * len(districts)
    assert dates == sorted(dates), "frame must be chronological by date"
    assert not frame_24.duplicated(subset=["valid_date", "district_id"]).any()
    assert set(frame_24["feature_availability"]) <= {
        FEATURE_AVAILABILITY_OK,
        FEATURE_AVAILABILITY_MISSING_FORECAST,
        FEATURE_AVAILABILITY_INSUFFICIENT_HISTORY,
    }
    for column in FEATURE_COLUMNS + [TARGET_COLUMN, "feature_availability",
                                    "feature_skip_reason", "prior_observation_days"]:
        assert column in frame_24.columns
    expected_districts = sorted(dataset.districts["district_id"].astype(str).unique())
    assert districts == expected_districts


def test_frame_excludes_unavailable_rows_with_a_reason(frame_24):
    bad = frame_24[frame_24["feature_availability"] != FEATURE_AVAILABILITY_OK]
    assert len(bad) > 0, "the earliest dates must be excluded (insufficient history)"
    for _, row in bad.iterrows():
        assert isinstance(row["feature_skip_reason"], str) and row["feature_skip_reason"]
    first_date = frame_24["valid_date"].astype(str).min()
    first_rows = frame_24[frame_24["valid_date"].astype(str) == first_date]
    assert set(first_rows["feature_availability"]) == {
        FEATURE_AVAILABILITY_INSUFFICIENT_HISTORY
    }


def test_frame_values_match_the_single_row_builder(dataset, frame_24):
    for district, date_str in (
        (DISTRICT, "2025-07-04"),
        (DISTRICT, "2025-08-15"),
        ("varanasi", "2025-09-20"),
        ("gorakhpur", "2025-08-30"),
    ):
        row = build_feature_row(
            dataset, district_id=district, valid_date=date_str, lead_hours=24,
            cfg=settings,
        )
        frame_row = frame_24[
            (frame_24["district_id"].astype(str) == district)
            & (frame_24["valid_date"].astype(str) == date_str)
        ].iloc[0]
        assert _features_equal(row.features, frame_row[FEATURE_COLUMNS].to_dict()), (
            district,
            date_str,
        )


def test_frame_construction_does_not_mutate_the_dataset(dataset):
    before_forecasts = dataset.forecasts.copy(deep=True)
    before_observations = dataset.observations.copy(deep=True)
    build_feature_row(
        dataset, district_id=DISTRICT, valid_date=MID_DATE, lead_hours=72, cfg=settings
    )
    assert dataset.forecasts.equals(before_forecasts)
    assert dataset.observations.equals(before_observations)
