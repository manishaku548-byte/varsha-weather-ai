"""Phase 4 — model inference service for the AI source of GET /forecast.

Every forecast request asks this service for the AI-source value. The service
answers with exactly one of two *explicitly labelled* outcomes:

* ``trained_local_correction_model`` — a validated artifact exists for the
  requested lead horizon, the strictly-prior feature row is complete, and the
  pipeline produced ``ai_local_model_prediction_mm`` (clipped to the
  plausible rainfall range), or
* ``fallback_precomputed_ai_source`` — the precomputed ``ai_rain_mm`` CSV
  value is used instead, with a machine-readable ``reason``.

The switch is never silent: callers receive the label, a boolean
``model_inference_available``, the model version / report reference when a
model answered, and always a reason. Any unexpected inference error is
contained here and downgraded to the disclosed fallback — a forecast must
never crash because of the ML path.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..config import Settings, settings as default_settings
from .features import build_feature_row
from .model_store import load_artifact, report_path

MODEL_LABEL = "trained_local_correction_model"
FALLBACK_LABEL = "fallback_precomputed_ai_source"


def _clip(value: float, cfg: Settings) -> float:
    return max(0.0, min(float(value), cfg.max_plausible_rain_mm))


@dataclass
class AiSourceInference:
    """Result of asking the model for one (district, date, lead) AI value."""

    available: bool
    source_label: str
    prediction_mm: float | None
    model_version: str | None
    model_report_reference: str | None
    held_out_test_mae_mm: float | None
    feature_availability: str | None
    reason: str

    @property
    def model_inference_available(self) -> bool:
        return self.available

    def as_provenance(self) -> dict:
        """ML provenance block embedded in forecast/backtest responses."""
        return {
            "source_label": self.source_label,
            "model_inference_available": self.available,
            "model_version": self.model_version,
            "model_report_reference": self.model_report_reference,
            "held_out_test_mae_mm": self.held_out_test_mae_mm,
            "ai_local_model_prediction_mm": self.prediction_mm
            if self.available
            else None,
            "feature_availability": self.feature_availability,
            "reason": self.reason,
        }


def _fallback(
    reason: str,
    *,
    feature_availability: str | None = None,
) -> AiSourceInference:
    return AiSourceInference(
        available=False,
        source_label=FALLBACK_LABEL,
        prediction_mm=None,
        model_version=None,
        model_report_reference=None,
        held_out_test_mae_mm=None,
        feature_availability=feature_availability,
        reason=f"{reason} AI source falls back to '{FALLBACK_LABEL}'.",
    )


def predict_ai_local(
    ds,
    *,
    district_id: str,
    valid_date: str,
    lead_hours: int,
    cfg: Settings | None = None,
) -> AiSourceInference:
    """Return the AI-source value for one point — model first, fallback second."""
    s = cfg or default_settings

    # 0. explicit kill switch (tests / operations)
    if not s.ml_inference_enabled:
        return _fallback(
            "ML inference disabled by configuration (VARSHA_ML_INFERENCE=false)."
        )

    # 1. artifact must exist and validate for this exact lead horizon
    loaded, load_reason = load_artifact(int(lead_hours), s)
    if loaded is None:
        return _fallback(
            load_reason
            or f"No trained model artifact for {lead_hours}h lead. "
            "Train one via POST /model/train."
        )

    # 2. strictly-prior feature row must be complete enough to score
    try:
        row = build_feature_row(
            ds,
            district_id=district_id,
            valid_date=valid_date,
            lead_hours=int(lead_hours),
            cfg=s,
        )
    except Exception as exc:  # contained: never crash a forecast on ML errors
        return _fallback(
            f"Feature construction failed ({type(exc).__name__}: {exc})."
        )
    if not row.is_usable:
        return _fallback(
            f"Features unavailable for this point ({row.feature_skip_reason})",
            feature_availability=row.feature_availability,
        )

    # 3. predict (any failure downgrades to the disclosed fallback)
    try:
        import pandas as pd

        X = pd.DataFrame(
            [{column: row.features[column] for column in _feature_order()}]
        )
        for column in _numeric_order():
            X[column] = pd.to_numeric(X[column], errors="coerce")
        raw = loaded.pipeline.predict(X)[0]
        value = _clip(float(raw), s)
        if math.isnan(value):
            raise ValueError("model produced NaN")
    except Exception as exc:  # contained: forecast must not crash on ML errors
        return _fallback(
            f"Model inference failed ({type(exc).__name__}: {exc}).",
            feature_availability=row.feature_availability,
        )

    test_metrics = loaded.report.get("held_out_test_metrics") or {}
    return AiSourceInference(
        available=True,
        source_label=MODEL_LABEL,
        prediction_mm=value,
        model_version=loaded.model_version,
        model_report_reference=report_path(int(lead_hours), s).name,
        held_out_test_mae_mm=test_metrics.get("mae_mm"),
        feature_availability=row.feature_availability,
        reason=(
            f"ai_local_model_prediction_mm generated by trained model "
            f"{loaded.model_version} (selected: {loaded.selected_model}; held-out "
            f"test MAE {test_metrics.get('mae_mm')} mm; report "
            f"{report_path(int(lead_hours), s).name})."
        ),
    )


def _feature_order() -> list[str]:
    from .features import FEATURE_COLUMNS

    return list(FEATURE_COLUMNS)


def _numeric_order() -> list[str]:
    from .features import NUMERIC_FEATURES

    return list(NUMERIC_FEATURES)
