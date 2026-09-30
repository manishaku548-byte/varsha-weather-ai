"""Forecast Intelligence Engine — Phase 2 orchestration.

Pipeline for one (district, date, lead_hours) point:

    1. range/availability checks
    2. source health as-of the selected date (window ends at the date, no leakage)
    3. bias correction per source from strictly prior records
    4. regime detection (heavy > heatwave > monsoon > normal)
    5. Dynamic Trust Engine -> normalized weights
    6. blending -> final rainfall (+ fallback mode)
    7. confidence / uncertainty
    8. rainfall risk guidance

Every number in a forecast response comes from this pipeline — nothing is
hardcoded. Inputs from the selected date's *observations* (the outcome) are
never used; skill, bias, health and regime context all stop strictly before
the selected valid_date.

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from ..config import SOURCE_DEFINITIONS, Settings, settings as default_settings
from ..schemas import SourceHealth
from .bias import BiasResult, compute_bias, prior_history
from .blend import BlendResult, blend_sources
from .confidence import ConfidenceResult, compute_confidence
from .model_inference import predict_ai_local
from .regime import RegimeResult, detect_regime
from .risk import RiskResult, assess_risk
from .source_health import compute_source_health
from .trust import TrustResult, TrustSource, compute_trust

#: Query alias -> source id for the failure-simulation parameter.
FAILURE_ALIASES: dict[str, str] = {
    "nwp": "nwp_model_a",
    "ensemble": "ensemble_mean",
    "ai": "ai_local_v1",
}
FAILURE_ALIAS_OF = {v: k for k, v in FAILURE_ALIASES.items()}

#: The AI source slot — replaced by the trained Phase 4 model when available.
AI_SOURCE_ID = "ai_local_v1"


class ForecastDateOutOfRangeError(ValueError):
    """Selected date lies outside the loaded replay dataset range."""


class ForecastUnavailableError(RuntimeError):
    """No source could produce a usable forecast for the selected point."""


@dataclass
class SourceForecast:
    """Everything the API reports about one source at the selected point."""

    source_id: str
    source_type: str
    display_name: str
    # --- record level -----------------------------------------------------------
    record_found: bool
    row_status: str
    quality_flag: str
    raw_forecast_mm: float | None
    value_usable: bool
    unusable_reason: str | None
    # --- ensemble fields --------------------------------------------------------
    ensemble_spread_mm: float | None = None
    ensemble_p10_mm: float | None = None
    ensemble_p90_mm: float | None = None
    # --- bias correction (A) ----------------------------------------------------
    bias: BiasResult | None = None
    corrected_forecast_mm: float | None = None
    # --- eligibility / trust (C) ------------------------------------------------
    eligible: bool = False
    ineligible_reason: str | None = None
    health: SourceHealth | None = None
    trust: TrustSource | None = None
    weight: float = 0.0
    # --- ML provenance (Phase 4 — populated for the AI source only) --------------
    model_inference_available: bool | None = None
    source_label: str | None = None
    model_version: str | None = None
    model_report_reference: str | None = None
    model_inference_reason: str | None = None


@dataclass
class ForecastResult:
    """Full forecast package produced by the engine."""

    district_id: str
    district_name: str
    valid_date: str
    lead_hours: int
    issue_time: str
    validity_start: str
    validity_end: str
    data_availability: dict = field(default_factory=dict)
    regime: RegimeResult | None = None
    source_health: list[SourceHealth] = field(default_factory=list)
    sources: list[SourceForecast] = field(default_factory=list)
    blend: BlendResult | None = None
    confidence: ConfidenceResult | None = None
    risk: RiskResult | None = None
    simulate_failure_source: str | None = None
    prior_context: dict = field(default_factory=dict)
    algorithm_version: str = ""
    config_version: str = ""
    #: Phase 4 ML provenance for the AI source (model vs disclosed fallback).
    ai_source_provenance: dict = field(default_factory=dict)


def _as_float(value) -> float | None:
    """Convert a cell to float, treating None/NaN/blank as missing."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _prior_context(
    ds,
    district_id: str,
    valid_date: str,
    cfg: Settings,
) -> dict:
    """Observational context strictly before the selected date.

    * trailing_3day_mm : sum of usable 24h observations in [date-3, date-1]
    * temp_c / humidity: latest usable observation before the date (walk back
      up to 3 days when the nearest row is missing)
    """
    as_of = pd.to_datetime(valid_date)
    obs = ds.observations[
        (ds.observations["district_id"].astype(str) == district_id)
        & (pd.to_numeric(ds.observations["lead_hours"], errors="coerce") == 24)
    ].copy()
    obs["_date"] = pd.to_datetime(obs["valid_date"], errors="coerce")
    prior = obs[obs["_date"] < as_of].sort_values("_date", ascending=False)

    trailing_mm: float | None = None
    window = prior[prior["_date"] >= as_of - pd.Timedelta(days=3)]
    if len(window):
        values = pd.to_numeric(window["observed_rain_mm"], errors="coerce")
        usable = values[(values >= 0) & (values <= cfg.max_plausible_rain_mm)]
        if len(usable):
            trailing_mm = float(usable.sum())

    temp_c: float | None = None
    humidity_pct: float | None = None
    for row in prior.head(3).to_dict("records"):
        if temp_c is None:
            temp_c = _as_float(row.get("observed_temp_c"))
        if humidity_pct is None:
            humidity_pct = _as_float(row.get("observed_humidity_pct"))
        if temp_c is not None and humidity_pct is not None:
            break

    return {
        "trailing_3day_mm": trailing_mm,
        "temp_c": temp_c,
        "humidity_pct": humidity_pct,
        "prior_observation_days": int(len(prior)),
        "context_note": (
            "Temperature, humidity and trailing rainfall are taken from "
            f"observations strictly earlier than {valid_date}."
        ),
    }


