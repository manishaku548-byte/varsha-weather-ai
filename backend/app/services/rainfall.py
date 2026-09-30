"""Rainfall categorisation helpers using configurable thresholds.

Defaults follow India (IMD-style) 24-hour rainfall categories but remain
prototype defaults only and are fully configurable in ``config.Settings``.

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..config import Settings, settings as default_settings
from ..schemas import RainfallBuckets

BUCKET_ORDER = ("dry", "light", "moderate", "heavy", "very_heavy", "extreme")


def rainfall_bucket(mm: float, cfg: Settings | None = None) -> str:
    """Classify a rainfall amount (mm) into a named bucket."""
    s = cfg or default_settings
    if mm < 0.1:
        return "dry"
    if mm <= s.light_max_mm:
        return "light"
    if mm <= s.moderate_max_mm:
        return "moderate"
    if mm <= s.heavy_max_mm:
        return "heavy"
    if mm <= s.very_heavy_max_mm:
        return "very_heavy"
    return "extreme"


def bucket_counts(values: Iterable[float], cfg: Settings | None = None) -> RainfallBuckets:
    """Count values per rainfall bucket (NaN/None values are skipped)."""
    counts = dict.fromkeys(BUCKET_ORDER, 0)
    for value in values:
        if value is None:
            continue
        try:
            mm = float(value)
        except (TypeError, ValueError):
            continue
        if mm != mm:  # NaN guard
            continue
        counts[rainfall_bucket(mm, cfg)] += 1
    return RainfallBuckets(**counts)
