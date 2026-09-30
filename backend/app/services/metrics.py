"""Regression and heavy-rain event metrics for Phase-3 backtesting.

Every function here is pure: it consumes computed (prediction, actual) pairs
and returns full-precision numbers. Nothing is hardcoded, rounded or tuned to
make any method look better. Empty inputs and zero-division cases return
``None`` with an explanatory note instead of crashing or inventing zeros.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..config import Settings, settings as default_settings

#: Methods evaluated by the backtest (order is display order).
METHOD_KEYS: tuple[str, ...] = (
    "nwp",
    "ensemble",
    "ai_local",
    "equal_weight",
    "varsha_dynamic_blend",
)

METHOD_DISPLAY: dict[str, str] = {
    "nwp": "NWP bias-corrected",
    "ensemble": "Ensemble forecast",
    "ai_local": "AI local correction",
    "equal_weight": "Equal-weight average",
    "varsha_dynamic_blend": "VARSHA dynamic blend",
}

#: Standalone single-source methods (used for the "best single source" baseline).
SINGLE_SOURCE_METHODS: tuple[str, ...] = ("nwp", "ensemble", "ai_local")

EMPTY_REGRESSION_NOTE = "No evaluated rows for this method; metrics are null."
EMPTY_EVENT_NOTE = "No evaluated rows for this method; event metrics are null."

INSUFFICIENT_SAMPLE_NOTE = "Insufficient evaluation sample for reliable comparison."


def _clean_pairs(pairs) -> list[tuple[float, float]]:
    """Keep finite (prediction, actual) pairs only; None/NaN never enter metrics."""
    clean: list[tuple[float, float]] = []
    for prediction, actual in pairs:
        if prediction is None or actual is None:
            continue
        try:
            p = float(prediction)
            a = float(actual)
        except (TypeError, ValueError):
            continue
        if math.isnan(p) or math.isnan(a) or math.isinf(p) or math.isinf(a):
            continue
        clean.append((p, a))
    return clean


# --------------------------------------------------------------------------------------
# Regression metrics (spec B)
# --------------------------------------------------------------------------------------
@dataclass
class RegressionMetrics:
    """MAE / RMSE / MBE / median AE / max AE over evaluated rows (full precision)."""

    sample_count: int = 0
    mae_mm: float | None = None
    rmse_mm: float | None = None
    mean_bias_error_mm: float | None = None
    median_absolute_error_mm: float | None = None
    max_absolute_error_mm: float | None = None
    note: str | None = None


def regression_metrics(pairs) -> RegressionMetrics:
    """Compute regression metrics from (prediction, actual) pairs in mm.

    * MAE      = mean(|prediction - actual|)
    * RMSE     = sqrt(mean((prediction - actual)^2))
    * MBE      = mean(prediction - actual)  — positive means over-prediction
    * MedianAE = median(|prediction - actual|)
    * MaxAE    = max(|prediction - actual|)

    With no usable pairs every metric is ``None`` and ``note`` explains why.
    """
    clean = _clean_pairs(pairs)
    if not clean:
        return RegressionMetrics(sample_count=0, note=EMPTY_REGRESSION_NOTE)

    errors = [p - a for p, a in clean]
    abs_errors = [abs(e) for e in errors]
    n = len(errors)

    return RegressionMetrics(
        sample_count=n,
        mae_mm=sum(abs_errors) / n,
        rmse_mm=math.sqrt(sum(e * e for e in errors) / n),
        mean_bias_error_mm=sum(errors) / n,
        median_absolute_error_mm=_median(abs_errors),
        max_absolute_error_mm=max(abs_errors),
        note=None,
    )


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


# --------------------------------------------------------------------------------------
# Heavy-rain event metrics (spec C)
# --------------------------------------------------------------------------------------
@dataclass
class EventMetrics:
    """Confusion matrix and scores for one method at one event threshold."""

    threshold_mm: float
    sample_count: int = 0
    event_count: int | None = None  # observed events (TP + FN)
    predicted_event_count: int | None = None  # TP + FP
    true_positives: int | None = None
    false_positives: int | None = None
    true_negatives: int | None = None
    false_negatives: int | None = None
    precision: float | None = None
    recall: float | None = None
    f1_score: float | None = None
    false_alarm_rate: float | None = None
    missed_event_rate: float | None = None
    notes: list[str] = field(default_factory=list)
    low_event_sample_warning: str | None = None


def event_metrics(pairs, threshold_mm: float, cfg: Settings | None = None) -> EventMetrics:
    """Confusion matrix + precision/recall/F1 for rainfall >= threshold.

    The *same* effective threshold is applied to the observed value and to the
    prediction. Zero-division cases (e.g. nothing ever predicted) yield
    ``None`` for the affected score plus an explanatory note — never a fake 0.
    """
    s = cfg or default_settings
    clean = _clean_pairs(pairs)
    if not clean:
        return EventMetrics(
            threshold_mm=float(threshold_mm), sample_count=0, notes=[EMPTY_EVENT_NOTE]
        )

    thr = float(threshold_mm)
    tp = fp = tn = fn = 0
    for p, a in clean:
        pred_event = p >= thr
        obs_event = a >= thr
        if obs_event and pred_event:
            tp += 1
        elif pred_event:
            fp += 1
        elif obs_event:
            fn += 1
        else:
            tn += 1

    n = len(clean)
    notes: list[str] = []

    precision: float | None = None
    if tp + fp > 0:
        precision = tp / (tp + fp)
    else:
        notes.append(
            f"Precision undefined (TP+FP = 0): the method predicted no events "
            f"at the {thr:g} mm threshold."
        )

    recall: float | None = None
    missed: float | None = None
    if tp + fn > 0:
        recall = tp / (tp + fn)
        missed = fn / (tp + fn)
    else:
        notes.append(
            f"Recall and missed-event rate undefined (TP+FN = 0): no events were "
            f"observed at the {thr:g} mm threshold."
        )

    f1: float | None = None
    if precision is not None and recall is not None:
        if precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            notes.append(
                "F1 undefined (precision + recall = 0): the method detected no "
                "events and made no correct event predictions."
            )
    else:
        notes.append("F1 undefined because precision or recall is undefined.")

    far: float | None = None
    if fp + tn > 0:
        far = fp / (fp + tn)
    else:
        notes.append(
            f"False-alarm rate undefined (FP+TN = 0): every evaluated row was an "
            f"event at the {thr:g} mm threshold."
        )

    event_count = tp + fn
    warning: str | None = None
    if event_count < int(s.low_event_sample_threshold):
        warning = (
            f"Event sample is small ({event_count} observed event(s) < "
            f"{s.low_event_sample_threshold}): event metrics are statistically "
            "weak and must not be read as verification skill."
        )

    return EventMetrics(
        threshold_mm=thr,
        sample_count=n,
        event_count=event_count,
        predicted_event_count=tp + fp,
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1_score=f1,
        false_alarm_rate=far,
        missed_event_rate=missed,
        notes=notes,
        low_event_sample_warning=warning,
    )


# --------------------------------------------------------------------------------------
# Honest baseline comparison (spec D)
# --------------------------------------------------------------------------------------
def _best_method(
    values: dict[str, float | None], *, mode: str = "min", absolute: bool = False
) -> str | None:
    """Select the best method from computed values only (never assumed)."""
    candidates: list[tuple[str, float]] = []
    for key in METHOD_KEYS:
        value = values.get(key)
        if value is None:
            continue
        score = abs(value) if absolute else value
        if math.isnan(score):
            continue
        candidates.append((key, score))
    if not candidates:
        return None
    pick = min(candidates, key=lambda kv: kv[1]) if mode == "min" else max(
        candidates, key=lambda kv: kv[1]
    )
    return pick[0]


def _verdict(delta: float | None, baseline_value: float | None, tol: float) -> str | None:
    if delta is None or baseline_value is None:
        return None
    if delta < -tol:
        return "better"
    if delta > tol:
        return "worse"
    return "similar"


def build_comparison(
    regression: dict[str, RegressionMetrics],
    events: dict[str, EventMetrics],
    evaluated_dates: int,
    cfg: Settings | None = None,
) -> dict:
    """Compare VARSHA against the baselines using only computed numbers.

    Deltas are ``VARSHA - baseline``: a negative MAE delta favours VARSHA,
    a positive recall delta favours VARSHA. ``best_method_by_metric`` is
    selected strictly from computed metric values — VARSHA is never assumed
    to win. With too few evaluated rows the outcome states the exact
    insufficient-sample sentence instead of a verdict.
    """
    s = cfg or default_settings
    tol = float(s.comparison_similar_tolerance_mm)
    sufficient = evaluated_dates >= int(s.min_comparison_sample)

    def reg(method: str) -> RegressionMetrics:
        return regression.get(method) or RegressionMetrics()

    def evt(method: str) -> EventMetrics:
        return events.get(method) or EventMetrics(threshold_mm=0.0)

    # --- best method per metric (computed values only) ------------------------------
    best_by_metric: dict[str, str | None] = {
        "mae_mm": _best_method({k: reg(k).mae_mm for k in METHOD_KEYS}, mode="min"),
        "rmse_mm": _best_method({k: reg(k).rmse_mm for k in METHOD_KEYS}, mode="min"),
        "mean_bias_error_mm": _best_method(
            {k: reg(k).mean_bias_error_mm for k in METHOD_KEYS}, mode="min", absolute=True
        ),
        "median_absolute_error_mm": _best_method(
            {k: reg(k).median_absolute_error_mm for k in METHOD_KEYS}, mode="min"
        ),
        "max_absolute_error_mm": _best_method(
            {k: reg(k).max_absolute_error_mm for k in METHOD_KEYS}, mode="min"
        ),
        "precision": _best_method({k: evt(k).precision for k in METHOD_KEYS}, mode="max"),
        "recall": _best_method({k: evt(k).recall for k in METHOD_KEYS}, mode="max"),
        "f1_score": _best_method({k: evt(k).f1_score for k in METHOD_KEYS}, mode="max"),
        "false_alarm_rate": _best_method(
            {k: evt(k).false_alarm_rate for k in METHOD_KEYS}, mode="min"
        ),
        "missed_event_rate": _best_method(
            {k: evt(k).missed_event_rate for k in METHOD_KEYS}, mode="min"
        ),
    }

    # --- best single source (lowest MAE among nwp / ensemble / ai_local) ------------
    single_maes = {k: reg(k).mae_mm for k in SINGLE_SOURCE_METHODS}
    best_single = _best_method(single_maes, mode="min")

    varsha_mae = reg("varsha_dynamic_blend").mae_mm
    equal_mae = reg("equal_weight").mae_mm
    best_single_mae = single_maes.get(best_single) if best_single else None
    varsha_recall = evt("varsha_dynamic_blend").recall
    equal_recall = evt("equal_weight").recall
    best_single_recall = evt(best_single).recall if best_single else None

    def delta(a: float | None, b: float | None) -> float | None:
        if a is None or b is None:
            return None
        return a - b

    # --- honest plain-language outcome ---------------------------------------------
    outcome: list[str] = []
    if not sufficient:
        outcome.append(INSUFFICIENT_SAMPLE_NOTE)
    else:
        verdicts = [
            _verdict(delta(varsha_mae, equal_mae), equal_mae, tol),
            _verdict(delta(varsha_mae, best_single_mae), best_single_mae, tol),
        ]
        labels = [
            "the equal-weight average",
            (
                f"the best single source ({METHOD_DISPLAY[best_single]})"
                if best_single
                else None
            ),
        ]
        for verdict, label, base_mae in zip(verdicts, labels, (equal_mae, best_single_mae)):
            if verdict is None or label is None:
                continue
            outcome.append(
                f"VARSHA performed {('similarly to' if verdict == 'similar' else verdict + ' than')} "
                f"{label} for this selected synthetic evaluation period "
                f"(MAE {varsha_mae:.3f} mm vs {base_mae:.3f} mm, "
                f"delta {delta(varsha_mae, base_mae):+.3f} mm)."
            )
        if not outcome:
            outcome.append("No comparable metrics were computed for this evaluation.")

    return {
        "delta_definition": (
            "Deltas are VARSHA minus baseline: a negative MAE delta favours "
            "VARSHA (lower error); a positive recall delta favours VARSHA "
            "(higher recall)."
        ),
        "outcome_basis": (
            f"Verdicts compare MAE with a ±{tol:g} mm similarity tolerance."
        ),
        "best_method_by_metric": best_by_metric,
        "best_single_source": best_single,
        "varsha_vs_equal_weight_mae_delta_mm": delta(varsha_mae, equal_mae),
        "varsha_vs_best_single_source_mae_delta_mm": delta(varsha_mae, best_single_mae),
        "varsha_vs_equal_weight_recall_delta": delta(varsha_recall, equal_recall),
        "varsha_vs_best_single_source_recall_delta": delta(
            varsha_recall, best_single_recall
        ),
        "sufficient_sample": sufficient,
        "note": None if sufficient else INSUFFICIENT_SAMPLE_NOTE,
        "outcome_summary": outcome,
    }
