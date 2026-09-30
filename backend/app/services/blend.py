"""Forecast blending (SRS FR-BLD-01..06).

    final_rainfall_mm = sum(weight_i * corrected_forecast_i)

Fallback modes:
* ``normal``        — all three sources available
* ``degraded``      — exactly two sources available (fallback blend)
* ``single_source`` — only one source available; its weight is exactly 1.0
                      and the output is explicitly labelled
                      "single-source fallback"

No rounding happens here — values are full precision; the API layer rounds
for display only.

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import SOURCE_DEFINITIONS


@dataclass
class BlendResult:
    final_rainfall_mm: float
    fallback_mode: str
    fallback_note: str
    available_count: int
    contributions: list[dict] = field(default_factory=list)
    unavailable_sources: list[str] = field(default_factory=list)


def fallback_mode_for(available_count: int) -> str:
    if available_count >= len(SOURCE_DEFINITIONS):
        return "normal"
    if available_count == 1:
        return "single_source"
    if available_count == 0:
        return "unavailable"
    return "degraded"


def blend_sources(
    corrected_mm: dict[str, float | None],
    weights: dict[str, float],
    display_names: dict[str, str] | None = None,
) -> BlendResult:
    """Blend eligible corrected forecasts with their normalized weights."""
    names = display_names or {sid: sid for sid in SOURCE_DEFINITIONS}
    contributions: list[dict] = []
    total = 0.0
    available: list[str] = []

    for source_id in SOURCE_DEFINITIONS:
        weight = float(weights.get(source_id, 0.0))
        corrected = corrected_mm.get(source_id)
        if weight > 0.0 and corrected is not None:
            contribution = weight * float(corrected)
            total += contribution
            available.append(source_id)
            contributions.append(
                {
                    "source_id": source_id,
                    "weight": weight,
                    "corrected_mm": float(corrected),
                    "contribution_mm": contribution,
                }
            )

    mode = fallback_mode_for(len(available))
    unavailable = [sid for sid in SOURCE_DEFINITIONS if sid not in available]

    if mode == "single_source":
        note = (
            "single-source fallback: only "
            f"{names[available[0]]} was available, so it carries the entire "
            "weight (1.0) and confidence is capped."
        )
    elif mode == "degraded":
        note = (
            "degraded fallback: blended from "
            + ", ".join(names[sid] for sid in available)
            + " only; "
            + ", ".join(names[sid] for sid in unavailable)
            + " was excluded (weight 0.0) and confidence is capped."
        )
    elif mode == "unavailable":
        note = "no source available: forecast cannot be produced."
    else:
        note = "normal blend: all three sources contributed with normalized weights."

    return BlendResult(
        final_rainfall_mm=float(total),
        fallback_mode=mode,
        fallback_note=note,
        available_count=len(available),
        contributions=contributions,
        unavailable_sources=unavailable,
    )
