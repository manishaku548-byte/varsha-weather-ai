"""Phase 5 tests: expert override + audit timeline endpoints.

These cover the minimal local-review API added so the dashboard can record an
expert override and render the audit timeline. The storage tables already
existed (SRS NFR-REL-05); Phase 5 only exposes POST /overrides and
GET /audit-logs over them.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import pytest

from app.database import SessionLocal, init_db
from app import models


@pytest.fixture(autouse=True)
def _clean_audit_tables():
    """Audit tests never depend on rows left behind by earlier tests."""
    init_db()
    with SessionLocal() as db:
        db.query(models.OverrideDecision).delete()
        db.query(models.AuditLog).delete()
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(models.OverrideDecision).delete()
        db.query(models.AuditLog).delete()
        db.commit()


def _valid_payload(**overrides) -> dict:
    payload = {
        "district": "Prayagraj",
        "date": "2025-09-15",
        "lead_hours": 24,
        "selected_risk_level": "High",
        "reason": "District control room reports localised ponding; escalate for "
        "preparedness coordination.",
        "reviewer_name": "Test Reviewer",
        "role": "forecaster",
    }
    payload.update(overrides)
    return payload


def test_create_override_success(client):
    resp = client.post("/overrides", json=_valid_payload())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data_mode"] == "synthetic"
    assert "Decision-Support Prototype" in body["disclaimer"]
    assert "not an official authorization record" in body["note"]

    record = body["record"]
    assert record["district_id"] == "prayagraj"
    assert record["district_name"] == "Prayagraj"
    assert record["valid_date"] == "2025-09-15"
    assert record["lead_hours"] == 24
    assert record["actor"] == "Test Reviewer"
    assert record["role"] == "forecaster"
    assert record["overridden_risk_level"] == "High"
    assert record["reason"].startswith("District control room")
    # The system's own output is preserved alongside the expert decision.
    assert record["original_risk_level"] in {"Low", "Moderate", "High", "Critical"}
    assert isinstance(record["original_forecast_mm"], (int, float))
    assert record["original_output"]["algorithm_version"] == "varsha-blend-2.0.0"
    assert record["original_output"]["final_rainfall_mm"] == record[
        "original_forecast_mm"
    ]
    assert record["id"] >= 1


def test_override_original_output_matches_live_forecast(client):
    """The stored original output must equal the engine's own forecast point."""
    forecast = client.get(
        "/forecast",
        params={
            "district": "Prayagraj",
            "date": "2025-09-15",
            "lead_hours": 24,
        },
    )
    assert forecast.status_code == 200, forecast.text
    fc = forecast.json()
    displayed_mm = round(float(fc["blend"]["final_rainfall_mm"]), 4)

    resp = client.post("/overrides", json=_valid_payload())
    assert resp.status_code == 200, resp.text
    record = resp.json()["record"]
    # Stored value keeps engine precision (4 decimals); the API display rounds.
    assert abs(record["original_forecast_mm"] - displayed_mm) < 0.01
    assert record["original_output"]["risk_level"] == fc["risk"]["risk_level"]
    assert record["original_output"]["weather_regime"] == fc["weather_regime"]["label"]
    assert record["original_output"]["ai_source_label"] == "fallback_precomputed_ai_source"


def test_override_reason_is_mandatory(client):
    resp = client.post("/overrides", json=_valid_payload(reason="   "))
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["error"] == "reason_required"


def test_override_invalid_date(client):
    resp = client.post("/overrides", json=_valid_payload(date="2025-13-40"))
    assert resp.status_code == 422, resp.text
    assert "error" in resp.json()["detail"]


def test_override_unknown_district(client):
    resp = client.post("/overrides", json=_valid_payload(district="nope"))
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["error"] == "unknown_district"


def test_override_invalid_lead(client):
    resp = client.post("/overrides", json=_valid_payload(lead_hours=12))
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    if isinstance(detail, list):  # pydantic validation error list
        assert any("lead_hours" in repr(e.get("loc", "")) for e in detail)
    else:
        assert detail["error"] == "invalid_lead_hours"


def test_audit_logs_show_created_override(client):
    created = client.post("/overrides", json=_valid_payload()).json()["record"]
    resp = client.get("/audit-logs")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] >= 1
    assert body["note"] == (
        "Prototype local review log — not an official authorization record."
    )
    entry = body["entries"][0]
    assert entry["kind"] == "override"
    assert entry["id"] == created["id"]
    assert entry["original_risk_level"] == created["original_risk_level"]
    assert entry["overridden_risk_level"] == "High"
    assert entry["reason"] == created["reason"]
    assert entry["actor"] == "Test Reviewer"


def test_audit_logs_overrides_newest_first(client):
    for i in range(3):
        client.post(
            "/overrides",
            json=_valid_payload(
                reason=f"reason number {i}",
                reviewer_name=f"Reviewer {i}",
            ),
        )
    body = client.get("/audit-logs").json()
    entries = [e for e in body["entries"] if e["kind"] == "override"][:3]
    # created_at is second-granularity; order by id desc for stability.
    ids = [e["id"] for e in entries]
    assert ids == sorted(ids, reverse=True)


def test_audit_logs_kind_filter_system(client):
    resp = client.get("/audit-logs", params={"kind": "system"})
    assert resp.status_code == 200, resp.text
    for entry in resp.json()["entries"]:
        assert entry["kind"] == "system"


def test_audit_logs_limit_validation(client):
    resp = client.get("/audit-logs", params={"limit": 0})
    assert resp.status_code == 422, resp.text