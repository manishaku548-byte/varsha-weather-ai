"""Tests for GET /health (liveness, labels, graceful degradation)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import dataset as dataset_module


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["dataset_loaded"] is True
    assert body["database_status"] == "connected"
    assert body["service"] == "VARSHA Weather AI"
    assert body["problem_statement_id"] == "SIH26081"
    assert body["records"]["districts"] == 5
    assert body["records"]["forecast_records"] > 0
    assert body["records"]["observation_records"] > 0

    # Mandatory labelling
    assert body["data_mode"] == "synthetic"
    assert "Synthetic Development Dataset" in body["data_label"]
    assert "Not an Official Weather Warning" in body["disclaimer"]
    assert "Decision-Support Prototype" in body["disclaimer"]


def test_health_degrades_when_dataset_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    dataset_module.clear_cache()

    with TestClient(app) as test_client:
        body = test_client.get("/health").json()

    assert body["dataset_loaded"] is False
    assert body["status"] == "degraded"
    assert body["records"] == {}
    # disclaimers still present even when degraded
    assert "Not an Official Weather Warning" in body["disclaimer"]
