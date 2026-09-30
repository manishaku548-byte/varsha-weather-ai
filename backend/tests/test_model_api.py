"""Phase 4 — endpoint behaviour, inference and disclosed fallback (spec G6, G7, G8).

What these tests protect at the API boundary:

* ``POST /model/train`` is the only training trigger, validates its input,
  reports honest metrics and skips (never fakes) on inadequate data;
* ``GET /model/report`` and ``GET /model/status`` describe the artifact state
  truthfully, including "nothing trained yet";
* ``GET /forecast`` uses the trained model when one exists and the precomputed
  CSV source when it does not — and always says which, with a reason;
* the Phase 4 additions never change the Phase 1-3 forecast/backtest contract.

Training is expensive, so the real 24h training run happens once per module.
"""

from __future__ import annotations

import json
import math

import pytest

from app.config import settings
from app.services.model_inference import FALLBACK_LABEL, MODEL_LABEL
from app.services.model_store import clear_model_cache, pipeline_path, report_path

LEAD = 24
DISTRICT_QUERY = "Prayagraj"
FORECAST_DATE = "2025-08-15"
PHASE4_DISCLAIMER_KEYS = ("Not Operational Weather Data", "Not an Official Weather Warning")


@pytest.fixture(scope="module")
def trained_24h(tmp_path_factory):
    """One real training run through the API into an isolated models dir."""
    from app.services.dataset import get_dataset
    from app.services.ml_training import train_local_correction_model

    directory = tmp_path_factory.mktemp("api_models")
    original_dir = settings.models_dir
    settings.models_dir = directory
    try:
        report = train_local_correction_model(
            get_dataset(), lead_hours=LEAD, force_retrain=True, cfg=settings
        )
    finally:
        settings.models_dir = original_dir
        clear_model_cache()
    return directory, report


@pytest.fixture()
def served_model(trained_24h, monkeypatch):
    """Point the app at the module-trained artifacts with inference enabled."""
    directory, report = trained_24h
    monkeypatch.setattr(settings, "models_dir", directory)
    monkeypatch.setattr(settings, "ml_inference_enabled", True)
    clear_model_cache()
    yield report
    clear_model_cache()


def _ai_source(body: dict) -> dict:
    return next(s for s in body["sources"] if s["source_id"] == "ai_local_v1")


# ----------------------------------------------------------------------------------
# training endpoint
# ----------------------------------------------------------------------------------
def test_train_endpoint_rejects_an_unsupported_lead(client, model_env):
    response = client.post("/model/train", json={"lead_hours": 12})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "lead_hours"


def test_train_endpoint_rejects_a_non_positive_minimum_sample(client, model_env):
    response = client.post(
        "/model/train", json={"lead_hours": 24, "minimum_samples": 0}
    )
    assert response.status_code == 422


def test_train_endpoint_runs_the_workflow_and_persists_artifacts(client, model_env):
    response = client.post("/model/train", json={"lead_hours": LEAD})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["report_type"] == "local_correction_model"
    assert body["lead_hours"] == LEAD
    for key in PHASE4_DISCLAIMER_KEYS:
        assert key in body["disclaimer"]
    assert body["data_mode"] == settings.data_mode
    assert body["selected_model"] in ("linear_regression", "hist_gradient_boosting")
    assert set(body["candidates"]) == {"linear_regression", "hist_gradient_boosting"}
    assert body["split"]["method"] == "chronological_by_unique_global_date"
    assert body["split"]["boundaries"]["train"]["end"] < (
        body["split"]["boundaries"]["validation"]["start"]
    )
    assert body["split"]["boundaries"]["validation"]["end"] < (
        body["split"]["boundaries"]["test"]["start"]
    )
    assert body["record_counts"]["test"] > 0
    assert body["held_out_test_metrics"]["sample_count"] == body["record_counts"]["test"]
    assert body["honesty"]["test_used_for_selection"] is False
    assert body["honesty"]["selection_metric"] == "validation_mae_only"
    assert isinstance(body["honesty"]["ml_worse_than_baseline"], bool)
    assert body["fallback"] == {"active": False, "label": MODEL_LABEL, "reason": None}
    assert body["feature_schema"]["version"] == settings.ml_feature_schema_version
    assert body["feature_schema"]["target"] == "target_observed_rain_mm"
    assert body["limitations"]
    assert pipeline_path(LEAD, settings).is_file()
    assert report_path(LEAD, settings).is_file()
    stored = json.loads(report_path(LEAD, settings).read_text(encoding="utf-8"))
    assert stored["model_version"] == body["model_version"]


