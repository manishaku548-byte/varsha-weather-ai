"""Tests for the audit/override SQLite storage created at startup."""

from __future__ import annotations

from sqlalchemy import inspect

from app import models
from app.database import engine, init_db


def test_audit_and_override_tables_exist() -> None:
    init_db()  # idempotent
    tables = set(inspect(engine).get_table_names())
    assert {"audit_logs", "override_decisions"} <= tables


def test_override_reason_column_is_not_nullable() -> None:
    columns = {c.name: c for c in models.OverrideDecision.__table__.columns}
    assert columns["reason"].nullable is False
    assert columns["original_risk_level"].nullable is False
    assert columns["overridden_risk_level"].nullable is False
    assert columns["original_output_json"].nullable is False


def test_audit_columns_match_srs_fields() -> None:
    columns = {c.name for c in models.AuditLog.__table__.columns}
    assert {
        "created_at",
        "actor",
        "role",
        "action",
        "district_id",
        "forecast_reference",
        "details",
    } <= columns
