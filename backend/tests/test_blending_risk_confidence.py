"""Phase 2 tests: blending, confidence/uncertainty and the rainfall risk engine.

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

import pytest

from app.config import settings, thresholds_for_lead
from app.services.blend import blend_sources, fallback_mode_for
from app.services.confidence import compute_confidence, confidence_label
from app.services.forecast_engine import run_forecast
from app.services.risk import assess_risk

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


# --------------------------------------------------------------------------------------
# Blending
# --------------------------------------------------------------------------------------
def test_blend_equals_sum_of_weighted_corrected_values(dataset):
    for date, lead in ((DATE, 24), (DATE, 6), (DATE, 72), ("2025-07-20", 24)):
        result = _run(dataset, date=date, lead=lead)
        manual = sum(
            sf.weight * sf.corrected_forecast_mm
            for sf in result.sources
            if sf.eligible and sf.corrected_forecast_mm is not None
        )
        assert result.blend.final_rainfall_mm == pytest.approx(manual, abs=1e-9)
        contributions = sum(c["contribution_mm"] for c in result.blend.contributions)
        assert result.blend.final_rainfall_mm == pytest.approx(contributions, abs=1e-9)
        assert result.blend.final_rainfall_mm >= 0.0


def test_blend_supports_all_three_leads(dataset):
    for lead in (6, 24, 72):
        result = _run(dataset, lead=lead)
        assert result.lead_hours == lead
        assert result.blend.final_rainfall_mm >= 0.0
        assert result.validity_start < result.validity_end


def test_fallback_mode_classification():
    nwp, ens, ai = "nwp_model_a", "ensemble_mean", "ai_local_v1"
    corrected = {nwp: 10.0, ens: 20.0, ai: 30.0}
    third = 1 / 3
    assert blend_sources(corrected, {nwp: third, ens: third, ai: third}).fallback_mode == "normal"
    assert blend_sources(corrected, {nwp: 0.5, ens: 0.5, ai: 0.0}).fallback_mode == "degraded"
    single = blend_sources(corrected, {nwp: 1.0, ens: 0.0, ai: 0.0})
    assert single.fallback_mode == "single_source"
    assert "single-source fallback" in single.fallback_note
    assert single.final_rainfall_mm == pytest.approx(10.0)
    assert blend_sources(corrected, {nwp: 0.0, ens: 0.0, ai: 0.0}).fallback_mode == "unavailable"
    assert fallback_mode_for(3) == "normal"
    assert fallback_mode_for(2) == "degraded"
    assert fallback_mode_for(1) == "single_source"


# --------------------------------------------------------------------------------------
# Confidence and uncertainty
# --------------------------------------------------------------------------------------
def test_confidence_bands():
    assert confidence_label(0) == "Low"
    assert confidence_label(39.9) == "Low"
    assert confidence_label(40) == "Medium"
    assert confidence_label(69.9) == "Medium"
    assert confidence_label(70) == "High"
    assert confidence_label(100) == "High"


def _confidence(**overrides):
    kwargs = dict(
        available_count=3,
        weighted_historical_skill=0.8,
        weighted_health=1.0,
        weighted_agreement=0.9,
        ensemble_spread_mm=8.0,
        disagreement_mm=4.0,
        blend_mm=50.0,
        fallback_mode="normal",
    )
    kwargs.update(overrides)
    return compute_confidence(**kwargs)


def test_confidence_reduced_for_failure_and_disagreement():
    normal = _confidence()
    failed = _confidence(available_count=2, fallback_mode="degraded")
    disagreeing = _confidence(weighted_agreement=0.2, disagreement_mm=40.0)
    low_skill = _confidence(weighted_historical_skill=0.1, weighted_health=0.3)

    assert failed.score < normal.score
    assert disagreeing.score < normal.score
    assert low_skill.score < normal.score
    assert 0.0 <= normal.score <= 100.0


def test_confidence_caps_for_fallbacks():
    generous = dict(
        weighted_historical_skill=1.0,
        weighted_health=1.0,
        weighted_agreement=1.0,
        ensemble_spread_mm=0.1,
        disagreement_mm=0.0,
        blend_mm=30.0,
    )
    single = _confidence(available_count=1, fallback_mode="single_source", **generous)
    degraded = _confidence(available_count=2, fallback_mode="degraded", **generous)
    assert single.score <= settings.confidence_cap_single_source
    assert single.label == "Low"
    assert degraded.score <= settings.confidence_cap_degraded
    assert degraded.label in ("Low", "Medium")


def test_confidence_explanation_lists_factors():
    result = _confidence()
    assert result.explanation
    joined = " ".join(result.explanation)
    assert "available sources" in joined
    assert "historical skill" in joined
    assert "ensemble spread" in joined
    assert set(result.factors) >= {
        "available_sources",
        "historical_skill",
        "health",
        "agreement",
        "ensemble_spread",
    }


def test_uncertainty_range_brackets_blend(dataset):
    result = _run(dataset)
    conf = result.confidence
    blend = result.blend.final_rainfall_mm
    assert conf.uncertainty_lower_mm is not None
    assert conf.uncertainty_upper_mm is not None
    assert conf.uncertainty_lower_mm <= blend <= conf.uncertainty_upper_mm
    assert conf.uncertainty_lower_mm >= 0.0
    assert conf.uncertainty_half_width_mm >= 0.0
    assert "not a calibrated" in conf.uncertainty_basis


def test_failure_lowers_confidence_engine_level(dataset):
    normal = _run(dataset)
    failed = _run(dataset, failed="ensemble")
    assert failed.confidence.score < normal.confidence.score
    assert normal.blend.fallback_mode == "normal"
    assert failed.blend.fallback_mode == "degraded"


# --------------------------------------------------------------------------------------
# Risk engine
# --------------------------------------------------------------------------------------
def _risk(rainfall: float, *, regime: str = "Normal", confidence: float = 75.0,
          label: str = "High", lead: int = 24):
    return assess_risk(
        rainfall_mm=rainfall,
        regime_label=regime,
        confidence_score=confidence,
        confidence_label=label,
        valid_date=DATE,
        lead_hours=lead,
    )


def test_risk_thresholds_classify_values_at_24h():
    assert _risk(0.0).risk_level == "Low"
    assert _risk(10.0).risk_level == "Low"
    assert _risk(15.5).risk_level == "Low"
    assert _risk(15.6).risk_level == "Moderate"
    assert _risk(64.4).risk_level == "Moderate"
    assert _risk(64.5).risk_level == "High"
    assert _risk(115.5).risk_level == "High"
    assert _risk(115.6).risk_level == "Critical"
    assert _risk(300.0).risk_level == "Critical"


def test_risk_extreme_category_adds_reason():
    result = _risk(250.0)
    assert any("Extreme category crossed" in reason for reason in result.reasons)


def test_risk_uses_lead_scaled_thresholds():
    thresholds6 = thresholds_for_lead(6, settings)
    assert _risk(thresholds6["heavy"] - 0.1, lead=6).risk_level == "Moderate"
    assert _risk(thresholds6["heavy"], lead=6).risk_level == "High"


def test_risk_escalates_for_heavy_rain_regime():
    escalated = _risk(20.0, regime="Heavy-Rain Risk")
    assert escalated.escalated is True
    assert escalated.risk_level == "High"
    already_high = _risk(70.0, regime="Heavy-Rain Risk")
    assert already_high.escalated is False
    assert already_high.risk_level == "High"


def test_risk_low_confidence_adds_caveat_not_downgrade():
    result = _risk(70.0, confidence=25.0, label="Low")
    assert result.risk_level == "High"
    assert any("caveat" in reason for reason in result.reasons)


def test_risk_output_fields_and_disclaimer():
    result = _risk(120.0, confidence=45.0, label="Medium")
    assert result.event_type == "heavy_rainfall"
    assert result.predicted_rainfall_mm == 120.0
    assert result.validity_start == "2025-09-14T00:00:00Z"  # valid_date - 24h
    assert result.validity_end == f"{DATE}T00:00:00Z"
    assert result.confidence_score == 45.0
    assert result.reasons
    assert result.preparedness_actions
    assert result.disclaimer == "Decision-support output only; not an official warning."
    assert "not an official warning" in result.disclaimer.lower()
    assert result.thresholds_used["heavy_mm"] == pytest.approx(64.5)


def test_risk_validity_window_matches_lead():
    result = _risk(10.0, lead=6)
    assert result.validity_start == "2025-09-14T18:00:00Z"
    assert result.validity_end == f"{DATE}T00:00:00Z"


def test_preparedness_actions_are_configured_per_level():
    for level in settings.risk_levels:
        assert settings.preparedness_actions[level], level
    assert _risk(0.0).preparedness_actions
    high = _risk(100.0)
    assert high.risk_level == "High"
    assert high.preparedness_actions
    critical = _risk(250.0)
    assert critical.risk_level == "Critical"
    assert critical.preparedness_actions
