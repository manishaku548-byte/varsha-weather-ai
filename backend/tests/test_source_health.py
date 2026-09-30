"""Unit tests for the source-health service."""

from __future__ import annotations

import pandas as pd

from app.config import SOURCE_DEFINITIONS, settings
from app.services.source_health import compute_source_health

BASE_DATE = pd.Timestamp("2025-06-01")
WINDOW = settings.source_health_window_days  # 14 days


def frame(statuses: dict[str, list[str]], start: pd.Timestamp = BASE_DATE) -> pd.DataFrame:
    """Build a minimal forecast frame: one record per source per day."""
    rows = []
    for source_id, status_list in statuses.items():
        for offset, status in enumerate(status_list):
            rows.append(
                {
                    "source_id": source_id,
                    "valid_date": (start + pd.Timedelta(days=offset)).strftime("%Y-%m-%d"),
                    "status": status,
                }
            )
    return pd.DataFrame(rows)


def health_map(forecasts: pd.DataFrame) -> dict:
    return {h.source_id: h for h in compute_source_health(forecasts)}


def test_all_sources_healthy() -> None:
    statuses = {sid: ["ok"] * WINDOW for sid in SOURCE_DEFINITIONS}
    health = health_map(frame(statuses))
    assert {h.status for h in health.values()} == {"Healthy"}
    for h in health.values():
        assert h.records_in_window == WINDOW
        assert h.unavailable_ratio == 0.0
        assert h.delayed_ratio == 0.0
        assert "thresholds" in h.reason


def test_mostly_unavailable_source_is_unavailable() -> None:
    statuses = {
        "nwp_model_a": ["unavailable"] * 8 + ["ok"] * 6,
        "ensemble_mean": ["ok"] * WINDOW,
        "ai_local_v1": ["ok"] * WINDOW,
    }
    health = health_map(frame(statuses))
    assert health["nwp_model_a"].status == "Unavailable"
    assert health["nwp_model_a"].unavailable_ratio == round(8 / WINDOW, 4)
    assert health["ensemble_mean"].status == "Healthy"


def test_delayed_burst_is_delayed() -> None:
    statuses = {
        "nwp_model_a": ["delayed"] * 4 + ["ok"] * (WINDOW - 4),
        "ensemble_mean": ["ok"] * WINDOW,
        "ai_local_v1": ["ok"] * WINDOW,
    }
    health = health_map(frame(statuses))
    assert health["nwp_model_a"].status == "Delayed"
    assert health["nwp_model_a"].delayed_ratio == round(4 / WINDOW, 4)


def test_anomalous_burst_is_anomalous() -> None:
    statuses = {
        "nwp_model_a": ["ok"] * WINDOW,
        "ensemble_mean": ["ok"] * WINDOW,
        "ai_local_v1": ["anomalous"] * 3 + ["ok"] * (WINDOW - 3),
    }
    health = health_map(frame(statuses))
    assert health["ai_local_v1"].status == "Anomalous"
    assert health["ai_local_v1"].anomalous_ratio == round(3 / WINDOW, 4)


def test_missing_source_is_reported_not_silently_ignored() -> None:
    forecasts = frame({"nwp_model_a": ["ok"] * WINDOW})
    health = health_map(forecasts)
    assert set(health) == set(SOURCE_DEFINITIONS)
    assert health["ensemble_mean"].status == "Unavailable"
    assert "No records" in health["ensemble_mean"].reason


def test_empty_frame_reports_every_source_unavailable() -> None:
    health = health_map(pd.DataFrame(columns=["source_id", "valid_date", "status"]))
    assert {h.status for h in health.values()} == {"Unavailable"}


def test_records_outside_the_window_are_ignored() -> None:
    """Only the most recent `window_days` are considered for health."""
    recent = {"nwp_model_a": ["delayed"] * WINDOW, "ensemble_mean": ["ok"] * WINDOW,
              "ai_local_v1": ["ok"] * WINDOW}
    forecasts = frame(recent)
    # add very old anomalous records (older than the window)
    old_rows = pd.DataFrame(
        [
            {
                "source_id": "ai_local_v1",
                "valid_date": "2020-01-01",
                "status": "anomalous",
            }
        ]
    )
    forecasts = pd.concat([forecasts, old_rows], ignore_index=True)
    health = health_map(forecasts)
    assert health["ai_local_v1"].status == "Healthy"
    assert health["ai_local_v1"].records_in_window == WINDOW
