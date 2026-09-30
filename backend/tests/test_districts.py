"""Tests for GET /districts."""

from __future__ import annotations

from fastapi.testclient import TestClient

EXPECTED = ["Prayagraj", "Lucknow", "Varanasi", "Kanpur Nagar", "Gorakhpur"]


def test_districts_returns_five_mvp_districts(client: TestClient) -> None:
    response = client.get("/districts")
    assert response.status_code == 200

    body = response.json()
    assert body["count"] == 5
    assert [d["district_name"] for d in body["districts"]] == EXPECTED
    assert body["data_mode"] == "synthetic"
    assert "Synthetic Development Dataset" in body["data_label"]
    assert "Not an Official Weather Warning" in body["disclaimer"]


def test_district_coordinates_are_plausible(client: TestClient) -> None:
    districts = client.get("/districts").json()["districts"]
    for district in districts:
        assert 24.0 < district["latitude"] < 28.5  # Uttar Pradesh
        assert 77.0 < district["longitude"] < 84.5
        assert district["state"] == "Uttar Pradesh"
        assert district["district_id"]


def test_district_schema_is_explicit(client: TestClient) -> None:
    districts = client.get("/districts").json()["districts"]
    keys = {"district_id", "district_name", "state", "latitude", "longitude"}
    for district in districts:
        assert set(district) == keys
