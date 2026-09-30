"""Chronological walk-forward backtesting engine (Phase 3).

For every date D in the requested inclusive range the engine:

1. fetches the observation and the forecast records for (district, D, lead),
2. skips D with an explicit reason when data is missing/invalid/insufficient,
3. otherwise runs the existing Phase 2 Forecast Intelligence Engine in
   strictly historical mode (bias, skill, health and regime context all stop
   strictly before D — never the observation of D itself),
4. records predictions for five methods: NWP bias-corrected, Ensemble,
   AI local correction, Equal-weight average and the VARSHA dynamic blend.

The observation of D is used **only as the verification truth** for metrics,
never as an input to any prediction. Normal backtest runs never mutate the
stored forecast data.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

import pandas as pd

from ..config import Settings, settings as default_settings
from .forecast_engine import (
    ForecastDateOutOfRangeError,
    ForecastUnavailableError,
    _as_float,  # finite-float guard already used by the Phase 2 engine
    run_forecast,
)
from .model_inference import FALLBACK_LABEL, MODEL_LABEL
from .metrics import (
    METHOD_KEYS,
    EventMetrics,
    RegressionMetrics,
    build_comparison,
    event_metrics,
    regression_metrics,
)

# --- skip reasons (stable identifiers used in rows, CSV and API responses) ------------
SKIP_MISSING_OBSERVATION = "missing_observation"
SKIP_MISSING_FORECAST = "missing_forecast"
SKIP_INVALID_DATA = "invalid_data"
SKIP_INSUFFICIENT_HISTORY = "insufficient_history"
SKIP_NO_VALID_SOURCE = "no_valid_source"

SKIP_REASONS: tuple[str, ...] = (
    SKIP_MISSING_OBSERVATION,
    SKIP_MISSING_FORECAST,
    SKIP_INVALID_DATA,
    SKIP_INSUFFICIENT_HISTORY,
    SKIP_NO_VALID_SOURCE,
)

SKIP_REASON_NOTES: dict[str, str] = {
    SKIP_MISSING_OBSERVATION: "No observation exists for this district, date and lead_hours.",
    SKIP_MISSING_FORECAST: "No forecast record exists for this district, date and lead_hours.",
    SKIP_INVALID_DATA: "The observation value is malformed or implausible for this row.",
    SKIP_INSUFFICIENT_HISTORY: "Prior usable history is below minimum_history_days.",
    SKIP_NO_VALID_SOURCE: "The forecast engine found no usable source for this point.",
}

SOURCE_ALIASES: dict[str, str] = {
    "nwp_model_a": "nwp",
    "ensemble_mean": "ensemble",
    "ai_local_v1": "ai_local",
}


# --------------------------------------------------------------------------------------
# Result containers (full precision — rounding happens only at the API edge)
# --------------------------------------------------------------------------------------
@dataclass
class BacktestRow:
    """One evaluated (or skipped) date in the walk-forward run."""

    date: str
    district_id: str
    district_name: str
    lead_hours: int
    actual_mm: float | None
    predictions: dict[str, float | None] = field(
        default_factory=lambda: {k: None for k in METHOD_KEYS}
    )
    prior_history_days: int = 0
    regime: str | None = None
    weights: dict[str, float | None] = field(default_factory=dict)
    confidence_score: float | None = None
    confidence_label: str | None = None
    risk_level: str | None = None
    fallback_mode: str | None = None
    source_health: dict[str, str] = field(default_factory=dict)
    included_in_evaluation: bool = False
    skip_reason: str | None = None
    # --- Phase 4 AI-source provenance (which input fed the ai_local method) ------
    ai_source_label: str | None = None
    ai_model_version: str | None = None


@dataclass
class BacktestResult:
    """Full output of one backtest run (raw precision, ready for reports)."""

    district_id: str
    district_name: str
    lead_hours: int
    start_date: str
    end_date: str
    minimum_history_days: int
    configured_threshold_mm: float
    event_threshold_mm: float
    threshold_scaling_applied: bool
    rows: list[BacktestRow]
    regression: dict[str, RegressionMetrics]
    events: dict[str, EventMetrics]
    comparison: dict
    total_requested_dates: int
    evaluated_dates: int
    skipped_dates: int
    skipped_reason_counts: dict[str, int]
    sufficient_sample_warning: str | None
    dataset_first_date: str
    dataset_last_date: str
    dates_in_dataset_range: int
    data_mode: str
    disclaimer: str
    algorithm_version: str
    config_version: str
    limitations: list[str]
    #: Phase 4 summary: trained model vs fallback precomputed AI source per row.
    ai_source_provenance: dict = field(default_factory=dict)


def default_limitations(cfg: Settings) -> list[str]:
    """Static caveats attached to every backtest response and report file."""
    return [
        cfg.backtest_disclaimer,
        "Metrics are computed from a controlled synthetic development dataset for "
        "development and testing only; they are not operational skill scores.",
        "Strict chronological walk-forward: each date uses only records strictly "
        "earlier than that date for bias, skill, regime context and dynamic "
        "weights — the observation of the evaluated date is used only as "
        "verification truth.",
        "Single deterministic dataset and single period — no cross-validation or "
        "multi-season sampling; results may differ on other data.",
        "Heavy-rain event metrics can be statistically weak when few events occur; "
        "precision, recall and F1 must be read together with the event count.",
        "This evaluation is not an official-warning verification and makes no claim "
        "against IMD/NCMRWF products or thresholds.",
        "The 64.5 mm heavy-rain threshold is a configurable prototype default, not "
        "an official warning threshold.",
    ]


# --------------------------------------------------------------------------------------
# Per-date helpers
# --------------------------------------------------------------------------------------
def ai_provenance_summary(rows: list[BacktestRow]) -> dict:
    """Aggregate per-row AI-source labels into a run-level provenance block (Phase 4).

    Explicitly records whether the ``ai_local`` method predictions came from the
    trained local correction model or from the precomputed synthetic fallback —
    so historical metrics are never silently attributed to the wrong input.
    """
    evaluated = [r for r in rows if r.included_in_evaluation]
    labels: dict[str, int] = {}
    for row in evaluated:
        if row.ai_source_label:
            labels[row.ai_source_label] = labels.get(row.ai_source_label, 0) + 1
    model_rows = labels.get(MODEL_LABEL, 0)
    fallback_rows = labels.get(FALLBACK_LABEL, 0)
    versions = sorted({r.ai_model_version for r in evaluated if r.ai_model_version})
    primary = max(labels, key=lambda key: labels[key]) if labels else None
    return {
        "source_label": primary,
        "model_inference_available": model_rows > 0,
        "labels_used": labels,
        "rows_using_trained_model": model_rows,
        "rows_using_fallback_source": fallback_rows,
        "mixed_inputs": len(labels) > 1,
        "model_versions": versions,
        "note": (
            "Per-row ai_local input: 'trained_local_correction_model' when the "
            "trained artifact answered for that point, else the disclosed "
            "'fallback_precomputed_ai_source'. The artifact is trained once from "
            "a controlled chronological dataset split via POST /model/train; "
            "full rolling-origin ML retraining per backtest date is future scope "
            "(not in this MVP)."
        ),
    }


def _observation_lookup(ds, district_id: str, lead_hours: int, cfg: Settings):
    """Map date -> (row_found, plausible_value_or_None) for one point."""
    obs = ds.observations[
        (ds.observations["district_id"].astype(str) == district_id)
        & (pd.to_numeric(ds.observations["lead_hours"], errors="coerce") == lead_hours)
    ]
    table: dict[str, tuple[bool, float | None]] = {}
    for row in obs.to_dict("records"):
        key = pd.to_datetime(row.get("valid_date"), errors="coerce")
        if pd.isna(key):
            continue
        value = _as_float(row.get("observed_rain_mm"))
        plausible = (
            value is not None and 0.0 <= value <= cfg.max_plausible_rain_mm
        )
        table[key.strftime("%Y-%m-%d")] = (True, value if plausible else None)
    return table


def _forecast_dates(ds, district_id: str, lead_hours: int) -> set[str]:
    fc = ds.forecasts[
        (ds.forecasts["district_id"].astype(str) == district_id)
        & (pd.to_numeric(ds.forecasts["lead_hours"], errors="coerce") == lead_hours)
    ]
    parsed = pd.to_datetime(fc["valid_date"], errors="coerce").dropna()
    return {ts.strftime("%Y-%m-%d") for ts in parsed}


def _evaluate_date(
    ds,
    *,
    date: str,
    district_id: str,
    district_name: str,
    lead_hours: int,
    obs_table: dict[str, tuple[bool, float | None]],
    fc_date_set: set[str],
    prior_common: list[str],
    minimum_history_days: int,
    cfg: Settings,
) -> BacktestRow:
    """Run one walk-forward step, returning an included or skipped row."""
    row = BacktestRow(
        date=date,
        district_id=district_id,
        district_name=district_name,
        lead_hours=lead_hours,
        actual_mm=None,
    )

    # 1. observation must exist ------------------------------------------------------
    obs_entry = obs_table.get(date)
    if obs_entry is None:
        row.skip_reason = SKIP_MISSING_OBSERVATION
        return row
    obs_found, obs_value = obs_entry
    if not obs_found:
        row.skip_reason = SKIP_MISSING_OBSERVATION
        return row

    # 2. forecast record(s) must exist ----------------------------------------------
    if date not in fc_date_set:
        row.skip_reason = SKIP_MISSING_FORECAST
        return row

    # 3. observation must be plausible ----------------------------------------------
    if obs_value is None:
        row.skip_reason = SKIP_INVALID_DATA
        return row
    row.actual_mm = obs_value

    # 4. prior history must cover minimum_history_days -------------------------------
    prior_days = bisect.bisect_left(prior_common, date)
    row.prior_history_days = prior_days
    if prior_days < minimum_history_days:
        row.skip_reason = SKIP_INSUFFICIENT_HISTORY
        return row

    # 5. Phase 2 engine in strictly historical mode ----------------------------------
    try:
        result = run_forecast(
            ds,
            district_id=district_id,
            district_name=district_name,
            valid_date=date,
            lead_hours=lead_hours,
            cfg=cfg,
        )
    except (ForecastUnavailableError, ForecastDateOutOfRangeError):
        row.skip_reason = SKIP_NO_VALID_SOURCE
        return row

    # --- method predictions ---------------------------------------------------------
    by_alias: dict[str, float | None] = {}
    usable_corrected: list[float] = []
    for source_id, alias in SOURCE_ALIASES.items():
        source = next((sf for sf in result.sources if sf.source_id == source_id), None)
        corrected = (
            source.corrected_forecast_mm
            if source is not None
            and source.value_usable
            and source.corrected_forecast_mm is not None
            else None
        )
        by_alias[alias] = corrected
        if corrected is not None:
            usable_corrected.append(float(corrected))

    assert result.blend is not None
    assert result.confidence is not None
    assert result.risk is not None
    assert result.regime is not None

    row.predictions = {
        "nwp": by_alias.get("nwp"),
        "ensemble": by_alias.get("ensemble"),
        "ai_local": by_alias.get("ai_local"),
        "equal_weight": (
            sum(usable_corrected) / len(usable_corrected) if usable_corrected else None
        ),
        "varsha_dynamic_blend": float(result.blend.final_rainfall_mm),
    }
    row.regime = result.regime.label
    row.weights = {
        alias: float(next(sf.weight for sf in result.sources if sf.source_id == sid))
        for sid, alias in SOURCE_ALIASES.items()
    }
    row.confidence_score = float(result.confidence.score)
    row.confidence_label = result.confidence.label
    row.risk_level = result.risk.risk_level
    row.fallback_mode = result.blend.fallback_mode
    row.source_health = {
        h.source_id: str(h.status) for h in result.source_health
    }
    provenance = result.ai_source_provenance or {}
    row.ai_source_label = provenance.get("source_label")
    row.ai_model_version = provenance.get("model_version")
    row.included_in_evaluation = True
    return row


# --------------------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------------------
def run_backtest(
    ds,
    *,
    district_id: str,
    district_name: str,
    lead_hours: int,
    start_date: str,
    end_date: str,
    minimum_history_days: int | None = None,
    heavy_rain_threshold_mm: float | None = None,
    cfg: Settings | None = None,
) -> BacktestResult:
    """Chronological walk-forward evaluation over an inclusive date range."""
    s = cfg or default_settings
    min_hist = (
        int(minimum_history_days)
        if minimum_history_days is not None
        else int(s.default_minimum_history_days)
    )
    configured_thr = (
        float(heavy_rain_threshold_mm)
        if heavy_rain_threshold_mm is not None
        else float(s.base_thresholds_24h_mm["heavy"])
    )
    scaling = bool(s.scale_thresholds_by_lead)
    effective_thr = configured_thr * (lead_hours / 24.0) if scaling else configured_thr

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    dates = [ts.strftime("%Y-%m-%d") for ts in pd.date_range(start, end, freq="D")]

    # --- precomputed lookups (built once per run) -----------------------------------
    obs_table = _observation_lookup(ds, district_id, lead_hours, s)
    fc_date_set = _forecast_dates(ds, district_id, lead_hours)
    prior_common = sorted(
        set(fc_date_set)
        & {d for d, (found, value) in obs_table.items() if found and value is not None}
    )

    fc_all = pd.to_datetime(ds.forecasts["valid_date"], errors="coerce").dropna()
    dataset_first = min(fc_all).strftime("%Y-%m-%d")
    dataset_last = max(fc_all).strftime("%Y-%m-%d")
    dates_in_range = sum(dataset_first <= d <= dataset_last for d in dates)

    rows: list[BacktestRow] = []
    for date in dates:
        rows.append(
            _evaluate_date(
                ds,
                date=date,
                district_id=district_id,
                district_name=district_name,
                lead_hours=lead_hours,
                obs_table=obs_table,
                fc_date_set=fc_date_set,
                prior_common=prior_common,
                minimum_history_days=min_hist,
                cfg=s,
            )
        )

    included = [r for r in rows if r.included_in_evaluation]
    skipped = [r for r in rows if not r.included_in_evaluation]

    # --- metrics per method (only rows where that method produced a prediction) ------
    regression: dict[str, RegressionMetrics] = {}
    events: dict[str, EventMetrics] = {}
    for method in METHOD_KEYS:
        pairs = [
            (r.predictions.get(method), r.actual_mm)
            for r in included
            if r.predictions.get(method) is not None and r.actual_mm is not None
        ]
        regression[method] = regression_metrics(pairs)
        events[method] = event_metrics(pairs, effective_thr, s)

    comparison = build_comparison(regression, events, len(included), s)

    reason_counts = {reason: 0 for reason in SKIP_REASONS}
    for r in skipped:
        if r.skip_reason:
            reason_counts[r.skip_reason] = reason_counts.get(r.skip_reason, 0) + 1

    sufficient_warning = comparison["note"]

    return BacktestResult(
        district_id=district_id,
        district_name=district_name,
        lead_hours=lead_hours,
        start_date=start_date,
        end_date=end_date,
        minimum_history_days=min_hist,
        configured_threshold_mm=configured_thr,
        event_threshold_mm=effective_thr,
        threshold_scaling_applied=scaling,
        rows=rows,
        regression=regression,
        events=events,
        comparison=comparison,
        total_requested_dates=len(dates),
        evaluated_dates=len(included),
        skipped_dates=len(skipped),
        skipped_reason_counts=reason_counts,
        sufficient_sample_warning=sufficient_warning,
        dataset_first_date=dataset_first,
        dataset_last_date=dataset_last,
        dates_in_dataset_range=dates_in_range,
        data_mode=s.data_mode,
        disclaimer=s.backtest_disclaimer,
        algorithm_version=s.algorithm_version,
        config_version=s.config_version,
        limitations=default_limitations(s),
        ai_source_provenance=ai_provenance_summary(rows),
    )
