"""Phase 2 tests: rule-based regime detection and its priority order.

Priority: Heavy-Rain Risk > Heatwave > Active Monsoon > Normal.
Plus a leakage test: regime never reads observations from the selected date.

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from app.config import settings, thresholds_for_lead
from app.services.forecast_engine import run_forecast
from app.services.regime import detect_regime

DATE = "2025-07-15"
DISTRICT = "prayagraj"


def _regime(**overrides):
    kwargs = dict(
        ensemble_mm=0.0,
        corrected_values=[0.0],
        trailing_3day_mm=0.0,
        temp_c=30.0,
        humidity_pct=50.0,
        lead_hours=24,
    )
    kwargs.update(overrides)
    return detect_regime(**kwargs)


def test_heavy_rain_risk_has_highest_priority():
    result = _regime(
        ensemble_mm=80.0,
        corrected_values=[72.0],
        temp_c=42.0,
        humidity_pct=25.0,
        trailing_3day_mm=0.0,
    )
    assert result.label == "Heavy-Rain Risk"
    assert result.triggered_rules  # rules are reported
    assert any("heavy_rain" in rule for rule in result.triggered_rules)


def test_heatwave_selected_when_no_heavy_signal():
    result = _regime(ensemble_mm=0.0, corrected_values=[1.0], temp_c=41.5)
    assert result.label == "Heatwave"
    assert 0.0 <= result.confidence <= 1.0
    assert any("heatwave" in rule for rule in result.triggered_rules)


def test_active_monsoon_from_ensemble_signal():
    result = _regime(ensemble_mm=30.0, corrected_values=[25.0], temp_c=30.0)
    assert result.label == "Active Monsoon"
    assert any("active_monsoon" in rule for rule in result.triggered_rules)


def test_active_monsoon_from_trailing_rainfall():
    result = _regime(ensemble_mm=2.0, corrected_values=[1.0], trailing_3day_mm=55.0)
    assert result.label == "Active Monsoon"


def test_active_monsoon_from_humidity_proxy():
    result = _regime(ensemble_mm=2.0, corrected_values=[1.0], humidity_pct=88.0)
    assert result.label == "Active Monsoon"


def test_normal_when_no_rule_triggers():
    result = _regime()
    assert result.label == "Normal"
    assert result.triggered_rules == []
    assert result.reason
    assert 0.0 <= result.confidence <= 1.0


def test_heatwave_beats_monsoon_but_not_heavy():
    heat_vs_monsoon = _regime(ensemble_mm=30.0, temp_c=41.0, humidity_pct=85.0)
    assert heat_vs_monsoon.label == "Heatwave"

    heavy_vs_heat = _regime(ensemble_mm=90.0, temp_c=43.0)
    assert heavy_vs_heat.label == "Heavy-Rain Risk"


def test_thresholds_are_configured_and_scale_with_lead():
    result24 = _regime()
    assert result24.thresholds_used["heavy_rain_mm"] == pytest.approx(64.5)

    result6 = _regime(lead_hours=6)
    expected6 = thresholds_for_lead(6, settings)["heavy"]
    assert result6.thresholds_used["heavy_rain_mm"] == pytest.approx(expected6)
    assert expected6 < 64.5

    result72 = _regime(lead_hours=72)
    assert result72.thresholds_used["heavy_rain_mm"] > 64.5


def test_reason_is_human_readable_and_states_no_certification():
    result = _regime(ensemble_mm=80.0, corrected_values=[70.0])
    assert len(result.reason) > 30
    assert "certified" not in result.reason.lower()


def test_regime_ignores_selected_date_observations(dataset):
    """Regime context (temp/humidity/trailing rain) must come from prior dates only."""
    baseline = run_forecast(
        dataset,
        district_id=DISTRICT,
        district_name="Prayagraj",
        valid_date=DATE,
        lead_hours=24,
    )

    obs = dataset.observations.copy()
    mask = pd.to_datetime(obs["valid_date"]) >= pd.Timestamp(DATE)
    # Make the selected/future days look like an extreme heatwave + deluge.
    obs.loc[mask, "observed_temp_c"] = 47.0
    obs.loc[mask, "observed_humidity_pct"] = 99.0
    obs.loc[mask, "observed_rain_mm"] = 300.0
    polluted = dataclasses.replace(dataset, observations=obs)

    after = run_forecast(
        polluted,
        district_id=DISTRICT,
        district_name="Prayagraj",
        valid_date=DATE,
        lead_hours=24,
    )

    assert after.regime.label == baseline.regime.label
    assert after.regime.triggered_rules == baseline.regime.triggered_rules
    # Bias/skill must be unchanged as well (same leakage boundary).
    for before_src, after_src in zip(baseline.sources, after.sources):
        assert before_src.bias.bias_mm == after_src.bias.bias_mm
        assert before_src.trust.historical_mae_mm == after_src.trust.historical_mae_mm
