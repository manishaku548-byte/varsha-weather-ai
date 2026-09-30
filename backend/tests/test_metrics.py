"""Phase 3 metric tests: regression math, event confusion matrix, honest comparison.

Every expected number below is computed by hand from a small known fixture.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import math

import pytest

from app.services.metrics import (
    EMPTY_EVENT_NOTE,
    EMPTY_REGRESSION_NOTE,
    INSUFFICIENT_SAMPLE_NOTE,
    METHOD_KEYS,
    EventMetrics,
    RegressionMetrics,
    build_comparison,
    event_metrics,
    regression_metrics,
)

HEAVY_MM = 64.5


# --------------------------------------------------------------------------------------
# B. Regression metrics on a known fixture
# --------------------------------------------------------------------------------------
def test_regression_metrics_known_fixture():
    # errors = pred-actual = [2, -7, 0, -2]; |errors| = [2, 7, 0, 2]
    pairs = [(10.0, 8.0), (5.0, 12.0), (20.0, 20.0), (7.0, 9.0)]
    m = regression_metrics(pairs)

    assert m.sample_count == 4
    assert m.mae_mm == pytest.approx((2 + 7 + 0 + 2) / 4)  # 2.75
    assert m.rmse_mm == pytest.approx(math.sqrt((4 + 49 + 0 + 4) / 4))  # sqrt(14.25)
    assert m.mean_bias_error_mm == pytest.approx((2 - 7 + 0 - 2) / 4)  # -1.75
    assert m.median_absolute_error_mm == pytest.approx(2.0)  # median [0,2,2,7]
    assert m.max_absolute_error_mm == pytest.approx(7.0)
    assert m.note is None


def test_regression_metrics_keeps_full_precision():
    m = regression_metrics([(1.23456789, 1.0)])
    assert m.mae_mm == pytest.approx(0.23456789)
    assert m.mae_mm != round(m.mae_mm, 4)  # raw data is not pre-rounded


def test_regression_metrics_empty_and_invalid_pairs():
    for pairs in ([], [(None, 10.0)], [(5.0, None)], [(float("nan"), 3.0)]):
        m = regression_metrics(pairs)
        assert m.sample_count == 0
        assert m.mae_mm is None
        assert m.rmse_mm is None
        assert m.mean_bias_error_mm is None
        assert m.median_absolute_error_mm is None
        assert m.max_absolute_error_mm is None
        assert m.note == EMPTY_REGRESSION_NOTE


# --------------------------------------------------------------------------------------
# C. Event confusion matrix on a known fixture
# --------------------------------------------------------------------------------------
def test_event_confusion_matrix_known_fixture():
    pairs = [
        (70.0, 70.0),    # TP
        (70.0, 50.0),    # FP
        (50.0, 70.0),    # FN
        (50.0, 50.0),    # TN
        (80.0, 90.0),    # TP
        (30.0, 20.0),    # TN
        (64.5, 100.0),   # TP — threshold is inclusive (>=)
        (10.0, 64.4),    # TN — just below threshold
    ]
    m = event_metrics(pairs, HEAVY_MM)

    assert m.threshold_mm == pytest.approx(HEAVY_MM)
    assert m.sample_count == 8
    assert m.true_positives == 3
    assert m.false_positives == 1
    assert m.true_negatives == 3
    assert m.false_negatives == 1
    assert m.event_count == 4
    assert m.predicted_event_count == 4
    assert m.precision == pytest.approx(0.75)       # 3/4
    assert m.recall == pytest.approx(0.75)          # 3/4
    assert m.f1_score == pytest.approx(0.75)        # harmonic mean of 0.75/0.75
    assert m.false_alarm_rate == pytest.approx(0.25)  # FP/(FP+TN) = 1/4
    assert m.missed_event_rate == pytest.approx(0.25)  # FN/(TP+FN) = 1/4


def test_event_metrics_same_threshold_for_actual_and_predicted():
    # The one threshold governs both sides of the matrix.
    m = event_metrics([(64.49, 64.49), (64.5, 64.5)], 64.5)
    assert (m.true_positives, m.false_positives, m.false_negatives, m.true_negatives) == (
        1,
        0,
        0,
        1,
    )


def test_event_metrics_zero_division_no_predicted_events():
    m = event_metrics([(10.0, 10.0), (20.0, 30.0)], HEAVY_MM)  # never predicts, never observes
    assert m.precision is None  # TP+FP = 0
    assert m.recall is None  # TP+FN = 0
    assert m.f1_score is None
    assert m.missed_event_rate is None
    assert m.false_alarm_rate == pytest.approx(0.0)  # FP/(FP+TN) = 0/2 defined
    assert any("Precision undefined" in note for note in m.notes)
    assert any("Recall" in note for note in m.notes)


def test_event_metrics_zero_division_all_rows_are_events():
    m = event_metrics([(70.0, 80.0), (90.0, 75.0)], HEAVY_MM)  # every row is an event
    assert m.false_alarm_rate is None  # FP+TN = 0
    assert any("False-alarm rate undefined" in note for note in m.notes)
    assert m.precision == pytest.approx(1.0)


def test_event_metrics_empty_rows():
    m = event_metrics([], HEAVY_MM)
    assert m.sample_count == 0
    assert m.true_positives is None
    assert m.precision is None
    assert m.notes == [EMPTY_EVENT_NOTE]


def test_event_metrics_low_sample_warning():
    few = [(70.0, 70.0), (20.0, 20.0)]  # 1 observed event < 5
    m = event_metrics(few, HEAVY_MM)
    assert m.event_count == 1
    assert m.low_event_sample_warning is not None
    assert "statistically weak" in m.low_event_sample_warning

    many_pairs = (
        [(70.0, 70.0)] * 4  # 4 TP
        + [(70.0, 40.0)]  # 1 FP
        + [(40.0, 70.0)]  # 1 FN
        + [(10.0, 10.0)] * 3  # 3 TN
    )
    m2 = event_metrics(many_pairs, HEAVY_MM)  # 4 TP + 1 FN = 5 observed events
    assert m2.event_count == 5
    assert m2.low_event_sample_warning is None


# --------------------------------------------------------------------------------------
# D. Honest baseline comparison
# --------------------------------------------------------------------------------------
def _reg(mae: float) -> RegressionMetrics:
    return RegressionMetrics(
        sample_count=30,
        mae_mm=mae,
        rmse_mm=mae * 1.2,
        mean_bias_error_mm=0.1,
        median_absolute_error_mm=mae * 0.9,
        max_absolute_error_mm=mae * 3,
    )


def _evt(recall: float) -> EventMetrics:
    return EventMetrics(
        threshold_mm=HEAVY_MM,
        sample_count=30,
        event_count=10,
        precision=0.8,
        recall=recall,
        f1_score=2 * 0.8 * recall / (0.8 + recall),
        false_alarm_rate=0.2,
        missed_event_rate=1 - recall,
    )


def _comparison(maes: dict, recalls: dict, evaluated: int = 30) -> dict:
    regression = {k: _reg(maes[k]) for k in METHOD_KEYS}
    events = {k: _evt(recalls[k]) for k in METHOD_KEYS}
    return build_comparison(regression, events, evaluated)


def test_best_method_selected_from_computed_values_when_varsha_loses():
    # Ensemble is genuinely best — VARSHA must NOT be assumed to win.
    maes = {"nwp": 12.0, "ensemble": 3.0, "ai_local": 10.0, "equal_weight": 7.0,
            "varsha_dynamic_blend": 6.0}
    recalls = {"nwp": 0.5, "ensemble": 0.9, "ai_local": 0.6, "equal_weight": 0.7,
               "varsha_dynamic_blend": 0.8}
    comp = _comparison(maes, recalls)

    assert comp["best_method_by_metric"]["mae_mm"] == "ensemble"
    assert comp["best_method_by_metric"]["recall"] == "ensemble"
    assert comp["best_single_source"] == "ensemble"
    assert comp["varsha_vs_equal_weight_mae_delta_mm"] == pytest.approx(6.0 - 7.0)
    assert comp["varsha_vs_best_single_source_mae_delta_mm"] == pytest.approx(6.0 - 3.0)
    assert comp["varsha_vs_equal_weight_recall_delta"] == pytest.approx(0.1)
    assert comp["varsha_vs_best_single_source_recall_delta"] == pytest.approx(-0.1)
    assert any("better than the equal-weight average" in s for s in comp["outcome_summary"])
    assert any("worse than the best single source (Ensemble forecast)" in s
               for s in comp["outcome_summary"])
    assert comp["sufficient_sample"] is True
    assert comp["note"] is None


def test_best_method_when_varsha_wins():
    maes = {"nwp": 8.0, "ensemble": 9.0, "ai_local": 7.0, "equal_weight": 9.0,
            "varsha_dynamic_blend": 2.0}
    recalls = {k: 0.5 for k in METHOD_KEYS}
    comp = _comparison(maes, recalls)

    assert comp["best_method_by_metric"]["mae_mm"] == "varsha_dynamic_blend"
    assert comp["varsha_vs_equal_weight_mae_delta_mm"] < 0
    assert sum("performed better than" in s for s in comp["outcome_summary"]) == 2


def test_mean_bias_best_method_uses_absolute_value():
    maes = {k: 5.0 for k in METHOD_KEYS}
    regression = {k: _reg(maes[k]) for k in METHOD_KEYS}
    regression["nwp"].mean_bias_error_mm = -0.6  # smallest raw value...
    regression["ensemble"].mean_bias_error_mm = 0.2  # ...but smallest |MBE|
    for k in ("ai_local", "equal_weight", "varsha_dynamic_blend"):
        regression[k].mean_bias_error_mm = 0.4
    events = {k: _evt(0.5) for k in METHOD_KEYS}
    comp = build_comparison(regression, events, 30)
    # MBE is judged by magnitude, not by raw sign: ensemble (0.2) beats nwp (-0.6).
    assert comp["best_method_by_metric"]["mean_bias_error_mm"] == "ensemble"


def test_insufficient_sample_states_exact_sentence():
    maes = {k: 5.0 for k in METHOD_KEYS}
    comp = _comparison(maes, {k: 0.5 for k in METHOD_KEYS}, evaluated=5)
    assert comp["sufficient_sample"] is False
    assert comp["note"] == INSUFFICIENT_SAMPLE_NOTE
    assert comp["outcome_summary"] == [INSUFFICIENT_SAMPLE_NOTE]


def test_comparison_with_no_metrics_does_not_crash():
    regression = {k: RegressionMetrics() for k in METHOD_KEYS}
    events = {k: EventMetrics(threshold_mm=HEAVY_MM) for k in METHOD_KEYS}
    comp = build_comparison(regression, events, 30)
    assert comp["best_method_by_metric"]["mae_mm"] is None
    assert comp["best_single_source"] is None
    assert comp["varsha_vs_equal_weight_mae_delta_mm"] is None
    assert comp["varsha_vs_best_single_source_recall_delta"] is None
    assert comp["outcome_summary"] == [
        "No comparable metrics were computed for this evaluation."
    ]


def test_similar_verdict_within_tolerance():
    maes = {"nwp": 5.0, "ensemble": 4.0, "ai_local": 6.0, "equal_weight": 5.2,
            "varsha_dynamic_blend": 5.0}  # |delta| = 0.2 <= 0.5 tolerance
    comp = _comparison(maes, {k: 0.5 for k in METHOD_KEYS})
    assert any("performed similarly to the equal-weight average" in s
               for s in comp["outcome_summary"])
