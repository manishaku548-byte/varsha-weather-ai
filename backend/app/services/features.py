"""Phase 4 — leakage-safe feature engineering for the local correction model.

Every feature row for (district, valid_date D, lead_hours) is composed only
from information that exists **strictly before D** or that is known at issue
time from the forecast records themselves:

* raw NWP / ensemble forecast values for D         — issued at D - lead (forecast side)
* ensemble spread for D                            — issued with the forecast
* prior temperature / wind                         — latest observation < D
* rolling rainfall totals/means over [D-7, D-1]    — observations strictly < D
* prior source-status ratios over [D-14, D-1)      — forecast statuses < D
* district / month / season / lead_hours           — calendar & configuration

Never included (target leakage is impossible by construction):

* observed rainfall on D (the target) — only ever written to the target column
* any observation >= D
* bias-corrected or blended values (they are derived pipeline outputs)
* future source quality

`feature_availability` gives a per-row skip reason
(`ok` | `missing_forecast` | `insufficient_history`) so neither training nor
inference ever guesses from inadequate history.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from ..config import Settings, settings as default_settings

#: Target column (kept strictly separate from the feature lists).
TARGET_COLUMN = "target_observed_rain_mm"

#: Numeric features (imputed with train-fitted medians inside the pipeline).
NUMERIC_FEATURES: list[str] = [
    "nwp_rain_mm",
    "ensemble_mean_mm",
    "ensemble_spread_mm",
    "prior_temp_c",
    "prior_wind_kmph",
    "prior_rain_1d_mm",
    "prior_rain_3d_total_mm",
    "prior_rain_3d_mean_mm",
    "prior_rain_7d_total_mm",
    "prior_rain_7d_mean_mm",
    "nwp_prior_ok_ratio",
    "ensemble_prior_ok_ratio",
    "month",
    "lead_hours",
]

#: Categorical features (one-hot encoded, train-fitted categories, unknown-safe).
CATEGORICAL_FEATURES: list[str] = ["district", "season"]

#: Full ordered feature schema (the pipeline consumes columns by this name list).
FEATURE_COLUMNS: list[str] = NUMERIC_FEATURES + CATEGORICAL_FEATURES

FEATURE_AVAILABILITY_OK = "ok"
FEATURE_AVAILABILITY_MISSING_FORECAST = "missing_forecast"
FEATURE_AVAILABILITY_INSUFFICIENT_HISTORY = "insufficient_history"

#: Documentation for docs/data_dictionary.md — every feature with its source,
#: its timing and the reason it cannot leak the target.
FEATURE_DOCS: list[dict] = [
    {
        "feature": "nwp_rain_mm",
        "type": "numeric",
        "source": "historical_forecasts_synthetic.csv (nwp_model_a.forecast_rain_mm)",
        "timing": "Raw forecast for date D, issued at D - lead_hours (forecast side)",
        "leakage_safeguard": "Raw value only; never bias-corrected or blended; contains no observation",
    },
    {
        "feature": "ensemble_mean_mm",
        "type": "numeric",
        "source": "historical_forecasts_synthetic.csv (ensemble_mean.forecast_rain_mm)",
        "timing": "Raw forecast for date D, issued at D - lead_hours",
        "leakage_safeguard": "Raw value only; no observation enters this column",
    },
    {
        "feature": "ensemble_spread_mm",
        "type": "numeric",
        "source": "historical_forecasts_synthetic.csv (ensemble_spread_mm)",
        "timing": "Published with the ensemble forecast for D",
        "leakage_safeguard": "Forecast-side statistic; imputed with the train-split median when absent",
    },
    {
        "feature": "prior_temp_c",
        "type": "numeric",
        "source": "observations_synthetic.csv (observed_temp_c, lead 24 series)",
        "timing": "Latest observation strictly before D",
        "leakage_safeguard": "Window is `date < D`; the value on D itself is never read",
    },
    {
        "feature": "prior_wind_kmph",
        "type": "numeric",
        "source": "observations_synthetic.csv (observed_wind_kmph, lead 24 series)",
        "timing": "Latest observation strictly before D",
        "leakage_safeguard": "Window is `date < D`",
    },
    {
        "feature": "prior_rain_1d_mm",
        "type": "numeric",
        "source": "observations_synthetic.csv (observed_rain_mm, lead 24 series)",
        "timing": "Observation on D-1 only",
        "leakage_safeguard": "Lag-1 shift: uses dates strictly earlier than D",
    },
    {
        "feature": "prior_rain_3d_total_mm",
        "type": "numeric",
        "source": "observations_synthetic.csv (lead 24 series)",
        "timing": "Sum over [D-3, D-1]",
        "leakage_safeguard": "Rolling window ends at D-1",
    },
    {
        "feature": "prior_rain_3d_mean_mm",
        "type": "numeric",
        "source": "observations_synthetic.csv (lead 24 series)",
        "timing": "Mean over [D-3, D-1]",
        "leakage_safeguard": "Rolling window ends at D-1",
    },
    {
        "feature": "prior_rain_7d_total_mm",
        "type": "numeric",
        "source": "observations_synthetic.csv (lead 24 series)",
        "timing": "Sum over [D-7, D-1]",
        "leakage_safeguard": "Rolling window ends at D-1",
    },
    {
        "feature": "prior_rain_7d_mean_mm",
        "type": "numeric",
        "source": "observations_synthetic.csv (lead 24 series)",
        "timing": "Mean over [D-7, D-1]",
        "leakage_safeguard": "Rolling window ends at D-1",
    },
    {
        "feature": "nwp_prior_ok_ratio",
        "type": "numeric",
        "source": "historical_forecasts_synthetic.csv (status column, nwp_model_a)",
        "timing": "Share of status=='ok' rows over [D-14, D-1]",
        "leakage_safeguard": "Forecast-status only (no observations); window strictly before D",
    },
    {
        "feature": "ensemble_prior_ok_ratio",
        "type": "numeric",
        "source": "historical_forecasts_synthetic.csv (status column, ensemble_mean)",
        "timing": "Share of status=='ok' rows over [D-14, D-1]",
        "leakage_safeguard": "Forecast-status only (no observations); window strictly before D",
    },
    {
        "feature": "month",
        "type": "numeric",
        "source": "calendar derivation from valid_date",
        "timing": "Known at issue time",
        "leakage_safeguard": "Pure calendar feature",
    },
    {
        "feature": "lead_hours",
        "type": "numeric",
        "source": "request parameter (6 / 24 / 72)",
        "timing": "Known at issue time",
        "leakage_safeguard": "Configuration value",
    },
    {
        "feature": "district",
        "type": "categorical",
        "source": "districts.csv (district_id)",
        "timing": "Known at issue time",
        "leakage_safeguard": "One-hot encoded with train-fitted categories (handle_unknown='ignore')",
    },
    {
        "feature": "season",
        "type": "categorical",
        "source": "calendar derivation from valid_date month",
        "timing": "Known at issue time",
        "leakage_safeguard": "Pure calendar feature (Monsoon/Post-monsoon/Winter/Pre-monsoon)",
    },
]


@dataclass
class FeatureRow:
    """One (district, date, lead) feature vector plus its availability verdict."""

    district_id: str
    valid_date: str
    lead_hours: int
    features: dict = field(default_factory=dict)
    feature_availability: str = FEATURE_AVAILABILITY_OK
    feature_skip_reason: str | None = None
    prior_observation_days: int = 0
    target_mm: float | None = None

    @property
    def is_usable(self) -> bool:
        return self.feature_availability == FEATURE_AVAILABILITY_OK


def _as_float(value) -> float | None:
    """Finite-float guard (local copy so this module stays import-cycle free)."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def season_for_month(month: int) -> str:
    """Calendar season used as a categorical feature."""
    if month in (6, 7, 8, 9):
        return "Monsoon"
    if month in (10, 11):
        return "Post-monsoon"
    if month in (12, 1, 2):
        return "Winter"
    return "Pre-monsoon"