def run_forecast(
    ds,
    *,
    district_id: str,
    district_name: str,
    valid_date: str,
    lead_hours: int,
    simulate_failure_source: str | None = None,
    cfg: Settings | None = None,
) -> ForecastResult:
    """Compute the full forecast package for one point (raises on failure)."""
    s = cfg or default_settings

    # --- 1. range check --------------------------------------------------------
    fc_dates = pd.to_datetime(ds.forecasts["valid_date"], errors="coerce")
    first, last = fc_dates.min(), fc_dates.max()
    selected = pd.to_datetime(valid_date)
    if pd.isna(selected) or selected < first or selected > last:
        raise ForecastDateOutOfRangeError(
            f"Date '{valid_date}' is outside the loaded dataset range "
            f"{first.date()} to {last.date()}."
        )
    valid_date = selected.strftime("%Y-%m-%d")  # canonical form for downstream stages

    failed_source_id: str | None = None
    if simulate_failure_source:
        alias = str(simulate_failure_source).lower()
        if alias not in FAILURE_ALIASES:
            raise ValueError(
                f"Unknown source '{simulate_failure_source}'. "
                f"Use one of: {', '.join(sorted(FAILURE_ALIASES))}."
            )
        failed_source_id = FAILURE_ALIASES[alias]

    # --- rows at the selected point -------------------------------------------
    point = ds.forecasts[
        (ds.forecasts["district_id"].astype(str) == district_id)
        & (pd.to_numeric(ds.forecasts["lead_hours"], errors="coerce") == lead_hours)
        & (pd.to_datetime(ds.forecasts["valid_date"], errors="coerce") == selected)
    ]
    rows_by_source = {str(r["source_id"]): r for r in point.to_dict("records")}

    # --- 2. source health as-of the selected date (no future leakage) ----------
    health_list = compute_source_health(ds.forecasts, cfg=s, as_of_date=valid_date)
    health_by_id = {h.source_id: h for h in health_list}

    # --- 2b. Phase 4 AI source: trained model first, disclosed fallback second --
    ai_inference = predict_ai_local(
        ds,
        district_id=district_id,
        valid_date=valid_date,
        lead_hours=lead_hours,
        cfg=s,
    )

    # --- 3. per-source records, bias correction --------------------------------
    sources: list[SourceForecast] = []
    for source_id, meta in SOURCE_DEFINITIONS.items():
        row = rows_by_source.get(source_id)
        model_drives = source_id == AI_SOURCE_ID and ai_inference.available
        record_found = row is not None
        row_status = str(row.get("status")) if row is not None else "missing"
        quality_flag = str(row.get("quality_flag")) if row is not None else "missing"
        raw_value = _as_float(row.get("forecast_rain_mm")) if row is not None else None

        value_usable = True
        unusable_reason: str | None = None
        if model_drives:
            # Trained local correction model supplies the AI-source value.
            # The substitution is never silent: row_status/quality_flag and the
            # provenance fields record exactly what happened.
            record_found = True
            row_status = "model_inference"
            quality_flag = "model_prediction"
            raw_value = ai_inference.prediction_mm
            if raw_value is None or not (0.0 <= raw_value <= s.max_plausible_rain_mm):
                value_usable = False
                unusable_reason = (
                    "Model prediction failed the plausibility check."
                )
        elif row is None:
            value_usable = False
            unusable_reason = (
                "No forecast record for this district, date and lead_hours."
            )
        elif row_status == "unavailable":
            value_usable = False
            unusable_reason = "Record marked 'unavailable' by the source."
        elif raw_value is None:
            value_usable = False
            unusable_reason = "Forecast value is missing."
        elif not (0.0 <= raw_value <= s.max_plausible_rain_mm) or row_status == "anomalous":
            value_usable = False
            unusable_reason = (
                f"Implausible value ({raw_value} mm) quarantined by data-quality "
                f"checks (status={row_status})."
            )

        if model_drives and value_usable and raw_value is not None:
            # No mean-bias correction is stacked on top of the model output —
            # the trained model IS the learned correction (see its report).
            bias = BiasResult(
                source_id=source_id,
                raw_forecast_mm=float(raw_value),
                bias_mm=None,
                corrected_forecast_mm=float(raw_value),
                historical_record_count=0,
                bias_available=False,
                reason=(
                    "The AI-source value is produced by the trained local "
                    "correction model; no additional source-level bias "
                    "correction is applied to model output."
                ),
                method="model_output_passthrough",
            )
            corrected = float(raw_value)
        else:
            bias = compute_bias(
                ds.forecasts,
                ds.observations,
                district_id=district_id,
                lead_hours=lead_hours,
                source_id=source_id,
                as_of_date=valid_date,
                raw_forecast_mm=raw_value if value_usable else None,
                cfg=s,
            )
            corrected = bias.corrected_forecast_mm if value_usable else None
        if corrected is not None and (math.isnan(corrected) or math.isinf(corrected)):
            corrected = None

        spread = p10 = p90 = None
        if row is not None:
            spread = _as_float(row.get("ensemble_spread_mm"))
            p10 = _as_float(row.get("ensemble_p10_mm"))
            p90 = _as_float(row.get("ensemble_p90_mm"))

        health = health_by_id[source_id]
        eligible = value_usable and source_id != failed_source_id and health.status != "Unavailable"
        ineligible_reason: str | None = None
        if source_id == failed_source_id:
            ineligible_reason = (
                f"Simulated failure of '{FAILURE_ALIAS_OF[source_id]}' — source "
                "excluded from this forecast (trust 0.0, weight 0.0)."
            )
        elif not value_usable:
            ineligible_reason = unusable_reason
        elif health.status == "Unavailable":
            ineligible_reason = (
                f"Source health is Unavailable over the window ending {valid_date} "
                "(health score 0.0)."
            )

        ml_fields = (
            {
                "model_inference_available": ai_inference.available,
                "source_label": ai_inference.source_label,
                "model_version": ai_inference.model_version,
                "model_report_reference": ai_inference.model_report_reference,
                "model_inference_reason": ai_inference.reason,
            }
            if source_id == AI_SOURCE_ID
            else {}
        )
        sources.append(
            SourceForecast(
                source_id=source_id,
                source_type=str(meta["source_type"]),
                display_name=str(meta["display_name"]),
                record_found=record_found,
                row_status=row_status,
                quality_flag=quality_flag,
                raw_forecast_mm=raw_value,
                value_usable=value_usable,
                unusable_reason=unusable_reason,
                ensemble_spread_mm=spread,
                ensemble_p10_mm=p10,
                ensemble_p90_mm=p90,
                bias=bias,
                corrected_forecast_mm=corrected,
                eligible=eligible,
                ineligible_reason=ineligible_reason,
                health=health,
                **ml_fields,
            )
        )

    by_id = {sf.source_id: sf for sf in sources}

    # --- 4. prior observation context + regime ---------------------------------
    prior_ctx = _prior_context(ds, district_id, valid_date, s)
    ensemble_src = by_id.get("ensemble_mean")
    # Regime uses the RAW ensemble mean (per SRS FR-REG-02) plus the corrected
    # blend inputs (the ensemble's own corrected value is included there too).
    ensemble_raw = (
        ensemble_src.raw_forecast_mm
        if ensemble_src is not None and ensemble_src.value_usable and ensemble_src.source_id != failed_source_id
        else None
    )
    corrected_inputs = [
        sf.corrected_forecast_mm
        for sf in sources
        if sf.value_usable
        and sf.source_id != failed_source_id
        and sf.corrected_forecast_mm is not None
    ]
    regime = detect_regime(
        ensemble_mm=ensemble_raw,
        corrected_values=corrected_inputs,
        trailing_3day_mm=prior_ctx["trailing_3day_mm"],
        temp_c=prior_ctx["temp_c"],
        humidity_pct=prior_ctx["humidity_pct"],
        lead_hours=lead_hours,
        cfg=s,
    )

    # --- 5. trust engine --------------------------------------------------------
    hist_mae: dict[str, float | None] = {}
    hist_count: dict[str, int] = {}
    recent_mae: dict[str, float | None] = {}
    recent_count: dict[str, int] = {}
    for source_id in SOURCE_DEFINITIONS:
        history = prior_history(
            ds.forecasts,
            ds.observations,
            district_id=district_id,
            lead_hours=lead_hours,
            source_id=source_id,
            as_of_date=valid_date,
            cfg=s,
        )
        recent = history.recent(s.recent_skill_records)
        hist_mae[source_id] = history.mae()
        hist_count[source_id] = history.count
        recent_mae[source_id] = recent.mae()
        recent_count[source_id] = recent.count

    trust: TrustResult = compute_trust(
        eligible={sid: sf.eligible for sid, sf in by_id.items()},
        ineligible_reasons={
            sid: sf.ineligible_reason or ""
            for sid, sf in by_id.items()
            if sf.ineligible_reason
        },
        health_status={sid: sf.health.status for sid, sf in by_id.items()},
        corrected_mm={sid: sf.corrected_forecast_mm for sid, sf in by_id.items()},
        historical_mae_mm=hist_mae,
        historical_counts=hist_count,
        recent_mae_mm=recent_mae,
        recent_counts=recent_count,
        regime_label=regime.label,
        lead_hours=lead_hours,
        cfg=s,
    )
    for record in trust.sources:
        target = by_id[record.source_id]
        target.trust = record
        target.weight = record.weight

    if trust.eligible_count == 0 or trust.total_trust <= 0.0:
        details = "; ".join(
            f"{sf.display_name}: {sf.ineligible_reason or 'no reason recorded'}"
            for sf in sources
        )
        raise ForecastUnavailableError(
            "Forecast unavailable — no usable source for "
            f"{district_name} on {valid_date} at {lead_hours}h lead. {details}"
        )

    # --- 6. blend ----------------------------------------------------------------
    blend = blend_sources(
        {sid: sf.corrected_forecast_mm for sid, sf in by_id.items()},
        trust.weights,
        {sid: sf.display_name for sid, sf in by_id.items()},
    )

    # --- 7. confidence / uncertainty ---------------------------------------------
    eligible_ids = [sid for sid, sf in by_id.items() if sf.eligible]
    weight_sum = sum(trust.weights.get(sid, 0.0) for sid in eligible_ids) or 1.0
    weighted_skill = sum(
        trust.weights.get(sid, 0.0) * (by_id[sid].trust.historical_skill if by_id[sid].trust else 0.0)
        for sid in eligible_ids
    ) / weight_sum
    weighted_health = sum(
        trust.weights.get(sid, 0.0) * (by_id[sid].trust.health_score if by_id[sid].trust else 0.0)
        for sid in eligible_ids
    ) / weight_sum
    weighted_agreement = sum(
        trust.weights.get(sid, 0.0) * (by_id[sid].trust.agreement if by_id[sid].trust else 0.0)
        for sid in eligible_ids
    ) / weight_sum
    disagreement = math.sqrt(
        sum(
            trust.weights.get(sid, 0.0)
            * ((by_id[sid].corrected_forecast_mm or 0.0) - blend.final_rainfall_mm) ** 2
            for sid in eligible_ids
        )
    )
    ensemble_spread = (
        ensemble_src.ensemble_spread_mm
        if ensemble_src is not None
        and ensemble_src.value_usable
        and ensemble_src.source_id != failed_source_id
        else None
    )
    confidence = compute_confidence(
        available_count=blend.available_count,
        weighted_historical_skill=weighted_skill,
        weighted_health=weighted_health,
        weighted_agreement=weighted_agreement,
        ensemble_spread_mm=ensemble_spread,
        disagreement_mm=disagreement,
        blend_mm=blend.final_rainfall_mm,
        fallback_mode=blend.fallback_mode,
        cfg=s,
    )

    # --- 8. risk ------------------------------------------------------------------
    risk = assess_risk(
        rainfall_mm=blend.final_rainfall_mm,
        regime_label=regime.label,
        confidence_score=confidence.score,
        confidence_label=confidence.label,
        valid_date=valid_date,
        lead_hours=lead_hours,
        cfg=s,
    )

    # --- availability metadata -------------------------------------------------------
    issue_dt = selected - timedelta(hours=lead_hours)
    data_availability = {
        "dataset_first_valid_date": str(first.date()),
        "dataset_last_valid_date": str(last.date()),
        "records_found_for_point": int(len(point)),
        "available_sources": [sf.source_id for sf in sources if sf.eligible],
        "unavailable_sources": [sf.source_id for sf in sources if not sf.eligible],
        "data_available": bool(blend.available_count),
    }

    return ForecastResult(
        district_id=district_id,
        district_name=district_name,
        valid_date=valid_date,
        lead_hours=lead_hours,
        issue_time=issue_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        validity_start=(selected - timedelta(hours=lead_hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        validity_end=selected.strftime("%Y-%m-%dT%H:%M:%SZ"),
        data_availability=data_availability,
        regime=regime,
        source_health=health_list,
        sources=sources,
        blend=blend,
        confidence=confidence,
        risk=risk,
        simulate_failure_source=simulate_failure_source,
        prior_context=prior_ctx,
        algorithm_version=s.algorithm_version,
        config_version=s.config_version,
        ai_source_provenance=ai_inference.as_provenance(),
    )
