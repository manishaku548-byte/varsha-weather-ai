"""Phase 2 forecast endpoints:

* ``GET  /forecast``                            — full forecast package
* ``GET  /forecast/explain``                    — plain-language explanation
* ``POST /forecast/simulate-source-failure``    — normal vs degraded comparison

All values are computed by the Forecast Intelligence Engine from the stored
replay dataset. Nothing here is hardcoded; display rounding happens only in
this layer (the engine keeps full precision).

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import SOURCE_DEFINITIONS, settings
from ..schemas_forecast import (
    BlendContribution,
    BlendInfo,
    ConfidenceInfo,
    DistrictRef,
    ExplainSourceLine,
    FailureSourceAlias,
    ForecastExplainResponse,
    ForecastResponse,
    ForecastSource,
    ForecastSummary,
    RegimeInfo,
    RiskInfo,
    SimulateFailureResponse,
    TrustComponent,
    WeightChange,
)
from ..services.dataset import (
    available_district_names,
    get_dataset,
    resolve_district,
)
from ..services.forecast_engine import (
    FAILURE_ALIASES,
    ForecastDateOutOfRangeError,
    ForecastUnavailableError,
    ForecastResult,
    SourceForecast,
    run_forecast,
)

router = APIRouter()


# --------------------------------------------------------------------------------------
# Display-rounding helpers (engine stays full precision; round only for display)
# --------------------------------------------------------------------------------------
def _mm(value: float | None, ndigits: int = 2) -> float | None:
    if value is None:
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, ndigits)


def _display_weights(weights: dict[str, float], ndigits: int = 4) -> dict[str, float]:
    """Round weights for display and fix the residual so they sum to exactly 1."""
    if not any(w > 0 for w in weights.values()):
        return {k: round(float(v), ndigits) for k, v in weights.items()}
    rounded = {k: round(float(v), ndigits) for k, v in weights.items()}
    residual = round(1.0 - sum(rounded.values()), ndigits)
    if residual != 0:
        largest = max(rounded, key=lambda k: rounded[k])
        rounded[largest] = round(rounded[largest] + residual, ndigits)
    return rounded


def _district_name(ds, district_id: str) -> str:
    rows = ds.districts[ds.districts["district_id"].astype(str) == district_id]
    if len(rows):
        return str(rows.iloc[0]["district_name"])
    return district_id


def _resolve(ds, query: str) -> tuple[str, str]:
    try:
        district_id = resolve_district(ds, query)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "unknown_district",
                "message": f"Unknown district '{query}'.",
                "available_districts": available_district_names(ds),
            },
        ) from None
    assert district_id is not None
    return district_id, _district_name(ds, district_id)


def _run(ds, *, district_id: str, district_name: str, valid_date: str,
         lead_hours: int, simulate_failure_source: str | None) -> ForecastResult:
    try:
        return run_forecast(
            ds,
            district_id=district_id,
            district_name=district_name,
            valid_date=valid_date,
            lead_hours=lead_hours,
            simulate_failure_source=simulate_failure_source,
        )
    except ForecastDateOutOfRangeError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "date_out_of_range",
                "message": str(exc),
                "hint": "Use a YYYY-MM-DD date inside the loaded dataset range.",
            },
        ) from None
    except ForecastUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "forecast_unavailable",
                "message": str(exc),
                "hint": "No usable source remained for this point; check source "
                "records or disable the failure simulation.",
                "disclaimer": settings.decision_support_disclaimer,
            },
        ) from None


def _validate_lead(lead_hours: int) -> int:
    """Query parameters arrive as strings; enforce the allowed horizons here."""
    if int(lead_hours) not in (6, 24, 72):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_lead_hours",
                "message": "lead_hours must be one of 6, 24 or 72.",
                "allowed": [6, 24, 72],
            },
        )
    return int(lead_hours)


# --------------------------------------------------------------------------------------
# Response assembly
# --------------------------------------------------------------------------------------
def _bias_metadata(source: SourceForecast):
    bias = source.bias
    if bias is None:  # pragma: no cover - engine always sets it
        raise AssertionError("missing bias result")
    return {
        "source_id": bias.source_id,
        "method": bias.method,
        "bias_available": bias.bias_available,
        "bias_mm": _mm(bias.bias_mm),
        "raw_forecast_mm": _mm(source.raw_forecast_mm),
        "corrected_forecast_mm": _mm(source.corrected_forecast_mm),
        "historical_record_count": bias.historical_record_count,
        "reason": bias.reason,
    }


def _trust_component(source: SourceForecast) -> TrustComponent:
    trust = source.trust
    if trust is None:  # pragma: no cover - engine always sets it
        raise AssertionError("missing trust result")
    return TrustComponent(
        source_id=trust.source_id,
        source_type=trust.source_type,
        display_name=trust.display_name,
        eligible=trust.eligible,
        health_status=trust.health_status,
        health_score=trust.health_score,
        historical_mae_mm=_mm(trust.historical_mae_mm),
        historical_record_count=trust.historical_record_count,
        historical_skill=round(trust.historical_skill, 4),
        recent_mae_mm=_mm(trust.recent_mae_mm),
        recent_record_count=trust.recent_record_count,
        recent_skill=round(trust.recent_skill, 4),
        agreement=round(trust.agreement, 4),
        context_factor=round(trust.context_factor, 4),
        trust_score=round(trust.trust_score, 4),
        weight=round(float(source.weight), 4),
        reason=trust.reason,
        ineligible_reason=trust.ineligible_reason,
    )


def _forecast_source(source: SourceForecast) -> ForecastSource:
    ensemble = None
    if any(v is not None for v in (
        source.ensemble_spread_mm, source.ensemble_p10_mm, source.ensemble_p90_mm
    )):
        ensemble = {
            "ensemble_spread_mm": _mm(source.ensemble_spread_mm),
            "ensemble_p10_mm": _mm(source.ensemble_p10_mm),
            "ensemble_p90_mm": _mm(source.ensemble_p90_mm),
        }
    return ForecastSource(
        source_id=source.source_id,
        source_type=source.source_type,
        display_name=source.display_name,
        available=source.eligible,
        record_found=source.record_found,
        status=source.row_status,
        quality_flag=source.quality_flag,
        raw_forecast_mm=_mm(source.raw_forecast_mm),
        corrected_forecast_mm=_mm(source.corrected_forecast_mm),
        bias=_bias_metadata(source),  # type: ignore[arg-type]
        trust=_trust_component(source),
        weight=round(float(source.weight), 4),
        ensemble=ensemble,
        unavailable_reason=None if source.eligible else source.ineligible_reason,
        model_inference_available=source.model_inference_available,
        source_label=source.source_label,
        model_version=source.model_version,
        model_report_reference=source.model_report_reference,
        model_inference_reason=source.model_inference_reason,
    )


def _build_response(result: ForecastResult) -> ForecastResponse:
    assert result.regime is not None
    assert result.blend is not None
    assert result.confidence is not None
    assert result.risk is not None

    weights_display = _display_weights(
        {sf.source_id: sf.weight for sf in result.sources}
    )
    blend = result.blend
    confidence = result.confidence
    risk = result.risk

    return ForecastResponse(
        disclaimer=settings.decision_support_disclaimer,
        data_mode=settings.data_mode,
        data_label=settings.synthetic_data_label,
        algorithm_version=result.algorithm_version,
        config_version=result.config_version,
        district=DistrictRef(
            district_id=result.district_id, district_name=result.district_name
        ),
        valid_date=result.valid_date,
        lead_hours=result.lead_hours,  # type: ignore[arg-type]
        issue_time=result.issue_time,
        validity_start=result.validity_start,
        validity_end=result.validity_end,
        simulate_failure_source=result.simulate_failure_source,  # type: ignore[arg-type]
        data_availability=result.data_availability,
        prior_context=result.prior_context,
        weather_regime=RegimeInfo(
            label=result.regime.label,  # type: ignore[arg-type]
            confidence=round(result.regime.confidence, 3),
            triggered_rules=result.regime.triggered_rules,
            thresholds_used=result.regime.thresholds_used,
            reason=result.regime.reason,
            rule_version=result.regime.rule_version,
        ),
        source_health=result.source_health,
        sources=[_forecast_source(sf) for sf in result.sources],
        blend=BlendInfo(
            final_rainfall_mm=_mm(blend.final_rainfall_mm),
            formula="final_rainfall_mm = sum(weight x corrected_forecast)",
            fallback_mode=blend.fallback_mode,  # type: ignore[arg-type]
            fallback_note=blend.fallback_note,
            available_source_count=blend.available_count,
            contributions=[
                BlendContribution(
                    source_id=c["source_id"],
                    weight=round(weights_display.get(c["source_id"], c["weight"]), 4),
                    corrected_mm=_mm(c["corrected_mm"]),
                    contribution_mm=_mm(c["contribution_mm"]),
                )
                for c in blend.contributions
            ],
            unavailable_sources=blend.unavailable_sources,
        ),
        fallback_mode=blend.fallback_mode,  # type: ignore[arg-type]
        confidence=ConfidenceInfo(
            score=confidence.score,
            label=confidence.label,  # type: ignore[arg-type]
            factors=confidence.factors,
            explanation=confidence.explanation,
            uncertainty_lower_mm=_mm(confidence.uncertainty_lower_mm),
            uncertainty_upper_mm=_mm(confidence.uncertainty_upper_mm),
            uncertainty_half_width_mm=_mm(confidence.uncertainty_half_width_mm),
            uncertainty_basis=confidence.uncertainty_basis,
        ),
        risk=RiskInfo(
            event_type=risk.event_type,
            risk_level=risk.risk_level,  # type: ignore[arg-type]
            predicted_rainfall_mm=_mm(risk.predicted_rainfall_mm),
            validity_start=risk.validity_start,
            validity_end=risk.validity_end,
            confidence_score=round(risk.confidence_score, 1),
            confidence_label=risk.confidence_label,
            regime=risk.regime,
            escalated=risk.escalated,
            reasons=risk.reasons,
            preparedness_actions=risk.preparedness_actions,
            thresholds_used=risk.thresholds_used,
            disclaimer=risk.disclaimer,
        ),
        ml_model=result.ai_source_provenance,
    )


def _explain_lines(result: ForecastResult) -> list[ExplainSourceLine]:
    lines = []
    for sf in result.sources:
        lines.append(
            ExplainSourceLine(
                source_id=sf.source_id,
                display_name=sf.display_name,
                health_status=sf.health.status if sf.health else "Unknown",
                corrected_forecast_mm=_mm(sf.corrected_forecast_mm),
                weight=round(float(sf.weight), 4),
                reason=(
                    sf.trust.reason
                    if sf.trust and sf.trust.eligible
                    else (sf.ineligible_reason or "Excluded from this forecast.")
                ),
            )
        )
    return lines


def _build_explain(result: ForecastResult) -> ForecastExplainResponse:
    assert result.regime is not None
    assert result.blend is not None
    assert result.confidence is not None
    assert result.risk is not None

    regime, blend, confidence, risk = (
        result.regime, result.blend, result.confidence, result.risk
    )
    eligible = [sf for sf in result.sources if sf.eligible]
    top = max(eligible, key=lambda sf: sf.weight)
    final = _mm(blend.final_rainfall_mm) or 0.0

    headline = (
        f"{result.district_name}: about {final:.1f} mm of rain blended for "
        f"{result.valid_date} ({result.lead_hours}h lead) — {regime.label} regime, "
        f"{risk.risk_level} risk, {confidence.label} confidence "
        f"({confidence.score:.0f}/100)."
    )

    terms = " + ".join(
        f"{c['weight']:.2f} x {_mm(c['corrected_mm']) or 0.0:.1f} mm"
        for c in blend.contributions
    )
    why = [
        f"Blend: {final:.1f} mm = {terms} (algorithm {result.algorithm_version}, "
        f"config {result.config_version}).",
        f"Top-weighted source: {top.display_name} (weight {top.weight:.2f}) — "
        f"{top.trust.reason if top.trust else ''}",
        f"Weather regime {regime.label} (rule confidence {regime.confidence:.2f}): "
        f"{regime.reason}",
        "Source health: "
        + ", ".join(
            f"{sf.display_name} = {sf.health.status if sf.health else 'Unknown'}"
            for sf in result.sources
        )
        + f" (window ending {result.valid_date}).",
        f"Confidence {confidence.score:.0f}/100 ({confidence.label}): "
        + "; ".join(confidence.explanation[:4])
        + ".",
        f"Risk {risk.risk_level} ({risk.event_type}): {risk.reasons[0]} "
        + risk.disclaimer,
        "Bias correction: "
        + "; ".join(
            f"{sf.display_name} "
            + (
                f"{sf.bias.bias_mm:+.2f} mm from {sf.bias.historical_record_count} prior record(s)"
                if sf.bias and sf.bias.bias_available and sf.bias.bias_mm is not None
                else f"raw kept ({sf.bias.reason if sf.bias else 'n/a'})"
            )
            for sf in result.sources
        )
        + ".",
        blend.fallback_note,
        f"All bias, skill, health and regime context use records strictly earlier "
        f"than {result.valid_date}; no observation from the selected date or later "
        "is used.",
    ]

    health_note = (
        f"Source health (window ending {result.valid_date}): "
        + ", ".join(
            f"{sf.display_name} = {sf.health.status if sf.health else 'Unknown'}"
            for sf in result.sources
        )
        + f". {blend.fallback_note}"
    )

    return ForecastExplainResponse(
        disclaimer=settings.decision_support_disclaimer,
        data_mode=settings.data_mode,
        data_label=settings.synthetic_data_label,
        algorithm_version=result.algorithm_version,
        config_version=result.config_version,
        district=DistrictRef(
            district_id=result.district_id, district_name=result.district_name
        ),
        valid_date=result.valid_date,
        lead_hours=result.lead_hours,  # type: ignore[arg-type]
        headline=headline,
        final_rainfall_mm=final,
        regime=RegimeInfo(
            label=regime.label,  # type: ignore[arg-type]
            confidence=round(regime.confidence, 3),
            triggered_rules=regime.triggered_rules,
            thresholds_used=regime.thresholds_used,
            reason=regime.reason,
            rule_version=regime.rule_version,
        ),
        confidence=ConfidenceInfo(
            score=confidence.score,
            label=confidence.label,  # type: ignore[arg-type]
            factors=confidence.factors,
            explanation=confidence.explanation,
            uncertainty_lower_mm=_mm(confidence.uncertainty_lower_mm),
            uncertainty_upper_mm=_mm(confidence.uncertainty_upper_mm),
            uncertainty_half_width_mm=_mm(confidence.uncertainty_half_width_mm),
            uncertainty_basis=confidence.uncertainty_basis,
        ),
        risk=RiskInfo(
            event_type=risk.event_type,
            risk_level=risk.risk_level,  # type: ignore[arg-type]
            predicted_rainfall_mm=_mm(risk.predicted_rainfall_mm),
            validity_start=risk.validity_start,
            validity_end=risk.validity_end,
            confidence_score=round(risk.confidence_score, 1),
            confidence_label=risk.confidence_label,
            regime=risk.regime,
            escalated=risk.escalated,
            reasons=risk.reasons,
            preparedness_actions=risk.preparedness_actions,
            thresholds_used=risk.thresholds_used,
            disclaimer=risk.disclaimer,
        ),
        top_weighted_source=next(
            line for line in _explain_lines(result) if line.source_id == top.source_id
        ),
        sources=_explain_lines(result),
        source_health_note=health_note,
        fallback_mode=blend.fallback_mode,  # type: ignore[arg-type]
        fallback_note=blend.fallback_note,
        why_this_forecast=why,
        ml_model=result.ai_source_provenance,
    )


def _summary(result: ForecastResult) -> ForecastSummary:
    assert result.blend is not None
    assert result.confidence is not None
    assert result.risk is not None
    assert result.regime is not None
    return ForecastSummary(
        final_rainfall_mm=_mm(result.blend.final_rainfall_mm),
        confidence_score=result.confidence.score,
        confidence_label=result.confidence.label,
        fallback_mode=result.blend.fallback_mode,  # type: ignore[arg-type]
        weights=_display_weights({sf.source_id: sf.weight for sf in result.sources}),
        available_sources=list(result.data_availability["available_sources"]),
        regime=result.regime.label,
        risk_level=result.risk.risk_level,
    )


# --------------------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------------------
class SimulateFailureRequest(BaseModel):
    """Body for POST /forecast/simulate-source-failure."""

    district: str = Field(..., examples=["Prayagraj"])
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", examples=["2025-09-15"])
    lead_hours: Literal[6, 24, 72] = Field(..., examples=[24])
    failed_source: FailureSourceAlias = Field(..., examples=["nwp"])


# --------------------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------------------
@router.get(
    "/forecast",
    response_model=ForecastResponse,
    tags=["forecast"],
    summary="Blended forecast with bias correction, regime, trust weights, "
    "confidence and risk",
)
def forecast(
    district: str = Query(
        ..., description="District id or name.", examples=["Prayagraj"]
    ),
    valid_date: date = Query(
        ..., alias="date", description="Forecast valid date (YYYY-MM-DD)."
    ),
    lead_hours: int = Query(
        ...,
        description="Forecast horizon in hours — one of 6, 24 or 72.",
        examples=[24],
    ),
    simulate_failure_source: Optional[FailureSourceAlias] = Query(
        default=None,
        description="Optionally exclude one source (nwp | ensemble | ai) to demo "
        "degraded blending.",
    ),
) -> ForecastResponse:
    """Compute the full explainable forecast for one district/date/horizon."""
    lead_hours = _validate_lead(lead_hours)
    ds = get_dataset()
    district_id, name = _resolve(ds, district)
    result = _run(
        ds,
        district_id=district_id,
        district_name=name,
        valid_date=valid_date.isoformat(),
        lead_hours=lead_hours,
        simulate_failure_source=simulate_failure_source,
    )
    return _build_response(result)


@router.get(
    "/forecast/explain",
    response_model=ForecastExplainResponse,
    tags=["forecast"],
    summary="Plain-language explanation of a blended forecast",
)
def explain(
    district: str = Query(
        ..., description="District id or name.", examples=["Prayagraj"]
    ),
    valid_date: date = Query(
        ..., alias="date", description="Forecast valid date (YYYY-MM-DD)."
    ),
    lead_hours: int = Query(
        ...,
        description="Forecast horizon in hours — one of 6, 24 or 72.",
        examples=[24],
    ),
    simulate_failure_source: Optional[FailureSourceAlias] = Query(
        default=None, description="Optionally exclude one source (nwp | ensemble | ai)."
    ),
) -> ForecastExplainResponse:
    """Compact explanation built from exactly the same computed numbers."""
    lead_hours = _validate_lead(lead_hours)
    ds = get_dataset()
    district_id, name = _resolve(ds, district)
    result = _run(
        ds,
        district_id=district_id,
        district_name=name,
        valid_date=valid_date.isoformat(),
        lead_hours=lead_hours,
        simulate_failure_source=simulate_failure_source,
    )
    return _build_explain(result)


@router.post(
    "/forecast/simulate-source-failure",
    response_model=SimulateFailureResponse,
    tags=["forecast"],
    summary="Compare normal vs degraded blending when one source fails",
)
def simulate_source_failure(body: SimulateFailureRequest) -> SimulateFailureResponse:
    """Run the same point twice: normally and with one source excluded."""
    ds = get_dataset()
    district_id, name = _resolve(ds, body.district)
    try:
        parsed = datetime.strptime(body.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_date",
                "message": f"Invalid date '{body.date}'; expected YYYY-MM-DD.",
            },
        ) from None

    normal = _run(
        ds,
        district_id=district_id,
        district_name=name,
        valid_date=parsed.date().isoformat(),
        lead_hours=body.lead_hours,
        simulate_failure_source=None,
    )
    degraded = _run(
        ds,
        district_id=district_id,
        district_name=name,
        valid_date=parsed.date().isoformat(),
        lead_hours=body.lead_hours,
        simulate_failure_source=body.failed_source,
    )

    assert normal.blend is not None and degraded.blend is not None
    assert normal.confidence is not None and degraded.confidence is not None

    failed_id = FAILURE_ALIASES[body.failed_source]
    by_id_normal = {sf.source_id: sf for sf in normal.sources}
    by_id_degraded = {sf.source_id: sf for sf in degraded.sources}

    weight_changes = []
    for source_id, meta in SOURCE_DEFINITIONS.items():
        before = float(by_id_normal[source_id].weight)
        after = float(by_id_degraded[source_id].weight)
        trust_before = (
            by_id_normal[source_id].trust.trust_score
            if by_id_normal[source_id].trust
            else 0.0
        )
        trust_after = (
            by_id_degraded[source_id].trust.trust_score
            if by_id_degraded[source_id].trust
            else 0.0
        )
        weight_changes.append(
            WeightChange(
                source_id=source_id,
                display_name=str(meta["display_name"]),
                weight_before=round(before, 4),
                weight_after=round(after, 4),
                delta=round(after - before, 4),
                trust_score_before=round(float(trust_before), 4),
                trust_score_after=round(float(trust_after), 4),
            )
        )

    conf_before = normal.confidence.score
    conf_after = degraded.confidence.score
    rain_before = _mm(normal.blend.final_rainfall_mm) or 0.0
    rain_after = _mm(degraded.blend.final_rainfall_mm) or 0.0

    explanation = [
        f"Simulated failure of '{body.failed_source}' "
        f"({by_id_normal[failed_id].display_name}): weight "
        f"{by_id_normal[failed_id].weight:.2f} -> "
        f"{by_id_degraded[failed_id].weight:.2f} (trust forced to 0.0, weight 0.0).",
        "Weight redistribution: "
        + "; ".join(
            f"{sf.display_name} {by_id_normal[sf.source_id].weight:.2f} -> "
            f"{sf.weight:.2f} ({sf.weight - by_id_normal[sf.source_id].weight:+.2f})"
            for sf in degraded.sources
            if sf.eligible
        )
        + ".",
        f"Confidence changed {conf_before:.0f} -> {conf_after:.0f} "
        f"({conf_after - conf_before:+.0f} points); fallback mode "
        f"{normal.blend.fallback_mode} -> {degraded.blend.fallback_mode}.",
        f"Blended rainfall changed {rain_before:.1f} -> {rain_after:.1f} mm "
        f"({rain_after - rain_before:+.1f} mm).",
        settings.decision_support_disclaimer,
    ]

    return SimulateFailureResponse(
        disclaimer=settings.decision_support_disclaimer,
        data_mode=settings.data_mode,
        data_label=settings.synthetic_data_label,
        algorithm_version=normal.algorithm_version,
        config_version=normal.config_version,
        district=DistrictRef(district_id=district_id, district_name=name),
        valid_date=parsed.date().isoformat(),
        lead_hours=body.lead_hours,
        failed_source=body.failed_source,
        failed_source_id=failed_id,
        normal=_summary(normal),
        degraded=_summary(degraded),
        weight_changes=weight_changes,
        confidence_change={
            "normal": conf_before,
            "degraded": conf_after,
            "delta": round(conf_after - conf_before, 1),
        },
        rainfall_change_mm=round(rain_after - rain_before, 2),
        fallback_mode_change={
            "normal": normal.blend.fallback_mode,
            "degraded": degraded.blend.fallback_mode,
        },
        explanation=explanation,
    )