def _usable_rain(value, cfg: Settings) -> float | None:
    number = _as_float(value)
    if number is None or not (0.0 <= number <= cfg.max_plausible_rain_mm):
        return None
    return number


def _prior_status_ratio(
    forecasts: pd.DataFrame, source_id: str, as_of: pd.Timestamp, window_days: int
) -> float | None:
    """Share of status=='ok' rows for a source over [D-window, D) — strictly before D."""
    dates = pd.to_datetime(forecasts["valid_date"], errors="coerce")
    mask = (
        (forecasts["source_id"].astype(str) == source_id)
        & (dates < as_of)
        & (dates >= as_of - pd.Timedelta(days=window_days))
    )
    window = forecasts[mask]
    if not len(window):
        return None
    status = window["status"].astype(str)
    return float((status == "ok").sum()) / float(len(status))


def build_feature_row(
    ds,
    *,
    district_id: str,
    valid_date: str,
    lead_hours: int,
    cfg: Settings | None = None,
) -> FeatureRow:
    """Compose the feature vector for one point from strictly prior inputs."""
    s = cfg or default_settings
    as_of = pd.to_datetime(valid_date)
    if pd.isna(as_of):
        return FeatureRow(
            district_id=district_id,
            valid_date=str(valid_date),
            lead_hours=lead_hours,
            feature_availability=FEATURE_AVAILABILITY_MISSING_FORECAST,
            feature_skip_reason=f"Unparseable valid_date '{valid_date}'.",
        )
    date_str = as_of.strftime("%Y-%m-%d")

    row = FeatureRow(district_id=district_id, valid_date=date_str, lead_hours=lead_hours)

    # --- 1. forecast-side inputs for D (issued at D - lead) ---------------------
    fc_mask = (
        (ds.forecasts["district_id"].astype(str) == district_id)
        & (pd.to_numeric(ds.forecasts["lead_hours"], errors="coerce") == lead_hours)
        & (pd.to_datetime(ds.forecasts["valid_date"], errors="coerce") == as_of)
    )
    fc_rows = {str(r["source_id"]): r for r in ds.forecasts[fc_mask].to_dict("records")}

    def _raw(source_id: str) -> float | None:
        rec = fc_rows.get(source_id)
        if rec is None or str(rec.get("status")) in ("unavailable", "anomalous"):
            return None
        return _usable_rain(rec.get("forecast_rain_mm"), s)

    nwp = _raw("nwp_model_a")
    ens = _raw("ensemble_mean")
    if nwp is None or ens is None:
        row.feature_availability = FEATURE_AVAILABILITY_MISSING_FORECAST
        missing = [
            name
            for name, value in (("nwp_model_a", nwp), ("ensemble_mean", ens))
            if value is None
        ]
        row.feature_skip_reason = (
            f"Forecast input(s) missing/unusable for {', '.join(missing)} at "
            f"{district_id} {date_str} {lead_hours}h."
        )
        return row

    ens_rec = fc_rows.get("ensemble_mean") or {}
    spread = _as_float(ens_rec.get("ensemble_spread_mm"))

    # --- 2. strictly-prior observation history (lead-24 daily series) -----------
    obs = ds.observations[
        (ds.observations["district_id"].astype(str) == district_id)
        & (pd.to_numeric(ds.observations["lead_hours"], errors="coerce") == 24)
    ].copy()
    obs["_date"] = pd.to_datetime(obs["valid_date"], errors="coerce")
    obs = obs[obs["_date"] < as_of].sort_values("_date")  # STRICTLY before D
    obs["_rain"] = obs["observed_rain_mm"].map(lambda v: _usable_rain(v, s))
    usable = obs[obs["_rain"].notna()]
    prior_days = int(usable["_date"].nunique())
    row.prior_observation_days = prior_days

    if prior_days < int(s.ml_min_feature_history_days):
        row.feature_availability = FEATURE_AVAILABILITY_INSUFFICIENT_HISTORY
        row.feature_skip_reason = (
            f"Only {prior_days} prior usable observation day(s) before {date_str}; "
            f"{s.ml_min_feature_history_days} required for rolling features."
        )
        return row

    def _window(days: int) -> pd.DataFrame:
        start = as_of - pd.Timedelta(days=days)
        return usable[(usable["_date"] >= start) & (usable["_date"] < as_of)]

    w3, w7 = _window(3), _window(7)
    w1 = usable[usable["_date"] == as_of - pd.Timedelta(days=1)]

    # latest strictly-prior temperature / wind (walk back over prior rows)
    prior_temp = prior_wind = None
    for rec in obs.sort_values("_date", ascending=False).head(5).to_dict("records"):
        if prior_temp is None:
            prior_temp = _as_float(rec.get("observed_temp_c"))
        if prior_wind is None:
            prior_wind = _as_float(rec.get("observed_wind_kmph"))
        if prior_temp is not None and prior_wind is not None:
            break

    r3 = pd.to_numeric(w3["_rain"], errors="coerce").dropna()
    r7 = pd.to_numeric(w7["_rain"], errors="coerce").dropna()
    r1 = pd.to_numeric(w1["_rain"], errors="coerce").dropna()

    # --- 3. calendar / configuration features -----------------------------------
    month = int(as_of.month)
    nwp_ok = _prior_status_ratio(
        ds.forecasts, "nwp_model_a", as_of, s.source_health_window_days
    )
    ensemble_ok = _prior_status_ratio(
        ds.forecasts, "ensemble_mean", as_of, s.source_health_window_days
    )

    row.features = {
        "nwp_rain_mm": nwp,
        "ensemble_mean_mm": ens,
        "ensemble_spread_mm": spread if spread is not None else float("nan"),
        "prior_temp_c": prior_temp if prior_temp is not None else float("nan"),
        "prior_wind_kmph": prior_wind if prior_wind is not None else float("nan"),
        "prior_rain_1d_mm": float(r1.iloc[0]) if len(r1) else float("nan"),
        "prior_rain_3d_total_mm": float(r3.sum()) if len(r3) else float("nan"),
        "prior_rain_3d_mean_mm": float(r3.mean()) if len(r3) else float("nan"),
        "prior_rain_7d_total_mm": float(r7.sum()) if len(r7) else float("nan"),
        "prior_rain_7d_mean_mm": float(r7.mean()) if len(r7) else float("nan"),
        "nwp_prior_ok_ratio": nwp_ok if nwp_ok is not None else float("nan"),
        "ensemble_prior_ok_ratio": (
            ensemble_ok if ensemble_ok is not None else float("nan")
        ),
        "month": float(month),
        "lead_hours": float(lead_hours),
        "district": district_id,
        "season": season_for_month(month),
    }

    # --- 4. target (kept out of the feature vectors entirely) --------------------
    target_rows = ds.observations[
        (ds.observations["district_id"].astype(str) == district_id)
        & (pd.to_numeric(ds.observations["lead_hours"], errors="coerce") == lead_hours)
        & (pd.to_datetime(ds.observations["valid_date"], errors="coerce") == as_of)
    ]
    if len(target_rows):
        row.target_mm = _usable_rain(target_rows.iloc[0].get("observed_rain_mm"), s)

    return row


