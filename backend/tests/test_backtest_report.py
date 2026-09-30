"""Phase 3 report tests: CSV export, JSON metadata, report endpoint, safe paths.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from app.config import settings
from app.services.metrics import METHOD_KEYS
from app.services.reporting import (
    CSV_COLUMNS,
    ReportPathError,
    report_paths,
    report_stem,
    slugify_district,
)

#: Exactly the columns required by the Phase 3 CSV contract.
REQUIRED_CSV_COLUMNS = [
    "date",
    "district",
    "lead_hours",
    "actual_rain_mm",
    "nwp_prediction_mm",
    "ensemble_prediction_mm",
    "ai_prediction_mm",
    "equal_weight_prediction_mm",
    "varsha_prediction_mm",
    "regime",
    "nwp_weight",
    "ensemble_weight",
    "ai_weight",
    "confidence_score",
    "confidence_label",
    "risk_level",
    "fallback_mode",
    "included_in_evaluation",
    "skip_reason",
    "nwp_source_health",
    "ensemble_source_health",
    "ai_source_health",
    "data_mode",
    "disclaimer",
]

BASE = {
    "district": "Prayagraj",
    "lead_hours": 24,
    "start_date": "2025-07-21",
    "end_date": "2025-07-25",
}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


# --------------------------------------------------------------------------------------
# G6. CSV export
# --------------------------------------------------------------------------------------
def test_csv_report_created_with_required_columns(client):
    resp = client.get("/backtest", params=BASE)
    assert resp.status_code == 200
    files = resp.json()["report_files"]

    assert files["csv"] == "backtest_prayagraj_24h_2025-07-21_2025-07-25.csv"
    assert re.fullmatch(
        r"backtest_[a-z0-9_]+_24h_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}\.csv",
        files["csv"],
    )
    csv_path = Path(settings.reports_dir) / files["csv"]
    assert csv_path.exists()

    fieldnames, rows = _read_csv(csv_path)
    for column in REQUIRED_CSV_COLUMNS:
        assert column in fieldnames, f"missing CSV column: {column}"
    # CSV_COLUMNS is the writer contract and includes the required ones in order
    for column in REQUIRED_CSV_COLUMNS:
        assert CSV_COLUMNS.index(column) == fieldnames.index(column)

    assert len(rows) == 5  # one row per requested date
    assert rows[0]["date"] == "2025-07-21"
    assert rows[0]["district"] == "Prayagraj"
    assert rows[0]["included_in_evaluation"] == "true"
    assert rows[0]["skip_reason"] == ""
    assert rows[0]["varsha_prediction_mm"] != ""
    assert rows[0]["actual_rain_mm"] != ""
    assert rows[0]["regime"] != ""
    assert rows[0]["data_mode"] == settings.data_mode
    assert rows[0]["disclaimer"] == settings.backtest_disclaimer
    assert float(rows[0]["nwp_weight"]) + float(rows[0]["ensemble_weight"]) + float(
        rows[0]["ai_weight"]
    ) == pytest.approx(1.0, abs=1e-6)


def test_csv_contains_skipped_rows_with_reasons(client):
    resp = client.get(
        "/backtest",
        params={
            **BASE,
            "start_date": "2025-06-01",
            "end_date": "2025-06-16",
        },
    )
    assert resp.status_code == 200
    files = resp.json()["report_files"]
    csv_path = Path(settings.reports_dir) / files["csv"]
    assert csv_path.exists()

    _, rows = _read_csv(csv_path)
    assert len(rows) == 16  # every requested date is present

    skipped = [row for row in rows if row["included_in_evaluation"] == "false"]
    included = [row for row in rows if row["included_in_evaluation"] == "true"]
    assert len(skipped) == 14
    assert len(included) == 2
    assert all(row["skip_reason"] == "insufficient_history" for row in skipped)
    assert all(row["varsha_prediction_mm"] == "" for row in skipped)
    assert all(row["skip_reason"] == "" for row in included)

    summary = resp.json()["evaluation_summary"]
    assert summary["evaluated_dates"] == 2
    assert summary["skipped_dates"] == 14
    assert summary["skipped_reason_counts"]["insufficient_history"] == 14


# --------------------------------------------------------------------------------------
# G7. JSON report metadata
# --------------------------------------------------------------------------------------
def test_json_report_contains_required_metadata(client):
    resp = client.get("/backtest", params=BASE)
    assert resp.status_code == 200
    files = resp.json()["report_files"]

    json_path = Path(settings.reports_dir) / files["json"]
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    # labels + versions
    assert payload["disclaimer"] == settings.backtest_disclaimer
    assert "Development/Testing Only" in payload["disclaimer"]
    assert payload["data_mode"] == settings.data_mode
    assert payload["report_type"] == "backtest"
    assert payload["generated_at"].endswith("Z")
    assert payload["algorithm_version"] == settings.algorithm_version
    assert payload["config_version"] == settings.config_version

    # request + summary
    assert payload["request"]["district_id"] == "prayagraj"
    assert payload["request"]["start_date"] == "2025-07-21"
    assert payload["request"]["end_date"] == "2025-07-25"
    assert payload["row_counts"] == {"total": 5, "evaluated": 5, "skipped": 0}
    assert payload["evaluation_summary"]["evaluated_dates"] == 5

    # metrics table + comparisons
    assert set(payload["methods"]) == set(METHOD_KEYS)
    assert len(payload["metrics_table"]) == 5
    nwp_row = next(r for r in payload["metrics_table"] if r["method"] == "nwp")
    assert isinstance(nwp_row["mae_mm"], float)
    comp = payload["comparison_summary"]
    assert "best_method_by_metric" in comp
    assert comp["varsha_vs_equal_weight_mae_delta_mm"] is not None
    assert comp["varsha_vs_best_single_source_mae_delta_mm"] is not None

    # file cross-reference + limitations/caveats
    assert payload["files"]["csv"] == files["csv"]
    assert len(payload["limitations"]) >= 5
    assert any("Development/Testing Only" in lim for lim in payload["limitations"])
    assert any("not an official-warning verification" in lim for lim in payload["limitations"])
    assert any("precision, recall and F1 must be read together" in lim
               for lim in payload["limitations"])


def test_report_json_keeps_raw_precision_while_api_rounds(client):
    resp = client.get("/backtest", params=BASE)
    files = resp.json()["report_files"]

    payload = json.loads(
        (Path(settings.reports_dir) / files["json"]).read_text(encoding="utf-8")
    )
    raw = payload["methods"]["nwp"]["regression_metrics"]["mae_mm"]
    displayed = resp.json()["methods"]["nwp"]["regression_metrics"]["mae_mm"]
    assert raw == pytest.approx(displayed, abs=5e-5)
    # raw report value is the engine value, not a display-rounded copy
    assert isinstance(raw, float)


# --------------------------------------------------------------------------------------
# G8. Report endpoint
# --------------------------------------------------------------------------------------
def test_report_endpoint_json_stored_after_backtest(client):
    assert client.get("/backtest", params=BASE).status_code == 200

    resp = client.get("/backtest/report", params={**BASE, "format": "json"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_type"] == "backtest"
    assert body["report_source"] == "stored"
    assert body["disclaimer"] == settings.backtest_disclaimer
    assert body["data_mode"] == settings.data_mode
    assert set(body["methods"]) == set(METHOD_KEYS)
    assert body["comparison_summary"]["best_method_by_metric"] is not None
    assert len(body["limitations"]) >= 5
    assert body["files"]["csv"].startswith("backtest_prayagraj_24h_")


def test_report_endpoint_generates_when_missing(client):
    params = {**BASE, "start_date": "2025-07-26", "end_date": "2025-07-28"}
    # Remove any leftovers from earlier runs so "missing" is guaranteed.
    csv_path, json_path = report_paths("prayagraj", 24, "2025-07-26", "2025-07-28")
    csv_path.unlink(missing_ok=True)
    json_path.unlink(missing_ok=True)

    resp = client.get("/backtest/report", params={**params, "format": "json"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_source"] == "generated"
    # generating writes both files for later "stored" reads
    assert (Path(settings.reports_dir) / body["files"]["csv"]).exists()

    again = client.get("/backtest/report", params={**params, "format": "json"})
    assert again.json()["report_source"] == "stored"


def test_report_endpoint_csv_download(client):
    assert client.get("/backtest", params=BASE).status_code == 200

    resp = client.get("/backtest/report", params={**BASE, "format": "csv"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert (
        'attachment; filename="backtest_prayagraj_24h_2025-07-21_2025-07-25.csv"'
        in resp.headers["content-disposition"]
    )
    text = resp.content.decode("utf-8")
    lines = text.strip().splitlines()
    assert lines[0].split(",")[:3] == ["date", "district", "lead_hours"]
    assert len(lines) == 6  # header + 5 evaluated dates
    assert "Prayagraj" in text
    assert settings.backtest_disclaimer in text


def test_report_endpoint_validation_errors(client):
    base = dict(BASE)

    bad_format = client.get("/backtest/report", params={**base, "format": "xml"})
    assert bad_format.status_code == 422

    unknown = client.get(
        "/backtest/report", params={**base, "district": "Nowhere", "format": "json"}
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["error"] == "unknown_district"

    reversed_range = client.get(
        "/backtest/report",
        params={**base, "start_date": "2025-08-01", "end_date": "2025-07-01"},
    )
    assert reversed_range.status_code == 422
    assert reversed_range.json()["detail"]["error"] == "invalid_date_range"

    bad_lead = client.get("/backtest/report", params={**base, "lead_hours": 12})
    assert bad_lead.status_code == 422
    assert bad_lead.json()["detail"]["error"] == "invalid_lead_hours"


def test_report_regenerates_when_parameters_do_not_match(client):
    """Same district/range but a different threshold must not reuse the old file."""
    first = client.get("/backtest", params=BASE)
    assert first.status_code == 200

    resp = client.get(
        "/backtest/report", params={**BASE, "heavy_rain_threshold_mm": 100, "format": "json"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_source"] == "generated"
    assert body["request"]["heavy_rain_threshold_mm"] == 100
    assert body["event_threshold"]["configured_threshold_mm"] == 100


# --------------------------------------------------------------------------------------
# Path safety (never allow directory traversal)
# --------------------------------------------------------------------------------------
def test_slugify_and_stem_are_filesystem_safe():
    assert slugify_district("kanpur-nagar") == "kanpur_nagar"
    for hostile in ("../etc", "..\\..\\windows", "a/b", "prc/../../evil"):
        stem = report_stem(hostile, 24, "2025-07-01", "2025-07-05")
        assert "/" not in stem and "\\" not in stem and ".." not in stem
        assert re.fullmatch(
            r"backtest_[a-z0-9_]+_24h_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}", stem
        )


def test_report_paths_stay_inside_reports_dir():
    csv_path, json_path = report_paths("prayagraj", 24, "2025-07-01", "2025-07-05")
    resolved_dir = Path(settings.reports_dir).resolve()
    assert csv_path.parent == resolved_dir
    assert json_path.parent == resolved_dir
    assert csv_path.name == "backtest_prayagraj_24h_2025-07-01_2025-07-05.csv"
    assert json_path.name == "backtest_prayagraj_24h_2025-07-01_2025-07-05.json"


def test_unsafe_report_stem_is_rejected():
    with pytest.raises(ReportPathError):
        report_stem("prayagraj", 12345, "2025-07-01", "2025-07-05")  # bad lead
    with pytest.raises(ReportPathError):
        report_stem("prayagraj", 24, "2025-7-1", "2025-07-05")  # malformed date
