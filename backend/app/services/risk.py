"""Extreme-event rainfall risk engine (SRS FR-RISK-01..06).

Levels: Low · Moderate · High · Critical (all thresholds configurable).

Prototype default rainfall categories (24h, scaled by lead time):

    moderate 15.6 mm   heavy 64.5 mm   very heavy 115.6 mm   extreme 204.5 mm

Mapping (amount -> base level):
    < moderate            -> Low
    >= moderate           -> Moderate
    >= heavy              -> High
    >= very heavy         -> Critical   (extreme adds an explicit reason)

Adjustments:
* Heavy-Rain Risk regime escalates Low/Moderate by one level (the ensemble or
  a corrected input already crossed the heavy threshold even if the blend did
  not).
* Low confidence never silently lowers a level; it adds a caveat instead.

Every risk output carries the non-binding note:
"Decision-support output only; not an official warning."

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..config import Settings, settings as default_settings, thresholds_for_lead
from .regime import REGIME_HEAVY


@dataclass
class RiskResult:
    event_type: str
    risk_level: str
    predicted_rainfall_mm: float
    validity_start: str
    validity_end: str
    confidence_score: float
    confidence_label: str
    reasons: list[str] = field(default_factory=list)
    preparedness_actions: list[str] = field(default_factory=list)
    thresholds_used: dict[str, float] = field(default_factory=dict)
    disclaimer: str = ""
    regime: str = ""
    escalated: bool = False


def _base_level(rainfall_mm: float, thresholds: dict[str, float]) -> tuple[str, str]:
    if rainfall_mm >= thresholds["very_heavy"]:
        return "Critical", (
            f"blended rainfall {rainfall_mm:.1f} mm >= very-heavy threshold "
            f"{thresholds['very_heavy']:.1f} mm"
        )
    if rainfall_mm >= thresholds["heavy"]:
        return "High", (
            f"blended rainfall {rainfall_mm:.1f} mm >= heavy threshold "
            f"{thresholds['heavy']:.1f} mm"
        )
    if rainfall_mm >= thresholds["moderate"]:
        return "Moderate", (
            f"blended rainfall {rainfall_mm:.1f} mm >= moderate threshold "
            f"{thresholds['moderate']:.1f} mm"
        )
    return "Low", (
        f"blended rainfall {rainfall_mm:.1f} mm < moderate threshold "
        f"{thresholds['moderate']:.1f} mm"
    )


def assess_risk(
    *,
    rainfall_mm: float,
    regime_label: str,
    confidence_score: float,
    confidence_label: str,
    valid_date: str,
    lead_hours: int,
    cfg: Settings | None = None,
) -> RiskResult:
    """Classify rainfall risk for one blended forecast."""
    s = cfg or default_settings
    thresholds = thresholds_for_lead(lead_hours, s)
    levels = list(s.risk_levels)

    level, base_reason = _base_level(rainfall_mm, thresholds)
    reasons = [f"Amount: {base_reason}."]
    escalated = False

    if rainfall_mm >= thresholds["extreme"]:
        reasons.append(
            f"Extreme category crossed: {rainfall_mm:.1f} mm >= "
            f"{thresholds['extreme']:.1f} mm."
        )

    base_index = levels.index(level)
    if regime_label == REGIME_HEAVY and level in ("Low", "Moderate"):
        new_index = min(base_index + 1, len(levels) - 1)
        level = levels[new_index]
        escalated = True
        reasons.append(
            f"Regime: Heavy-Rain Risk detected (ensemble/corrected input crossed "
            f"{thresholds['heavy']:.1f} mm) — risk escalated from "
            f"{levels[base_index]} to {level}."
        )
    else:
        reasons.append(f"Regime: {regime_label} (no regime-driven escalation).")

    if confidence_label == "Low" and level in ("High", "Critical"):
        reasons.append(
            f"Confidence caveat: confidence is Low ({confidence_score:.0f}/100); "
            "treat the magnitude as uncertain and verify before acting."
        )
    else:
        reasons.append(
            f"Confidence: {confidence_score:.0f}/100 ({confidence_label})."
        )

    valid_end = datetime.strptime(valid_date, "%Y-%m-%d")
    valid_start = valid_end - timedelta(hours=lead_hours)

    return RiskResult(
        event_type="heavy_rainfall",
        risk_level=level,
        predicted_rainfall_mm=float(rainfall_mm),
        validity_start=valid_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        validity_end=valid_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        confidence_score=float(confidence_score),
        confidence_label=confidence_label,
        reasons=reasons,
        preparedness_actions=list(s.preparedness_actions.get(level, [])),
        thresholds_used={
            "moderate_mm": round(thresholds["moderate"], 3),
            "heavy_mm": round(thresholds["heavy"], 3),
            "very_heavy_mm": round(thresholds["very_heavy"], 3),
            "extreme_mm": round(thresholds["extreme"], 3),
        },
        disclaimer=s.risk_disclaimer,
        regime=regime_label,
        escalated=escalated,
    )
