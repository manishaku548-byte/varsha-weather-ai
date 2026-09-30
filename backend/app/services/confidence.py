"""Confidence and uncertainty engine (SRS FR-CONF-01..05).

Confidence (0-100) is a weighted combination of transparent factors:

    available sources : available / 3                                  (25%)
    historical skill  : weight-average of inverse-MAE skill scores     (25%)
    source health     : weight-average of health scores                 (15%)
    agreement         : weight-average of peer-median agreement         (20%)
    ensemble spread   : 1 / (1 + spread / scale)                        (15%)

Fallback caps guarantee reduced confidence on failure:
    single_source -> maximum 39 (Low)
    degraded      -> maximum 69 (Medium)

Bands: Low 0-39 · Medium 40-69 · High 70-100.

The uncertainty range is a prototype heuristic interval (NOT a calibrated
prediction interval) built from source disagreement, ensemble spread and the
unexplained part of the confidence score.

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import SOURCE_DEFINITIONS, Settings, settings as default_settings


@dataclass
class ConfidenceResult:
    score: float
    label: str
    factors: dict[str, float] = field(default_factory=dict)
    explanation: list[str] = field(default_factory=list)
    uncertainty_lower_mm: float | None = None
    uncertainty_upper_mm: float | None = None
    uncertainty_half_width_mm: float | None = None
    uncertainty_basis: str = ""


def confidence_label(score: float) -> str:
    if score < 40.0:
        return "Low"
    if score < 70.0:
        return "Medium"
    return "High"


def compute_confidence(
    *,
    available_count: int,
    weighted_historical_skill: float,
    weighted_health: float,
    weighted_agreement: float,
    ensemble_spread_mm: float | None,
    disagreement_mm: float,
    blend_mm: float,
    fallback_mode: str,
    cfg: Settings | None = None,
) -> ConfidenceResult:
    """Compute a 0-100 confidence score with explanation and uncertainty range."""
    s = cfg or default_settings
    total_sources = len(SOURCE_DEFINITIONS)

    factors: dict[str, float] = {
        "available_sources": round(available_count / total_sources, 4),
        "historical_skill": round(max(0.0, min(1.0, weighted_historical_skill)), 4),
        "health": round(max(0.0, min(1.0, weighted_health)), 4),
        "agreement": round(max(0.0, min(1.0, weighted_agreement)), 4),
    }

    weights = dict(s.confidence_weights)
    spread_factor: float | None = None
    if ensemble_spread_mm is not None:
        spread_factor = 1.0 / (1.0 + max(0.0, ensemble_spread_mm) / s.spread_score_scale_mm)
        factors["ensemble_spread"] = round(spread_factor, 4)
    else:
        weights = {k: v for k, v in weights.items() if k != "ensemble_spread"}

    usable = {k: v for k, v in weights.items() if k in factors}
    weight_sum = sum(usable.values())
    if weight_sum <= 0:  # pragma: no cover - configuration guard
        return ConfidenceResult(score=0.0, label="Low", factors=factors,
                                explanation=["No confidence factors configured."])

    score = 100.0 * sum(usable[k] * factors[k] for k in usable) / weight_sum

    cap_reason: str | None = None
    if fallback_mode == "single_source":
        cap = float(s.confidence_cap_single_source)
        if score > cap:
            cap_reason = f"capped at {cap:.0f} because of single-source fallback"
        score = min(score, cap)
    elif fallback_mode == "degraded":
        cap = float(s.confidence_cap_degraded)
        if score > cap:
            cap_reason = f"capped at {cap:.0f} because a source failed (degraded fallback)"
        score = min(score, cap)

    score = round(max(0.0, min(100.0, score)), 1)

    explanation = [
        f"available sources: {available_count}/{total_sources} "
        f"({factors['available_sources'] * 100:.0f}%)",
        f"weighted historical skill: {factors['historical_skill']:.2f} (0-1, inverse MAE)",
        f"weighted source health: {factors['health']:.2f}",
        f"weighted agreement: {factors['agreement']:.2f}",
    ]
    if spread_factor is not None:
        explanation.append(
            f"ensemble spread: {ensemble_spread_mm:.1f} mm -> {spread_factor:.2f}"
        )
    else:
        explanation.append("ensemble spread: not available for this point (neutral factor removed)")
    if cap_reason:
        explanation.append(f"fallback cap: {cap_reason}")
    explanation.append(f"bands: Low 0-39 · Medium 40-69 · High 70-100 -> {confidence_label(score)}")

    # --- uncertainty ---------------------------------------------------------------
    half_width = max(disagreement_mm, ensemble_spread_mm or 0.0)
    half_width = max(half_width, blend_mm * (100.0 - score) / 100.0)
    lower = max(0.0, blend_mm - half_width)
    upper = blend_mm + half_width

    basis = (
        "prototype heuristic interval = max(weighted source disagreement, ensemble "
        "spread, blend x (100 - confidence)/100); not a calibrated prediction interval"
    )

    return ConfidenceResult(
        score=score,
        label=confidence_label(score),
        factors=factors,
        explanation=explanation,
        uncertainty_lower_mm=float(lower),
        uncertainty_upper_mm=float(upper),
        uncertainty_half_width_mm=float(half_width),
        uncertainty_basis=basis,
    )
