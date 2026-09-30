"""Phase 2 tests: Dynamic Trust Engine (SRS FR-DTE-01..06).

Covers weight normalization, zero-weight rules, single-source fallback,
forecast-unavailable behaviour, score components and the no-future-data rule.

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from app.config import SOURCE_DEFINITIONS, settings
from app.services.forecast_engine import (
    ForecastUnavailableError,
    run_forecast,
)
from app.services.trust import agreement_score, compute_trust, inverse_mae_skill

DATE = "2025-09-15"
DISTRICT = "prayagraj"
DISTRICT_NAME = "Prayagraj"


def _run(ds, *, date: str = DATE, lead: int = 24, failed: str | None = None):
    return run_forecast(
        ds,
        district_id=DISTRICT,
        district_name=DISTRICT_NAME,
        valid_date=date,
        lead_hours=lead,
        simulate_failure_source=failed,
    )


def _drop_rows(ds, sources: list[str], date: str = DATE, lead: int = 24):
    """Remove forecast rows for the given sources at the test point."""
    mask = (
        (ds.forecasts["district_id"].astype(str) == DISTRICT)
        & (pd.to_numeric(ds.forecasts["lead_hours"], errors="coerce") == lead)
        & (pd.to_datetime(ds.forecasts["valid_date"]) == pd.Timestamp(date))
        & (ds.forecasts["source_id"].isin(sources))
    )
    return dataclasses.replace(ds, forecasts=ds.forecasts[~mask].copy())


def test_weights_sum_to_one_for_valid_sources(dataset):
    for date in ("2025-09-15", "2025-07-20", "2025-06-15"):
        for lead in (6, 24, 72):
            result = _run(dataset, date=date, lead=lead)
            eligible = [sf for sf in result.sources if sf.eligible]
            assert eligible, f"no eligible source for {date} {lead}h"
            total = sum(sf.weight for sf in result.sources)
            assert total == pytest.approx(1.0, abs=1e-9)
            if len(eligible) == 3:
                assert result.blend.fallback_mode == "normal"
                assert all(sf.weight > 0 for sf in result.sources)


def test_known_good_point_blends_all_three(dataset):
    """2025-09-15 / 24h is a verified clean point: all three sources usable."""
    result = _run(dataset)
    assert result.blend.fallback_mode == "normal"
    assert len(result.blend.contributions) == 3
    assert sum(sf.weight for sf in result.sources) == pytest.approx(1.0, abs=1e-9)


def test_weights_are_stored_per_component(dataset):
    result = _run(dataset)
    for source in result.sources:
        trust = source.trust
        assert trust is not None
        assert 0.0 <= trust.historical_skill <= 1.0
        assert 0.0 <= trust.recent_skill <= 1.0
        assert 0.0 <= trust.health_score <= 1.0
        assert 0.0 <= trust.agreement <= 1.0
        assert trust.context_factor > 0.0
        assert trust.trust_score >= 0.0
        expected = (
            settings.trust_weights["historical_skill"] * trust.historical_skill
            + settings.trust_weights["recent_skill"] * trust.recent_skill
            + settings.trust_weights["health"] * trust.health_score
            + settings.trust_weights["agreement"] * trust.agreement
        ) * trust.context_factor
        assert trust.trust_score == pytest.approx(expected, abs=1e-5)
        assert trust.reason


def test_health_score_mapping_is_configurable(dataset):
    result = _run(dataset)
    for source in result.sources:
        assert source.trust.health_score == pytest.approx(
            settings.health_score_map[source.trust.health_status]
        )


def test_unavailable_source_gets_exactly_zero_weight_and_trust(dataset):
    """Mark the ensemble row unavailable at the point -> weight and trust are 0."""
    forecasts = dataset.forecasts.copy()
    mask = (
        (forecasts["district_id"].astype(str) == DISTRICT)
        & (pd.to_numeric(forecasts["lead_hours"], errors="coerce") == 24)
        & (pd.to_datetime(forecasts["valid_date"]) == pd.Timestamp(DATE))
        & (forecasts["source_id"] == "ensemble_mean")
    )
    forecasts.loc[mask, "status"] = "unavailable"
    forecasts.loc[mask, "forecast_rain_mm"] = float("nan")
    modified = dataclasses.replace(dataset, forecasts=forecasts)

    result = _run(modified)
    ensemble = next(s for s in result.sources if s.source_id == "ensemble_mean")
    assert ensemble.eligible is False
    assert ensemble.trust.trust_score == 0.0
    assert ensemble.weight == 0.0
    others = [s for s in result.sources if s.source_id != "ensemble_mean"]
    assert sum(s.weight for s in others) == pytest.approx(1.0, abs=1e-9)
    assert result.blend.fallback_mode == "degraded"
    assert "ensemble_mean" in result.blend.unavailable_sources


def test_single_source_fallback_weight_exactly_one(dataset):
    reduced = _drop_rows(dataset, ["ensemble_mean", "ai_local_v1"])
    result = _run(reduced)

    nwp = next(s for s in result.sources if s.source_id == "nwp_model_a")
    others = [s for s in result.sources if s.source_id != "nwp_model_a"]

    assert result.blend.fallback_mode == "single_source"
    assert nwp.weight == 1.0
    assert all(s.weight == 0.0 for s in others)
    assert all(s.trust.trust_score == 0.0 for s in others)
    assert "single-source fallback" in result.blend.fallback_note


def test_no_valid_source_raises_forecast_unavailable(dataset):
    reduced = _drop_rows(dataset, ["nwp_model_a", "ensemble_mean", "ai_local_v1"])
    with pytest.raises(ForecastUnavailableError) as excinfo:
        _run(reduced)
    message = str(excinfo.value)
    assert "Forecast unavailable" in message
    assert "no usable source" in message.lower()
    # each source's reason is surfaced
    for display in SOURCE_DEFINITIONS.values():
        assert display["display_name"] in message


def test_failed_source_zero_weight_with_two_remaining(dataset):
    result = _run(dataset, failed="ai")
    ai = next(s for s in result.sources if s.source_id == "ai_local_v1")
    assert ai.weight == 0.0
    assert ai.trust.trust_score == 0.0
    assert "Simulated failure" in (ai.ineligible_reason or "")
    assert result.blend.fallback_mode == "degraded"
    remaining = [s for s in result.sources if s.source_id != "ai_local_v1"]
    assert sum(s.weight for s in remaining) == pytest.approx(1.0, abs=1e-9)


def test_inverse_mae_skill_monotone():
    assert inverse_mae_skill(0.0, settings) == 1.0
    assert inverse_mae_skill(5.0, settings) > inverse_mae_skill(20.0, settings)
    assert inverse_mae_skill(20.0, settings) > inverse_mae_skill(100.0, settings)
    assert inverse_mae_skill(None, settings) == settings.skill_score_when_no_history


def test_agreement_penalises_distance_from_median():
    assert agreement_score(20.0, 20.0, settings) == 1.0
    near = agreement_score(24.0, 20.0, settings)
    far = agreement_score(60.0, 20.0, settings)
    assert near > far >= 0.0
    # zero-median case uses the configured floor scale
    assert agreement_score(5.0, 0.0, settings) == pytest.approx(0.5)


def _direct_trust(**overrides):
    kwargs = dict(
        eligible={sid: True for sid in SOURCE_DEFINITIONS},
        ineligible_reasons={},
        health_status={sid: "Healthy" for sid in SOURCE_DEFINITIONS},
        corrected_mm={sid: 20.0 for sid in SOURCE_DEFINITIONS},
        historical_mae_mm={sid: 10.0 for sid in SOURCE_DEFINITIONS},
        historical_counts={sid: 100 for sid in SOURCE_DEFINITIONS},
        recent_mae_mm={sid: 10.0 for sid in SOURCE_DEFINITIONS},
        recent_counts={sid: 14 for sid in SOURCE_DEFINITIONS},
        regime_label="Normal",
        lead_hours=24,
    )
    kwargs.update(overrides)
    return compute_trust(**kwargs)


def test_context_regime_factor_applied():
    normal = _direct_trust(regime_label="Normal")
    heavy = _direct_trust(regime_label="Heavy-Rain Risk")
    nwp_normal = next(s for s in normal.sources if s.source_id == "nwp_model_a")
    nwp_heavy = next(s for s in heavy.sources if s.source_id == "nwp_model_a")
    ensemble_heavy = next(s for s in heavy.sources if s.source_id == "ensemble_mean")

    expected_nwp = settings.context_regime_factors["nwp_model_a"]["Heavy-Rain Risk"]
    expected_ens = settings.context_regime_factors["ensemble_mean"]["Heavy-Rain Risk"]
    assert nwp_normal.context_factor == pytest.approx(1.0)
    assert nwp_heavy.context_factor == pytest.approx(expected_nwp)
    assert ensemble_heavy.context_factor == pytest.approx(expected_ens)


def test_context_lead_factor_applied():
    result = _direct_trust(lead_hours=6)
    ai = next(s for s in result.sources if s.source_id == "ai_local_v1")
    expected = settings.context_lead_factors["ai_local_v1"]["6"]
    assert ai.context_factor == pytest.approx(expected)


def test_better_skill_source_receives_higher_weight():
    trust = _direct_trust(
        historical_mae_mm={
            "nwp_model_a": 5.0,
            "ensemble_mean": 30.0,
            "ai_local_v1": 12.0,
        },
        recent_mae_mm={
            "nwp_model_a": 5.0,
            "ensemble_mean": 30.0,
            "ai_local_v1": 12.0,
        },
    )
    weights = {s.source_id: s.weight for s in trust.sources}
    assert weights["nwp_model_a"] > weights["ai_local_v1"] > weights["ensemble_mean"]
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)


def test_no_skill_history_applies_neutral_score():
    trust = _direct_trust(
        historical_mae_mm={sid: None for sid in SOURCE_DEFINITIONS},
        historical_counts={sid: 0 for sid in SOURCE_DEFINITIONS},
        recent_mae_mm={sid: None for sid in SOURCE_DEFINITIONS},
        recent_counts={sid: 0 for sid in SOURCE_DEFINITIONS},
    )
    for source in trust.sources:
        assert source.historical_skill == pytest.approx(
            settings.skill_score_when_no_history
        )
    assert sum(s.weight for s in trust.sources) == pytest.approx(1.0, abs=1e-9)


def test_health_unavailable_forces_zero_trust_and_weight():
    health = {sid: "Healthy" for sid in SOURCE_DEFINITIONS}
    health["nwp_model_a"] = "Unavailable"
    trust = _direct_trust(health_status=health)
    nwp = next(s for s in trust.sources if s.source_id == "nwp_model_a")
    assert nwp.eligible is False
    assert nwp.trust_score == 0.0
    assert nwp.weight == 0.0
    others = [s for s in trust.sources if s.source_id != "nwp_model_a"]
    assert sum(s.weight for s in others) == pytest.approx(1.0, abs=1e-9)


def test_skill_and_recent_mae_ignore_future_observations(dataset):
    """Perturbing observations at/after the date must not move skills or weights."""
    baseline = _run(dataset)

    obs = dataset.observations.copy()
    mask = pd.to_datetime(obs["valid_date"]) >= pd.Timestamp(DATE)
    obs.loc[mask, "observed_rain_mm"] = 500.0
    polluted = dataclasses.replace(dataset, observations=obs)
    after = _run(polluted)

    for before_src, after_src in zip(baseline.sources, after.sources):
        assert before_src.trust.historical_mae_mm == after_src.trust.historical_mae_mm
        assert before_src.trust.recent_mae_mm == after_src.trust.recent_mae_mm
        assert before_src.weight == pytest.approx(after_src.weight, abs=1e-12)
