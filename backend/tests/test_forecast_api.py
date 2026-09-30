"""Phase 2 API tests: /forecast, /forecast/explain and failure simulation.

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.services.forecast_engine import ForecastUnavailableError

DISCLAIMER = (
    "Decision-Support Prototype — Synthetic Development Dataset — "
    "Not Operational Weather Data — Not an Official Weather Warning."
)
RISK_DISCLAIMER = "Decision-support output only; not an official warning."
POINT = {"district": "Prayagraj", "date": "2025-09-15", "lead_hours": 24}


# --------------------------------------------------------------------------------------
# GET /forecast — success path
# --------------------------------------------------------------------------------------
def test_forecast_success_shape(client):
    response = client.get("/forecast", params=POINT)
    assert response.status_code == 200
    body = response.json()

    required = {
        "disclaimer",
        "data_mode",
        "data_label",
        "algorithm_version",
        "config_version",
        "district",
        "valid_date",
        "lead_hours",
        "issue_time",
        "validity_start",
        "validity_end",
        "data_availability",
        "prior_context",
        "weather_regime",
        "source_health",
        "sources",
        "blend",
        "fallback_mode",
        "confidence",
        "risk",
    }
    assert required <= set(body)
    assert body["district"]["district_name"] == "Prayagraj"
    assert body["valid_date"] == "2025-09-15"
    assert body["lead_hours"] == 24
    assert body["algorithm_version"] == settings.algorithm_version
    assert body["config_version"] == settings.config_version


def test_forecast_carries_combined_disclaimer(client):
    body = client.get("/forecast", params=POINT).json()
    assert body["disclaimer"] == DISCLAIMER
    assert body["data_mode"] == "synthetic"
    assert "Synthetic Development Dataset" in body["data_label"]
    assert body["risk"]["disclaimer"] == RISK_DISCLAIMER
    assert "no meteorological operational certification" in body["weather_regime"][
        "certification_note"
    ]


def test_forecast_has_no_nan_or_raw_unrounded_artifacts(client):
    text = client.get("/forecast", params=POINT).text
    assert "NaN" not in text
    assert "Infinity" not in text


def test_forecast_source_records_and_bias_metadata(client):
    body = client.get("/forecast", params=POINT).json()
    assert len(body["sources"]) == 3
    for source in body["sources"]:
        for key in ("raw_forecast_mm", "corrected_forecast_mm", "bias", "trust", "weight"):
            assert key in source
        bias = source["bias"]
        for key in (
            "bias_available",
            "bias_mm",
            "raw_forecast_mm",
            "corrected_forecast_mm",
            "historical_record_count",
            "reason",
        ):
            assert key in bias
        assert bias["historical_record_count"] > 0
        assert bias["bias_available"] is True

    trust_keys = {
        "historical_skill",
        "recent_skill",
        "health_score",
        "agreement",
        "context_factor",
        "trust_score",
        "weight",
        "reason",
        "historical_mae_mm",
        "recent_mae_mm",
    }
    for source in body["sources"]:
        assert trust_keys <= set(source["trust"])
        assert source["trust"]["reason"]


def test_forecast_weights_sum_to_one(client):
    body = client.get("/forecast", params=POINT).json()
    total = sum(source["weight"] for source in body["sources"])
    assert total == pytest.approx(1.0, abs=1e-9)
    contributions = sum(c["weight"] for c in body["blend"]["contributions"])
    assert contributions == pytest.approx(1.0, abs=1e-9)


def test_forecast_blend_identity_within_display_rounding(client):
    body = client.get("/forecast", params=POINT).json()
    manual = sum(
        c["weight"] * c["corrected_mm"] for c in body["blend"]["contributions"]
    )
    assert body["blend"]["final_rainfall_mm"] == pytest.approx(manual, abs=0.05)
    assert body["blend"]["fallback_mode"] == "normal"
    assert body["fallback_mode"] == body["blend"]["fallback_mode"]


def test_forecast_confidence_risk_and_health_fields(client):
    body = client.get("/forecast", params=POINT).json()
    confidence = body["confidence"]
    assert 0.0 <= confidence["score"] <= 100.0
    assert confidence["label"] in ("Low", "Medium", "High")
    assert confidence["explanation"]
    assert confidence["uncertainty_lower_mm"] <= body["blend"]["final_rainfall_mm"]
    assert confidence["uncertainty_upper_mm"] >= body["blend"]["final_rainfall_mm"]

    risk = body["risk"]
    assert risk["risk_level"] in ("Low", "Moderate", "High", "Critical")
    assert risk["reasons"]
    assert risk["preparedness_actions"]
    assert risk["validity_start"] < risk["validity_end"]

    assert len(body["source_health"]) == 3
    assert body["weather_regime"]["label"] in (
        "Normal",
        "Active Monsoon",
        "Heavy-Rain Risk",
        "Heatwave",
    )
    assert 0.0 <= body["weather_regime"]["confidence"] <= 1.0
    assert body["data_availability"]["data_available"] is True
    assert body["prior_context"]["prior_observation_days"] > 0


# --------------------------------------------------------------------------------------
# GET /forecast — error paths
# --------------------------------------------------------------------------------------
def test_forecast_requires_query_parameters(client):
    assert client.get("/forecast").status_code == 422
    assert (
        client.get(
            "/forecast",
            params={"district": "Prayagraj", "date": "2025-09-15"},
        ).status_code
        == 422
    )


def test_forecast_rejects_unsupported_lead(client):
    response = client.get(
        "/forecast", params={**POINT, "lead_hours": 12}
    )
    assert response.status_code == 422


def test_forecast_unknown_district_404(client):
    response = client.get("/forecast", params={**POINT, "district": "Atlantis"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "unknown_district"
    assert len(detail["available_districts"]) == 5


def test_forecast_date_out_of_range_404(client):
    response = client.get("/forecast", params={**POINT, "date": "2024-01-01"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "date_out_of_range"
    assert "outside the loaded dataset range" in detail["message"]


def test_forecast_invalid_failure_alias_422(client):
    response = client.get(
        "/forecast", params={**POINT, "simulate_failure_source": "radar"}
    )
    assert response.status_code == 422


def test_forecast_unavailable_returns_503(client, monkeypatch):
    def _boom(*args, **kwargs):
        raise ForecastUnavailableError(
            "Forecast unavailable — no usable source for Prayagraj."
        )

    monkeypatch.setattr("app.routers.forecast.run_forecast", _boom)
    response = client.get("/forecast", params=POINT)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "forecast_unavailable"
    assert "Forecast unavailable" in detail["message"]
    assert detail["disclaimer"] == DISCLAIMER


# --------------------------------------------------------------------------------------
# Failure simulation via query parameter
# --------------------------------------------------------------------------------------
def test_forecast_with_simulate_failure_source(client):
    baseline = client.get("/forecast", params=POINT).json()
    degraded = client.get(
        "/forecast", params={**POINT, "simulate_failure_source": "ai"}
    ).json()

    ai = next(s for s in degraded["sources"] if s["source_id"] == "ai_local_v1")
    assert ai["weight"] == 0.0
    assert ai["trust"]["trust_score"] == 0.0
    assert "Simulated failure" in ai["unavailable_reason"]
    assert degraded["fallback_mode"] == "degraded"
    assert degraded["confidence"]["score"] < baseline["confidence"]["score"]
    assert degraded["simulate_failure_source"] == "ai"

    others = [s for s in degraded["sources"] if s["source_id"] != "ai_local_v1"]
    assert sum(s["weight"] for s in others) == pytest.approx(1.0, abs=1e-9)


# --------------------------------------------------------------------------------------
# GET /forecast/explain
# --------------------------------------------------------------------------------------
def test_explain_matches_forecast_numbers(client):
    forecast = client.get("/forecast", params=POINT).json()
    explain = client.get("/forecast/explain", params=POINT).json()

    assert explain["disclaimer"] == DISCLAIMER
    assert explain["why_this_forecast_title"] == "Why this forecast?"
    assert explain["final_rainfall_mm"] == forecast["blend"]["final_rainfall_mm"]
    assert explain["confidence"]["score"] == forecast["confidence"]["score"]
    assert explain["risk"]["risk_level"] == forecast["risk"]["risk_level"]
    assert explain["regime"]["label"] == forecast["weather_regime"]["label"]
    assert explain["fallback_mode"] == forecast["fallback_mode"]


def test_explain_headline_contains_only_computed_values(client):
    forecast = client.get("/forecast", params=POINT).json()
    explain = client.get("/forecast/explain", params=POINT).json()

    final = forecast["blend"]["final_rainfall_mm"]
    assert f"{final:.1f} mm" in explain["headline"]
    # the regime and risk words in the headline come from the same response
    assert forecast["weather_regime"]["label"] in explain["headline"]
    assert forecast["risk"]["risk_level"] in explain["headline"]


def test_explain_sources_and_weights_match_forecast(client):
    forecast = client.get("/forecast", params=POINT).json()
    explain = client.get("/forecast/explain", params=POINT).json()

    forecast_weights = {s["source_id"]: s["weight"] for s in forecast["sources"]}
    explain_weights = {s["source_id"]: s["weight"] for s in explain["sources"]}
    assert forecast_weights == explain_weights

    top = explain["top_weighted_source"]
    assert top["weight"] == max(forecast_weights.values())
    assert top["reason"]
    assert explain["why_this_forecast"]
    assert explain["source_health_note"]


def test_explain_contains_no_placeholder_text(client):
    response = client.get("/forecast/explain", params=POINT)
    assert "NaN" not in response.text
    assert "Infinity" not in response.text
    explain = response.json()
    raw = str(explain).lower()
    for placeholder in ("todo", "tbd", "xxx", "lorem ipsum"):
        assert placeholder not in raw
    # every bullet must be a real sentence, not a stub
    for bullet in explain["why_this_forecast"]:
        assert len(bullet) > 20


# --------------------------------------------------------------------------------------
# POST /forecast/simulate-source-failure
# --------------------------------------------------------------------------------------
def test_simulate_source_failure_comparison(client):
    body = {
        "district": "Prayagraj",
        "date": "2025-09-15",
        "lead_hours": 24,
        "failed_source": "ensemble",
    }
    response = client.post("/forecast/simulate-source-failure", json=body)
    assert response.status_code == 200
    data = response.json()

    assert data["disclaimer"] == DISCLAIMER
    assert data["failed_source"] == "ensemble"
    assert data["failed_source_id"] == "ensemble_mean"

    # normal vs degraded summaries
    assert data["normal"]["fallback_mode"] == "normal"
    assert data["degraded"]["fallback_mode"] == "degraded"
    assert data["normal"]["weights"]["ensemble_mean"] > 0.0
    assert data["degraded"]["weights"]["ensemble_mean"] == 0.0
    assert sum(data["normal"]["weights"].values()) == pytest.approx(1.0, abs=1e-9)
    assert sum(data["degraded"]["weights"].values()) == pytest.approx(1.0, abs=1e-9)

    # weight + confidence changes are explicit
    assert len(data["weight_changes"]) == 3
    ens_change = next(
        w for w in data["weight_changes"] if w["source_id"] == "ensemble_mean"
    )
    assert ens_change["weight_after"] == 0.0
    assert ens_change["delta"] == -ens_change["weight_before"]
    for change in data["weight_changes"]:
        if change["source_id"] != "ensemble_mean":
            assert change["weight_after"] > change["weight_before"]

    assert data["confidence_change"]["delta"] < 0
    assert data["confidence_change"]["degraded"] < data["confidence_change"]["normal"]
    assert data["fallback_mode_change"] == {
        "normal": "normal",
        "degraded": "degraded",
    }
    assert data["explanation"]
    assert any("weight" in line for line in data["explanation"])
    assert data["normal"]["final_rainfall_mm"] != data["degraded"]["final_rainfall_mm"]


def test_simulate_source_failure_matches_forecast_endpoints(client):
    """The comparison uses the same engine as GET /forecast."""
    body = {
        "district": "Prayagraj",
        "date": "2025-09-15",
        "lead_hours": 24,
        "failed_source": "nwp",
    }
    data = client.post("/forecast/simulate-source-failure", json=body).json()
    normal = client.get("/forecast", params=POINT).json()
    degraded = client.get(
        "/forecast", params={**POINT, "simulate_failure_source": "nwp"}
    ).json()

    assert data["normal"]["final_rainfall_mm"] == normal["blend"]["final_rainfall_mm"]
    assert data["degraded"]["final_rainfall_mm"] == degraded["blend"]["final_rainfall_mm"]
    assert data["normal"]["confidence_score"] == normal["confidence"]["score"]
    assert data["degraded"]["confidence_score"] == degraded["confidence"]["score"]


def test_simulate_source_failure_error_paths(client):
    base = {
        "district": "Prayagraj",
        "date": "2025-09-15",
        "lead_hours": 24,
        "failed_source": "ai",
    }

    unknown = client.post(
        "/forecast/simulate-source-failure", json={**base, "district": "Atlantis"}
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["error"] == "unknown_district"

    bad_date = client.post(
        "/forecast/simulate-source-failure", json={**base, "date": "15-09-2025"}
    )
    assert bad_date.status_code == 422

    bad_source = client.post(
        "/forecast/simulate-source-failure", json={**base, "failed_source": "radar"}
    )
    assert bad_source.status_code == 422

    out_of_range = client.post(
        "/forecast/simulate-source-failure", json={**base, "date": "2024-06-01"}
    )
    assert out_of_range.status_code == 404
    assert out_of_range.json()["detail"]["error"] == "date_out_of_range"
