"""Mean-bias correction from strictly prior records (SRS FR-BC-01..06).

For a selected (district, lead_hours, source) and a selected forecast date,
the bias is computed **only** from records whose ``valid_date`` is strictly
earlier than the selected date:

    bias   = mean(observed_rain_mm - source_forecast_mm)   over prior records
    corrected = max(0, raw_forecast + bias)

Records used for bias (and later for skill) must be *usable*:
``status == "ok"``, a present value, and both observed/forecast inside the
plausible range. Implausible (anomalous) and unavailable records never enter
the history.

Decision-Support Prototype — Synthetic Development Dataset —
Not Operational Weather Data — Not an Official Weather Warning.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from ..config import Settings, settings as default_settings


@dataclass
class BiasResult:
    """Bias metadata for one source at one forecast point."""

    source_id: str
    raw_forecast_mm: float
    bias_mm: float | None
    corrected_forecast_mm: float
    historical_record_count: int
    bias_available: bool
    reason: str
    method: str


@dataclass
class PriorHistory:
    """Prior (strictly earlier) usable records for one source."""

    source_id: str
    district_id: str
    lead_hours: int
    as_of_date: str
    frame: pd.DataFrame  # columns: valid_date, observed_mm, forecast_mm, residual_mm

    @property
    def count(self) -> int:
        return int(len(self.frame))

    def mae(self) -> float | None:
        if self.count == 0:
            return None
        return float(self.frame["residual_mm"].abs().mean())

    def recent(self, n: int) -> "PriorHistory":
        if self.count == 0:
            return self
        trimmed = self.frame.sort_values("valid_date", ascending=False).head(n)
        return PriorHistory(
            source_id=self.source_id,
            district_id=self.district_id,
            lead_hours=self.lead_hours,
            as_of_date=self.as_of_date,
            frame=trimmed.reset_index(drop=True),
        )


def _empty_history(source_id: str, district_id: str, lead_hours: int, as_of_date: str) -> PriorHistory:
    frame = pd.DataFrame(
        {
            "valid_date": pd.Series(dtype="datetime64[ns]"),
            "observed_mm": pd.Series(dtype="float64"),
            "forecast_mm": pd.Series(dtype="float64"),
            "residual_mm": pd.Series(dtype="float64"),
        }
    )
    return PriorHistory(source_id, district_id, lead_hours, as_of_date, frame)


def prior_history(
    forecasts: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    district_id: str,
    lead_hours: int,
    source_id: str,
    as_of_date: str,
    cfg: Settings | None = None,
) -> PriorHistory:
    """Join forecasts with observations and keep only strictly prior usable rows."""
    s = cfg or default_settings
    as_of = pd.to_datetime(as_of_date)

    fc = forecasts[
        (forecasts["district_id"].astype(str) == district_id)
        & (pd.to_numeric(forecasts["lead_hours"], errors="coerce") == lead_hours)
        & (forecasts["source_id"].astype(str) == source_id)
    ].copy()
    if fc.empty:
        return _empty_history(source_id, district_id, lead_hours, as_of_date)

    fc_dates = pd.to_datetime(fc["valid_date"], errors="coerce")
    fc = fc[fc_dates < as_of]  # strictly earlier — never the selected date
    if fc.empty:
        return _empty_history(source_id, district_id, lead_hours, as_of_date)

    obs = observations[
        (observations["district_id"].astype(str) == district_id)
        & (pd.to_numeric(observations["lead_hours"], errors="coerce") == lead_hours)
    ][["valid_date", "observed_rain_mm"]].copy()

    merged = fc.merge(obs, on="valid_date", how="inner")
    if merged.empty:
        return _empty_history(source_id, district_id, lead_hours, as_of_date)

    forecast_mm = pd.to_numeric(merged["forecast_rain_mm"], errors="coerce")
    observed_mm = pd.to_numeric(merged["observed_rain_mm"], errors="coerce")
    usable = (
        (merged["status"].astype(str) == "ok")
        & forecast_mm.notna()
        & observed_mm.notna()
        & (forecast_mm >= 0)
        & (forecast_mm <= s.max_plausible_rain_mm)
        & (observed_mm >= 0)
        & (observed_mm <= s.max_plausible_rain_mm)
    )
    merged = merged[usable]
    if merged.empty:
        return _empty_history(source_id, district_id, lead_hours, as_of_date)

    out = pd.DataFrame(
        {
            "valid_date": pd.to_datetime(merged["valid_date"], errors="coerce"),
            "observed_mm": observed_mm[merged.index].astype(float),
            "forecast_mm": forecast_mm[merged.index].astype(float),
        }
    ).sort_values("valid_date")
    out["residual_mm"] = out["observed_mm"] - out["forecast_mm"]
    out = out.reset_index(drop=True)

    return PriorHistory(source_id, district_id, lead_hours, as_of_date, out)


def compute_bias(
    forecasts: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    district_id: str,
    lead_hours: int,
    source_id: str,
    as_of_date: str,
    raw_forecast_mm: float | None,
    cfg: Settings | None = None,
) -> BiasResult:
    """Compute and apply mean bias for one source (prior records only)."""
    s = cfg or default_settings

    if raw_forecast_mm is None or (
        isinstance(raw_forecast_mm, float) and math.isnan(raw_forecast_mm)
    ):
        return BiasResult(
            source_id=source_id,
            raw_forecast_mm=float("nan"),
            bias_mm=None,
            corrected_forecast_mm=float("nan"),
            historical_record_count=0,
            bias_available=False,
            reason="No usable raw forecast to correct.",
            method=s.bias_method,
        )

    history = prior_history(
        forecasts,
        observations,
        district_id=district_id,
        lead_hours=lead_hours,
        source_id=source_id,
        as_of_date=as_of_date,
        cfg=s,
    )
    count = history.count

    if count < s.min_bias_history_records:
        return BiasResult(
            source_id=source_id,
            raw_forecast_mm=float(raw_forecast_mm),
            bias_mm=None,
            corrected_forecast_mm=float(raw_forecast_mm),
            historical_record_count=count,
            bias_available=False,
            reason="Insufficient prior history",
            method=s.bias_method,
        )

    bias = float(history.frame["residual_mm"].mean())
    corrected = max(0.0, float(raw_forecast_mm) + bias)
    reason = (
        f"Mean bias {bias:+.2f} mm computed from {count} record(s) strictly "
        f"earlier than {as_of_date} ({s.bias_method})."
    )
    if corrected == 0.0 and float(raw_forecast_mm) + bias < 0.0:
        reason += " Corrected value floored at 0.0 mm (rainfall cannot be negative)."

    return BiasResult(
        source_id=source_id,
        raw_forecast_mm=float(raw_forecast_mm),
        bias_mm=bias,
        corrected_forecast_mm=corrected,
        historical_record_count=count,
        bias_available=True,
        reason=reason,
        method=s.bias_method,
    )
