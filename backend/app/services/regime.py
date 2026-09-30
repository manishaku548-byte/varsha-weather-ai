"""Transparent rule-based weather-regime classification (SRS FR-REG-01..05).

Priority order (highest first):

    1. Heavy-Rain Risk  — ensemble mean OR any bias-corrected blend input
                          crosses the configured heavy-rain threshold
    2. Heatwave         — latest available temperature reaches the threshold
    3. Active Monsoon   — any wet-condition signal (ensemble rainfall,
                          trailing 3-day observations, humidity proxy)
    4. Normal           — otherwise

The classifier is deliberately simple, deterministic and fully configurable.
It is a prototype rule set — it carries **no** meteorological operational
certification.

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Settings, settings as default_settings, thresholds_for_lead

REGIME_NORMAL = "Normal"
REGIME_MONSOON = "Active Monsoon"
REGIME_HEAVY = "Heavy-Rain Risk"
REGIME_HEATWAVE = "Heatwave"

REGIME_ORDER = (REGIME_HEAVY, REGIME_HEATWAVE, REGIME_MONSOON, REGIME_NORMAL)


@dataclass
class RegimeResult:
    label: str
    confidence: float  # 0..1
    triggered_rules: list[str] = field(default_factory=list)
    thresholds_used: dict[str, float] = field(default_factory=dict)
    reason: str = ""
    rule_version: str = "regime-rules-v1"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def detect_regime(
    *,
    ensemble_mm: float | None,
    corrected_values: list[float | None],
    trailing_3day_mm: float | None,
    temp_c: float | None,
    humidity_pct: float | None,
    lead_hours: int,
    cfg: Settings | None = None,
) -> RegimeResult:
    """Classify the prevailing regime from forecast signals and prior observations.

    All observational inputs (trailing rainfall, temperature, humidity) must be
    values from *before* the selected date — the caller is responsible for that.
    """
    s = cfg or settings_ref(cfg)
    thresholds = thresholds_for_lead(lead_hours, s)

    inputs = [v for v in ([ensemble_mm] + list(corrected_values)) if v is not None]
    peak = max(inputs) if inputs else None

    thresholds_used = {
        "heavy_rain_mm": round(thresholds["heavy"], 3),
        "very_heavy_rain_mm": round(thresholds["very_heavy"], 3),
        "extreme_rain_mm": round(thresholds["extreme"], 3),
        "moderate_rain_mm": round(thresholds["moderate"], 3),
        "heatwave_temp_c": s.heatwave_temp_c,
        "monsoon_ensemble_mm": round(
            thresholds["moderate"] * s.active_monsoon_ensemble_mm_factor, 3
        ),
        "monsoon_trailing_3day_mm": s.active_monsoon_trailing_3day_mm,
        "monsoon_humidity_pct": s.active_monsoon_humidity_pct,
    }

    # --- Rule 1 (highest priority): Heavy-Rain Risk -------------------------------
    if peak is not None and peak >= thresholds["heavy"]:
        ensemble_crossed = ensemble_mm is not None and ensemble_mm >= thresholds["heavy"]
        corrected_crossed = any(
            v is not None and v >= thresholds["heavy"] for v in corrected_values
        )
        confidence = 0.60
        if peak >= thresholds["very_heavy"]:
            confidence += 0.20
        if ensemble_crossed and corrected_crossed:
            confidence += 0.10
        confidence = round(_clamp(confidence, 0.5, 0.95), 3)

        triggered = [
            f"heavy_rain: peak blend-input forecast {peak:.1f} mm >= "
            f"{thresholds['heavy']:.1f} mm threshold (lead {lead_hours}h)"
        ]
        if ensemble_crossed:
            triggered.append(
                f"heavy_rain: ensemble mean {ensemble_mm:.1f} mm >= "
                f"{thresholds['heavy']:.1f} mm"
            )
        if corrected_crossed:
            triggering = [
                f"{v:.1f} mm" for v in corrected_values if v is not None and v >= thresholds["heavy"]
            ]
            triggered.append(
                "heavy_rain: bias-corrected input(s) above threshold: "
                + ", ".join(triggering)
            )
        return RegimeResult(
            label=REGIME_HEAVY,
            confidence=confidence,
            triggered_rules=triggered,
            thresholds_used=thresholds_used,
            reason=(
                f"Peak blend-input rainfall {peak:.1f} mm reaches the configured "
                f"heavy-rain threshold ({thresholds['heavy']:.1f} mm for {lead_hours}h), "
                "so Heavy-Rain Risk takes priority over every other regime."
            ),
        )

    # --- Rule 2: Heatwave ---------------------------------------------------------
    if temp_c is not None and temp_c >= s.heatwave_temp_c:
        margin = _clamp((temp_c - s.heatwave_temp_c) / 5.0)
        confidence = round(_clamp(0.60 + 0.30 * margin, 0.5, 0.95), 3)
        triggered = [
            f"heatwave: latest available temperature {temp_c:.1f} C >= "
            f"{s.heatwave_temp_c:.1f} C threshold"
        ]
        if humidity_pct is not None and humidity_pct < 40.0:
            triggered.append(
                f"heatwave: humidity {humidity_pct:.0f}% supports dry hot conditions"
            )
        return RegimeResult(
            label=REGIME_HEATWAVE,
            confidence=confidence,
            triggered_rules=triggered,
            thresholds_used=thresholds_used,
            reason=(
                f"Temperature {temp_c:.1f} C (latest observation before the selected "
                f"date) reaches the {s.heatwave_temp_c:.1f} C heatwave threshold and no "
                "heavy-rain rule fired."
            ),
        )

    # --- Rule 3: Active Monsoon ---------------------------------------------------
    signals: list[str] = []
    wet_threshold = thresholds["moderate"] * s.active_monsoon_ensemble_mm_factor
    if ensemble_mm is not None and ensemble_mm >= wet_threshold:
        signals.append(
            f"active_monsoon: ensemble mean {ensemble_mm:.1f} mm >= {wet_threshold:.1f} mm"
        )
    if trailing_3day_mm is not None and trailing_3day_mm >= s.active_monsoon_trailing_3day_mm:
        signals.append(
            f"active_monsoon: trailing 3-day observed rainfall {trailing_3day_mm:.1f} mm >= "
            f"{s.active_monsoon_trailing_3day_mm:.1f} mm"
        )
    if humidity_pct is not None and humidity_pct >= s.active_monsoon_humidity_pct:
        signals.append(
            f"active_monsoon: humidity {humidity_pct:.0f}% >= "
            f"{s.active_monsoon_humidity_pct:.0f}%"
        )
    if signals:
        confidence = round(_clamp(0.50 + 0.15 * len(signals), 0.4, 0.95), 3)
        return RegimeResult(
            label=REGIME_MONSOON,
            confidence=confidence,
            triggered_rules=signals,
            thresholds_used=thresholds_used,
            reason=(
                f"{len(signals)} wet-condition signal(s) detected while rainfall stays "
                "below the heavy-rain threshold and temperature is below the heatwave "
                "threshold."
            ),
        )

    # --- Rule 4: Normal -----------------------------------------------------------
    if peak is None:
        wetness_ratio = 0.0
        note = "no forecast inputs available; defaulting to Normal"
    else:
        wetness_ratio = _clamp(peak / thresholds["heavy"])
        note = "all regime thresholds below trigger level"
    confidence = round(_clamp(0.60 + 0.30 * (1.0 - wetness_ratio), 0.5, 0.95), 3)

    return RegimeResult(
        label=REGIME_NORMAL,
        confidence=confidence,
        triggered_rules=[],
        thresholds_used=thresholds_used,
        reason=(
            f"No heavy-rain, heatwave or monsoon rule triggered ({note}); peak "
            f"blend-input rainfall is {peak:.1f} mm against a "
            f"{thresholds['heavy']:.1f} mm heavy threshold."
            if peak is not None
            else f"No regime threshold triggered ({note})."
        ),
    )


def settings_ref(cfg: Settings | None) -> Settings:
    """Return the active settings object (small indirection for readability)."""
    return cfg or default_settings
