"""Source-health service (SRS FR-SRC-06/07, NFR-REL-01/02).

Classifies each forecast source over a configurable recent window as
Healthy / Delayed / Unavailable / Anomalous using configurable ratio
thresholds. Health feeds the Dynamic Trust Engine in Phase 2.

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

import pandas as pd

from ..config import SOURCE_DEFINITIONS, Settings, settings as default_settings
from ..schemas import SourceHealth, SourceHealthStatus


def _classify(
    unavailable: float,
    anomalous: float,
    delayed: float,
    cfg: Settings,
    window_days: int,
) -> tuple[SourceHealthStatus, str]:
    """Rule cascade: Unavailable > Anomalous > Delayed > Healthy."""
    if unavailable >= cfg.health_unavailable_ratio:
        return (
            "Unavailable",
            f"{unavailable:.0%} of records in the window are unavailable "
            f"(threshold {cfg.health_unavailable_ratio:.0%}).",
        )
    if anomalous >= cfg.health_anomalous_ratio:
        return (
            "Anomalous",
            f"{anomalous:.0%} of records in the window are anomalous "
            f"(threshold {cfg.health_anomalous_ratio:.0%}).",
        )
    if delayed >= cfg.health_delayed_ratio:
        return (
            "Delayed",
            f"{delayed:.0%} of records in the window are delayed "
            f"(threshold {cfg.health_delayed_ratio:.0%}).",
        )
    return (
        "Healthy",
        f"All record-quality ratios are below their thresholds over the last "
        f"{window_days} day(s).",
    )


def compute_source_health(
    forecasts: pd.DataFrame,
    window_days: int | None = None,
    cfg: Settings | None = None,
    as_of_date: str | pd.Timestamp | None = None,
) -> list[SourceHealth]:
    """Compute health for every registered source over the recent window.

    ``as_of_date`` caps the window at a given date so replay forecasts never
    look at records from the selected date or later (no future-data leakage).
    """
    s = cfg or default_settings
    days = window_days or s.source_health_window_days

    results: list[SourceHealth] = []

    if forecasts.empty:
        window = forecasts
        max_date = pd.NaT
    else:
        dates = pd.to_datetime(forecasts["valid_date"], errors="coerce")
        if as_of_date is not None:
            as_of_ts = pd.to_datetime(as_of_date)
            eligible = forecasts[dates <= as_of_ts]
            max_date = as_of_ts if len(eligible) else pd.NaT
        else:
            eligible = forecasts
            max_date = dates.max()
        eligible_dates = pd.to_datetime(eligible["valid_date"], errors="coerce")
        if pd.isna(max_date):
            window = eligible.iloc[0:0]
        else:
            start = max_date - pd.Timedelta(days=days - 1)
            window = eligible[(eligible_dates >= start) & (eligible_dates <= max_date)]

    for source_id, meta in SOURCE_DEFINITIONS.items():
        rows = window[window["source_id"].astype(str) == source_id] if len(window) else window
        total = len(rows)

        if total == 0:
            results.append(
                SourceHealth(
                    source_id=source_id,
                    source_type=meta["source_type"],
                    status="Unavailable",
                    window_days=days,
                    records_in_window=0,
                    unavailable_ratio=1.0,
                    delayed_ratio=0.0,
                    anomalous_ratio=0.0,
                    reason=(
                        f"No records received in the last {days} day(s)"
                        + (f" up to {pd.to_datetime(as_of_date).date()}" if as_of_date is not None else "")
                        + "."
                    ),
                )
            )
            continue

        status_col = rows["status"].astype(str)
        unavailable = float((status_col == "unavailable").mean())
        delayed = float((status_col == "delayed").mean())
        anomalous = float((status_col == "anomalous").mean())

        status, reason = _classify(unavailable, anomalous, delayed, s, days)

        results.append(
            SourceHealth(
                source_id=source_id,
                source_type=meta["source_type"],
                status=status,
                window_days=days,
                records_in_window=total,
                unavailable_ratio=round(unavailable, 4),
                delayed_ratio=round(delayed, 4),
                anomalous_ratio=round(anomalous, 4),
                reason=(
                    f"{reason} Based on {total} record(s), all districts and lead times."
                    + (f" Window ends {pd.to_datetime(as_of_date).date()}." if as_of_date is not None else "")
                ),
            )
        )

    return results