def test_train_endpoint_is_idempotent_unless_force_is_requested(client, model_env):
    first = client.post("/model/train", json={"lead_hours": LEAD}).json()
    second = client.post("/model/train", json={"lead_hours": LEAD}).json()
    assert second["status"] == "already_trained"
    assert second["model_version"] == first["model_version"]
    forced = client.post(
        "/model/train", json={"lead_hours": LEAD, "force_retrain": True}
    ).json()
    assert forced["status"] == "completed"
    assert forced["model_version"] != first["model_version"]


def test_train_endpoint_skips_instead_of_training_a_misleading_model(client, model_env):
    response = client.post(
        "/model/train", json={"lead_hours": LEAD, "minimum_samples": 100_000}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "skipped_insufficient_data"
    assert body["model_version"] is None
    assert body["held_out_test_metrics"] is None
    assert body["fallback"]["active"] is True
    assert body["fallback"]["label"] == FALLBACK_LABEL
    assert body["warnings"]
    assert not pipeline_path(LEAD, settings).exists()


# ----------------------------------------------------------------------------------
# report + status endpoints
# ----------------------------------------------------------------------------------
def test_model_report_is_404_before_anything_is_trained(client, model_env):
    response = client.get("/model/report")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "model_not_trained"


def test_model_report_is_404_for_a_lead_that_was_never_trained(client, served_model):
    response = client.get("/model/report", params={"lead_hours": 72})
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "model_not_trained"
    assert response.json()["detail"]["lead_hours"] == 72


def test_model_report_returns_the_saved_report(client, served_model):
    response = client.get("/model/report", params={"lead_hours": LEAD})
    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == served_model["model_version"]
    assert body["selected_model"] == served_model["selected_model"]
    assert body["held_out_test_metrics"]["mae_mm"] == pytest.approx(
        served_model["held_out_test_metrics"]["mae_mm"], abs=1e-3
    )
    for key in PHASE4_DISCLAIMER_KEYS:
        assert key in body["disclaimer"]
    assert body["artifacts"]["pipeline_file"] == pipeline_path(LEAD, settings).name
    assert body["provenance"]["preprocessing_policy"]


def test_model_report_defaults_to_the_most_recently_trained_lead(client, served_model):
    response = client.get("/model/report")
    assert response.status_code == 200
    assert response.json()["lead_hours"] == LEAD


def test_model_status_reports_the_untrained_state_honestly(client, model_env):
    response = client.get("/model/status")
    assert response.status_code == 200
    body = response.json()
    assert body["artifact_exists"] is False
    assert body["trained_lead_hours"] == []
    assert body["model_version"] is None
    assert body["last_training_time"] is None
    assert body["inference_ready"] is False
    assert body["fallback_status"]["active"] is True
    assert body["fallback_status"]["label"] == FALLBACK_LABEL
    assert "POST /model/train" in body["fallback_status"]["reason"]
    assert set(body["per_lead"]) == {"6", "24", "72"}
    assert all(entry["artifact_exists"] is False for entry in body["per_lead"].values())
    assert all(entry["inference_ready"] is False for entry in body["per_lead"].values())
    assert "never" in body["note"].lower()
    for key in PHASE4_DISCLAIMER_KEYS:
        assert key in body["disclaimer"]


def test_model_status_reflects_a_trained_artifact(client, served_model):
    body = client.get("/model/status").json()
    assert body["artifact_exists"] is True
    assert body["trained_lead_hours"] == [LEAD]
    assert body["model_version"] == served_model["model_version"]
    assert body["inference_enabled"] is True
    assert body["inference_ready"] is True
    assert body["last_training_time"] == served_model["generated_at"]
    lead = body["per_lead"]["24"]
    assert lead["artifact_exists"] is True
    assert lead["inference_ready"] is True
    assert lead["selected_model"] == served_model["selected_model"]
    assert lead["held_out_test_mae_mm"] == pytest.approx(
        served_model["held_out_test_metrics"]["mae_mm"], abs=1e-3
    )
    assert body["per_lead"]["6"]["artifact_exists"] is False
    assert body["per_lead"]["72"]["artifact_exists"] is False
    assert body["fallback_status"]["active"] is False
    assert body["fallback_status"]["label"] == MODEL_LABEL


def test_model_status_shows_fallback_when_inference_is_disabled(
    client, served_model, monkeypatch
):
    monkeypatch.setattr(settings, "ml_inference_enabled", False)
    body = client.get("/model/status").json()
    assert body["artifact_exists"] is True
    assert body["inference_enabled"] is False
    assert body["inference_ready"] is False
    assert body["fallback_status"]["active"] is True
    assert body["fallback_status"]["label"] == FALLBACK_LABEL
    assert "VARSHA_ML_INFERENCE" in body["fallback_status"]["reason"]
    assert body["per_lead"]["24"]["artifact_exists"] is True
    assert body["per_lead"]["24"]["inference_ready"] is False


# ----------------------------------------------------------------------------------
# G6 — inference in GET /forecast
# ----------------------------------------------------------------------------------
def test_forecast_uses_the_trained_model_when_one_is_available(client, served_model):
    response = client.get(
        "/forecast",
        params={
            "district": DISTRICT_QUERY,
            "date": FORECAST_DATE,
            "lead_hours": LEAD,
        },
    )
    assert response.status_code == 200
    body = response.json()
    ai = _ai_source(body)
    assert ai["model_inference_available"] is True
    assert ai["source_label"] == MODEL_LABEL
    assert ai["model_version"] == served_model["model_version"]
    assert ai["model_report_reference"] == report_path(LEAD, settings).name
    assert ai["status"] == "model_inference"
    assert ai["quality_flag"] == "model_prediction"
    assert ai["bias"]["method"] == "model_output_passthrough"
    assert 0.0 <= ai["raw_forecast_mm"] <= settings.max_plausible_rain_mm

    provenance = body["ml_model"]
    assert provenance["source_label"] == MODEL_LABEL
    assert provenance["model_inference_available"] is True
    assert provenance["ai_local_model_prediction_mm"] == pytest.approx(
        ai["raw_forecast_mm"], abs=1e-3
    )
    assert provenance["feature_availability"] == "ok"
    assert provenance["model_version"] == served_model["model_version"]
    assert provenance["held_out_test_mae_mm"] == pytest.approx(
        served_model["held_out_test_metrics"]["mae_mm"], abs=1e-3
    )
    assert served_model["model_version"] in provenance["reason"]


def test_forecast_falls_back_and_discloses_it_when_no_model_is_trained(client, model_env):
    response = client.get(
        "/forecast",
        params={"district": DISTRICT_QUERY, "date": FORECAST_DATE, "lead_hours": LEAD},
    )
    assert response.status_code == 200
    body = response.json()
    ai = _ai_source(body)
    assert ai["model_inference_available"] is False
    assert ai["source_label"] == FALLBACK_LABEL
    assert ai["model_version"] is None
    assert ai["model_report_reference"] is None
    assert ai["model_inference_reason"]
    assert ai["status"] != "model_inference"

    provenance = body["ml_model"]
    assert provenance["source_label"] == FALLBACK_LABEL
    assert provenance["model_inference_available"] is False
    assert provenance["ai_local_model_prediction_mm"] is None
    assert provenance["reason"]
    # the value is the untouched precomputed CSV column
    dataset_value = _csv_ai_value(DISTRICT_QUERY, FORECAST_DATE, LEAD)
    assert ai["raw_forecast_mm"] == pytest.approx(dataset_value, abs=1e-6)


def test_forecast_falls_back_when_ml_inference_is_disabled(
    client, served_model, monkeypatch
):
    monkeypatch.setattr(settings, "ml_inference_enabled", False)
    body = client.get(
        "/forecast",
        params={"district": DISTRICT_QUERY, "date": FORECAST_DATE, "lead_hours": LEAD},
    ).json()
    ai = _ai_source(body)
    assert ai["source_label"] == FALLBACK_LABEL
    assert ai["model_inference_available"] is False
    assert "VARSHA_ML_INFERENCE" in ai["model_inference_reason"]
    assert body["ml_model"]["ai_local_model_prediction_mm"] is None


def test_forecast_falls_back_for_a_lead_without_a_trained_model(client, served_model):
    body = client.get(
        "/forecast",
        params={"district": DISTRICT_QUERY, "date": FORECAST_DATE, "lead_hours": 72},
    ).json()
    ai = _ai_source(body)
    assert ai["source_label"] == FALLBACK_LABEL
    assert ai["model_inference_available"] is False
    assert "72h" in ai["model_inference_reason"]


def test_forecast_falls_back_where_features_are_unavailable(client, served_model):
    """The first days of the series have no prior history — the model cannot be
    scored honestly there, so the fallback is used and said so."""
    body = client.get(
        "/forecast",
        params={"district": DISTRICT_QUERY, "date": "2025-06-02", "lead_hours": LEAD},
    ).json()
    ai = _ai_source(body)
    assert ai["model_inference_available"] is False
    assert ai["source_label"] == FALLBACK_LABEL
    assert body["ml_model"]["feature_availability"] == "insufficient_history"
    assert "prior usable observation day(s)" in body["ml_model"]["reason"]
    assert FALLBACK_LABEL in body["ml_model"]["reason"]


def test_model_prediction_feeds_the_blend_contribution(client, served_model):
    body = client.get(
        "/forecast",
        params={"district": DISTRICT_QUERY, "date": FORECAST_DATE, "lead_hours": LEAD},
    ).json()
    ai = _ai_source(body)
    contributions = {c["source_id"]: c for c in body["blend"]["contributions"]}
    assert "ai_local_v1" in contributions
    assert contributions["ai_local_v1"]["corrected_mm"] == pytest.approx(
        ai["corrected_forecast_mm"], abs=1e-3
    )
    assert ai["weight"] > 0.0, "the model output must be eligible for blending"


def test_explain_endpoint_carries_the_same_ml_provenance(client, served_model):
    body = client.get(
        "/forecast/explain",
        params={"district": DISTRICT_QUERY, "date": FORECAST_DATE, "lead_hours": LEAD},
    ).json()
    provenance = body["ml_model"]
    assert provenance["source_label"] == MODEL_LABEL
    assert provenance["model_inference_available"] is True
    assert provenance["model_version"] == served_model["model_version"]
    assert provenance["ai_local_model_prediction_mm"] is not None
    text = json.dumps(body)
    assert served_model["model_version"] in text
    assert "Not Operational Weather Data" in body["disclaimer"] or (
        "Not Operational Weather Data" in text
    )


def test_forecast_response_schema_is_unchanged_for_non_ai_sources(client, served_model):
    body = client.get(
        "/forecast",
        params={"district": DISTRICT_QUERY, "date": FORECAST_DATE, "lead_hours": LEAD},
    ).json()
    for source in body["sources"]:
        if source["source_id"] == "ai_local_v1":
            continue
        assert source["source_label"] is None
        assert source["model_inference_available"] is None
        assert source["model_version"] is None
        assert source["model_report_reference"] is None
    # Phase 1-3 fields are all still present
    for key in (
        "data_mode", "data_label", "disclaimer", "algorithm_version", "config_version",
        "district", "valid_date", "lead_hours", "issue_time", "validity_start",
        "validity_end", "simulate_failure_source", "data_availability",
        "prior_context", "weather_regime", "source_health", "sources", "blend",
        "fallback_mode", "confidence", "risk", "ml_model",
    ):
        assert key in body, key
    assert body["blend"]["final_rainfall_mm"] is not None
    assert body["confidence"]["score"] is not None
    assert body["weather_regime"]["label"] in (
        "Normal", "Active Monsoon", "Heavy-Rain Risk", "Heatwave"
    )
    assert body["risk"]["risk_level"] in ("Low", "Moderate", "High", "Critical")


def test_forecast_is_deterministic_for_the_same_request(client, served_model):
    params = {"district": DISTRICT_QUERY, "date": FORECAST_DATE, "lead_hours": LEAD}
    first = client.get("/forecast", params=params).json()
    second = client.get("/forecast", params=params).json()
    assert first["sources"] == second["sources"]
    assert first["blend"]["final_rainfall_mm"] == second["blend"]["final_rainfall_mm"]


# ----------------------------------------------------------------------------------
# G6 — backtest provenance (no per-date retraining)
# ----------------------------------------------------------------------------------
def test_backtest_reports_which_ai_source_drove_each_date(client, served_model):
    response = client.get(
        "/backtest",
        params={
            "district": DISTRICT_QUERY,
            "lead_hours": LEAD,
            "start_date": "2025-08-15",
            "end_date": "2025-08-18",
            "include_daily_rows": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    provenance = body["ai_source_provenance"]
    assert provenance["source_label"] == MODEL_LABEL
    assert provenance["model_inference_available"] is True
    assert provenance["mixed_inputs"] is False
    assert provenance["model_versions"] == [served_model["model_version"]]
    assert provenance["rows_using_fallback_source"] == 0
    assert provenance["rows_using_trained_model"] == len(body["daily_rows"])
    assert provenance["note"]
    for row in body["daily_rows"]:
        assert row["ai_source_label"] == MODEL_LABEL
        assert row["ai_model_version"] == served_model["model_version"]


def test_backtest_reports_the_fallback_label_without_a_model(client, model_env):
    response = client.get(
        "/backtest",
        params={
            "district": DISTRICT_QUERY,
            "lead_hours": LEAD,
            "start_date": "2025-08-15",
            "end_date": "2025-08-18",
            "include_daily_rows": True,
        },
    )
    body = response.json()
    assert body["ai_source_provenance"]["source_label"] == FALLBACK_LABEL
    assert body["ai_source_provenance"]["model_inference_available"] is False
    assert body["ai_source_provenance"]["rows_using_trained_model"] == 0
    assert body["ai_source_provenance"]["rows_using_fallback_source"] == len(
        body["daily_rows"]
    )
    for row in body["daily_rows"]:
        assert row["ai_source_label"] == FALLBACK_LABEL
        assert row["ai_model_version"] is None


def test_backtest_metrics_for_other_sources_are_untouched_by_the_ml_path(
    client, served_model, monkeypatch
):
    """The ML label is additive provenance only. Only the methods that consume the
    AI source may move: ``ai_local`` and both blends (which include it). The raw
    NWP and ensemble methods, the skip counts and the echoed request must not
    change at all."""
    params = {
        "district": DISTRICT_QUERY,
        "lead_hours": LEAD,
        "start_date": "2025-08-15",
        "end_date": "2025-08-18",
    }
    with_model = client.get("/backtest", params=params).json()
    monkeypatch.setattr(settings, "ml_inference_enabled", False)
    without_model = client.get("/backtest", params=params).json()

    for method in ("nwp", "ensemble"):
        assert with_model["methods"][method] == without_model["methods"][method], method
    for method in ("ai_local", "equal_weight", "varsha_dynamic_blend"):
        assert (
            with_model["methods"][method] != without_model["methods"][method]
        ), f"{method} consumes the AI source and is expected to differ"
    assert with_model["evaluation_summary"] == without_model["evaluation_summary"]
    assert with_model["request"] == without_model["request"]
    assert (
        with_model["ai_source_provenance"]["rows_using_trained_model"] > 0
    )
    assert without_model["ai_source_provenance"]["rows_using_trained_model"] == 0


def test_legacy_stored_reports_are_marked_as_fallback_provenance():
    from app.services.reporting import mark_legacy_ai_provenance

    legacy = {"report_type": "backtest", "row_counts": {"evaluated": 20, "skipped": 0}}
    marked = mark_legacy_ai_provenance(legacy)
    provenance = marked["ai_source_provenance"]
    assert provenance["source_label"] == FALLBACK_LABEL
    assert provenance["model_inference_available"] is False
    assert provenance["rows_using_trained_model"] == 0
    assert provenance["rows_using_fallback_source"] == 20
    assert "before the Phase 4" in provenance["note"]
    assert marked["row_counts"] == legacy["row_counts"], "nothing else is rewritten"

    already = {"ai_source_provenance": {"source_label": MODEL_LABEL}}
    assert mark_legacy_ai_provenance(already) is already


# ----------------------------------------------------------------------------------
# G8 — startup behaviour and OpenAPI
# ----------------------------------------------------------------------------------
def test_starting_the_app_does_not_train_anything(client, model_env):
    """A fresh models directory stays empty no matter which requests run."""
    client.get("/model/status")
    client.get(
        "/forecast",
        params={"district": DISTRICT_QUERY, "date": FORECAST_DATE, "lead_hours": LEAD},
    )
    assert not pipeline_path(LEAD, settings).exists()
    assert not report_path(LEAD, settings).exists()
    assert list(settings.models_dir.glob("*.joblib")) == []


def test_openapi_documents_the_model_endpoints(client):
    spec = client.get("/openapi.json").json()
    assert "/model/train" in spec["paths"]
    assert "/model/report" in spec["paths"]
    assert "/model/status" in spec["paths"]
    assert spec["paths"]["/model/train"]["post"]["tags"] == ["model"]
    assert spec["paths"]["/model/status"]["get"]["tags"] == ["model"]
    assert spec["info"]["version"] == "0.4.0"
    assert "model" in spec["info"]["description"].lower()


def test_health_endpoint_still_reports_phase_4(client, model_env):
    body = client.get("/health").json()
    assert body["status"] in ("ok", "degraded")
    assert body["phase"] == "Phase 4: AI/ML Local Correction Model"
    assert "Not Operational Weather Data" in body["disclaimer"]


# ----------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------
def _csv_ai_value(district_query: str, valid_date: str, lead_hours: int) -> float:
    from app.services.dataset import get_dataset

    ds = get_dataset()
    names = ds.districts.set_index("district_id")["district_name"].astype(str).to_dict()
    district_id = next(
        did for did, name in names.items() if name.lower() == district_query.lower()
    )
    import pandas as pd

    rows = ds.forecasts[
        (ds.forecasts["district_id"].astype(str) == district_id)
        & (ds.forecasts["source_id"].astype(str) == "ai_local_v1")
        & (pd.to_numeric(ds.forecasts["lead_hours"], errors="coerce") == lead_hours)
        & (ds.forecasts["valid_date"].astype(str) == valid_date)
    ]
    return float(rows.iloc[0]["forecast_rain_mm"])
