"""Tests for GET /data/summary (counts, validation, source health, filters)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import dataset as dataset_module

VALID_DAYS = 120
DISTRICTS = 5
LEADS = 3
SOURCES = 3


def test_summary_counts_and_labels(client: TestClient) -> None:
    response = client.get("/data/summary")
    assert response.status_code == 200
    body = response.json()

    assert body["district_count"] == DISTRICTS
    assert body["total_forecast_records"] == DISTRICTS * VALID_DAYS * LEADS * SOURCES
    assert body["total_observation_records"] == DISTRICTS * VALID_DAYS * LEADS
    assert body["lead_hours"] == [6, 24, 72]
    assert body["first_valid_date"] == "2025-06-01"
    assert body["last_valid_date"] == "2025-09-28"
    assert set(body["source_record_counts"]) == {
        "nwp_model_a",
        "ensemble_mean",
        "ai_local_v1",
    }
    # Mandatory labelling
    assert body["data_mode"] == "synthetic"
    assert "Synthetic Development Dataset" in body["data_label"]
    assert "Not an Official Weather Warning" in body["disclaimer"]
    # Structure is valid even though quality flags exist (anomalous rows etc.)
    assert body["validation"]["structure_ok"] is True
    assert body["validation"]["blocking_issues"] == []
    assert body["validation"]["checked_forecast_rows"] == (
        DISTRICTS * VALID_DAYS * LEADS * SOURCES
    )


def test_summary_rainfall_distribution_is_complete(client: TestClient) -> None:
    body = client.get("/data/summary").json()
    buckets = body["rainfall_24h_overall"]

    assert sum(buckets.values()) == DISTRICTS * VALID_DAYS
    assert buckets["dry"] > 0
    assert buckets["moderate"] > 0
    assert buckets["heavy"] > 0
    assert buckets["very_heavy"] >= 20  # 8 very-heavy days per district minimum
    assert buckets["extreme"] >= 5  # 3 extreme days per district minimum


def test_summary_reports_all_source_health_states(client: TestClient) -> None:
    body = client.get("/data/summary").json()
    health = {h["source_id"]: h for h in body["source_health"]}

    assert set(health) == {"nwp_model_a", "ensemble_mean", "ai_local_v1"}
    allowed = {"Healthy", "Delayed", "Unavailable", "Anomalous"}
    assert {h["status"] for h in health.values()} <= allowed

    # The synthetic dataset deliberately contains a recent NWP delay burst and
    # a recent AI anomaly burst so the dashboard can demonstrate real states.
    assert health["nwp_model_a"]["status"] == "Delayed"
    assert health["ai_local_v1"]["status"] == "Anomalous"
    assert health["ensemble_mean"]["status"] == "Healthy"
    for h in health.values():
        assert h["reason"]
        assert 0.0 <= h["unavailable_ratio"] <= 1.0


def test_summary_status_counts_include_disturbances(client: TestClient) -> None:
    body = client.get("/data/summary").json()
    counts = body["source_status_counts"]

    assert counts["nwp_model_a"]["delayed"] > 0
    assert counts["ai_local_v1"]["anomalous"] > 0
    # scattered unavailable / anomalous records exist across sources
    assert any(c.get("unavailable", 0) > 0 for c in counts.values())
    # every row carries a status -> totals reconcile
    total = sum(sum(c.values()) for c in counts.values())
    assert total == body["total_forecast_records"]


def test_summary_district_filter(client: TestClient) -> None:
    response = client.get("/data/summary", params={"district": "Prayagraj"})
    assert response.status_code == 200
    body = response.json()

    assert body["district_count"] == 1
    assert body["districts"][0]["district_id"] == "prayagraj"
    assert body["total_observation_records"] == VALID_DAYS * LEADS
    assert len(body["source_health"]) == 3  # health is still reported per source
    assert body["districts"][0]["mean_observed_24h_mm"] is not None


def test_summary_accepts_district_id_or_name(client: TestClient) -> None:
    by_id = client.get("/data/summary", params={"district": "gorakhpur"}).json()
    by_name = client.get("/data/summary", params={"district": "Gorakhpur"}).json()
    assert by_id["district_count"] == 1
    assert by_id["total_forecast_records"] == by_name["total_forecast_records"]


def test_summary_unknown_district_is_helpful(client: TestClient) -> None:
    response = client.get("/data/summary", params={"district": "Atlantis"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "Unknown district" in detail
    assert "Prayagraj" in detail


def test_summary_returns_503_with_hint_when_dataset_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)  # empty directory
    dataset_module.clear_cache()

    with TestClient(app) as test_client:
        response = test_client.get("/data/summary")

    assert response.status_code == 503
    payload = response.json()
    assert "districts.csv" in payload["detail"]
    assert "synthetic_generator" in payload["hint"]