def build_feature_frame(
    ds, *, lead_hours: int, cfg: Settings | None = None
) -> pd.DataFrame:
    """All (district, date) feature rows for one lead, chronological by date.

    The target column is attached for training use only; rows whose features
    are unusable stay in the frame with their ``feature_availability`` flag so
    training reports exactly how many rows were excluded and why.
    """
    s = cfg or default_settings
    districts = sorted(ds.districts["district_id"].astype(str).unique())
    dates = sorted(
        {
            d.strftime("%Y-%m-%d")
            for d in pd.to_datetime(ds.forecasts["valid_date"], errors="coerce")
            .dropna()
            .unique()
        }
    )

    records: list[dict] = []
    for date in dates:
        for district in districts:
            row = build_feature_row(
                ds, district_id=district, valid_date=date, lead_hours=lead_hours, cfg=s
            )
            record = {
                "district_id": row.district_id,
                "valid_date": row.valid_date,
                "lead_hours": row.lead_hours,
                **row.features,  # may be {} when unavailable — filled with NaN below
                TARGET_COLUMN: row.target_mm,
                "feature_availability": row.feature_availability,
                "feature_skip_reason": row.feature_skip_reason,
                "prior_observation_days": row.prior_observation_days,
            }
            for column in FEATURE_COLUMNS:
                record.setdefault(column, float("nan"))
            records.append(record)

    frame = pd.DataFrame.from_records(records)
    # Chronological order is guaranteed by the sorted date loop.
    return frame
