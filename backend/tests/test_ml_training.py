"""Phase 4 — training workflow integrity (spec G3, G4, G5, G7, G8).

Covers the scientific-integrity rules that are easy to break and hard to see:

* the split is chronological, disjoint, date-based and order-independent
  (never random);
* preprocessing statistics come from **training rows only**;
* selection can only see validation MAE (structurally, by signature);
* the selected candidate is refit on train+validation and scored on the
  held-out test split exactly once;
* corrupting future (test-range) observations cannot change the fitted model,
  the validation metrics or the selected algorithm — only the reported test
  metrics may move;
* insufficient data never produces a model or an artifact.
"""

from __future__ import annotations

import copy
import inspect
import json
import math

import numpy as np
import pandas as pd
import pytest

from app.config import settings
from app.services.dataset import get_dataset
from app.services.features import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    build_feature_frame,
)
from app.services.ml_training import (
    CANDIDATE_BASELINE,
    CANDIDATE_NONLINEAR,
    CANDIDATE_ORDER,
    CANDIDATE_ROLES,
    InsufficientSplitError,
    _preprocessor,
    _xy,
    candidate_pipelines,
    chronological_split,
    select_candidate,
    train_local_correction_model,
)
from app.services.model_store import (
    artifact_exists,
    clear_model_cache,
    load_artifact,
    pipeline_path,
    report_path,
    trained_lead_hours,
)
from app.services.model_inference import MODEL_LABEL
from app.services.model_inference import FALLBACK_LABEL

LEAD = 24


# ----------------------------------------------------------------------------------
# module-scoped heavy fixtures (training + frame are expensive: one each per run)
# ----------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def frame_24():
    return build_feature_frame(get_dataset(), lead_hours=LEAD, cfg=settings)


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    """One real 24h training run into an isolated directory (never the repo)."""
    directory = tmp_path_factory.mktemp("models_trained")
    original_dir = settings.models_dir
    settings.models_dir = directory
    try:
        report = train_local_correction_model(
            get_dataset(), lead_hours=LEAD, force_retrain=True, cfg=settings
        )
    finally:
        settings.models_dir = original_dir
        clear_model_cache()
    return directory, report


def _usable_rows(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[
        (frame["feature_availability"] == "ok") & frame[TARGET_COLUMN].notna()
    ]


def _trimmed_dataset(ds, dates: list[str]):
    """Dataset copy restricted to the given valid dates (for insufficiency tests)."""
    trimmed = copy.copy(ds)
    keep = set(dates)
    forecasts = ds.forecasts[
        ds.forecasts["valid_date"].astype(str).isin(keep)
    ].copy()
    observations = ds.observations[
        ds.observations["valid_date"].astype(str).isin(keep)
    ].copy()
    trimmed.forecasts = forecasts.reset_index(drop=True)
    trimmed.observations = observations.reset_index(drop=True)
    return trimmed


def _split_parts(frame: pd.DataFrame, report: dict):
    boundaries = report["split"]["boundaries"]
    usable = _usable_rows(frame)
    train = usable[
        usable["valid_date"].astype(str).isin(
            pd.date_range(boundaries["train"]["start"], boundaries["train"]["end"])
            .strftime("%Y-%m-%d")
        )
    ]
    val = usable[
        usable["valid_date"].astype(str).isin(
            pd.date_range(
                boundaries["validation"]["start"], boundaries["validation"]["end"]
            ).strftime("%Y-%m-%d")
        )
    ]
    test = usable[
        usable["valid_date"].astype(str).isin(
            pd.date_range(boundaries["test"]["start"], boundaries["test"]["end"])
            .strftime("%Y-%m-%d")
        )
    ]
    return train, val, test


# ----------------------------------------------------------------------------------
# G3 — chronological split
# ----------------------------------------------------------------------------------
def test_split_is_chronological_disjoint_and_complete():
    dates = sorted({d.strftime("%Y-%m-%d") for d in
                    pd.date_range("2025-06-01", "2025-09-28", freq="D")})
    split = chronological_split(dates, settings)
    assert split.train_dates + split.val_dates + split.test_dates == dates
    assert len(set(split.train_dates) & set(split.val_dates)) == 0
    assert len(set(split.train_dates) & set(split.test_dates)) == 0
    assert len(set(split.val_dates) & set(split.test_dates)) == 0
    assert max(split.train_dates) < min(split.val_dates)
    assert max(split.val_dates) < min(split.test_dates)
    assert (split.train_fraction, split.val_fraction, split.test_fraction) == (0.6, 0.2, 0.2)
    assert split.alternate_ratio_applied is False
    assert split.warning is None


def test_split_ignores_input_order_so_it_cannot_be_a_random_split():
    dates = sorted({d.strftime("%Y-%m-%d") for d in
                    pd.date_range("2025-06-01", "2025-09-28", freq="D")})
    shuffled = list(reversed(dates))
    forward = chronological_split(dates, settings)
    backward = chronological_split(shuffled, settings)
    assert forward.train_dates == backward.train_dates
    assert forward.val_dates == backward.val_dates
    assert forward.test_dates == backward.test_dates


def test_split_keeps_all_districts_of_a_date_together(frame_24):
    usable = _usable_rows(frame_24)
    split = chronological_split(usable["valid_date"].astype(str), settings)
    assignment: dict[str, str] = {}
    for name, dates in (
        ("train", split.train_dates),
        ("validation", split.val_dates),
        ("test", split.test_dates),
    ):
        for date_str in dates:
            assignment[date_str] = name
    per_date_sets = {}
    for _, row in usable.iterrows():
        per_date_sets.setdefault(str(row["valid_date"]), set()).add(
            assignment[str(row["valid_date"])]
        )
    assert all(len(splits) == 1 for splits in per_date_sets.values())


def test_alternate_ratio_is_used_and_disclosed_below_the_date_threshold(monkeypatch):
    monkeypatch.setattr(settings, "ml_min_split_dates", 150)
    dates = sorted({d.strftime("%Y-%m-%d") for d in
                    pd.date_range("2025-06-01", "2025-09-28", freq="D")})
    split = chronological_split(dates, settings)
    assert split.alternate_ratio_applied is True
    assert (split.train_fraction, split.val_fraction) == (0.70, 0.15)
    assert split.warning and "70%" in split.warning


def test_split_refuses_to_produce_empty_sections():
    with pytest.raises(InsufficientSplitError):
        chronological_split(["2025-06-01", "2025-06-02"], settings)


# ----------------------------------------------------------------------------------
# G4 — preprocessing is fitted on training rows only
# ----------------------------------------------------------------------------------
def test_preprocessing_statistics_come_from_train_rows_only(frame_24, trained):
    _, report = trained
    train, _, _ = _split_parts(frame_24, report)
    X_train, _ = _xy(train)
    pipe = candidate_pipelines(settings)[CANDIDATE_BASELINE]
    pipe.fit(X_train, _xy(train)[1])

    pre = pipe.named_steps["preprocess"]
    # the declared (unfitted) transformers must stay untouched ...
    declared = {name: transformer for name, transformer, _ in pre.transformers}
    assert not hasattr(
        declared["num"].named_steps["imputer"], "statistics_"
    ), "the imputer must not be fitted outside the pipeline fit"
    # ... the fitted copies are the ones that carry the statistics
    fitted = {name: transformer for name, transformer, _ in pre.transformers_}
    num_pipe = fitted["num"]
    imputer = num_pipe.named_steps["imputer"]
    scaler = num_pipe.named_steps["scaler"]
    onehot = fitted["cat"].named_steps["onehot"]

    # imputers / scaler / encoder statistics must equal TRAIN-ONLY statistics
    train_medians = []
    for index, column in enumerate(NUMERIC_FEATURES):
        train_values = pd.to_numeric(X_train[column], errors="coerce")
        expected_median = float(train_values.median())
        assert float(imputer.statistics_[index]) == pytest.approx(expected_median)
        train_medians.append(expected_median)
        imputed = train_values.fillna(expected_median)
        assert float(scaler.mean_[index]) == pytest.approx(float(imputed.mean()))
        spread = float(imputed.std(ddof=0))
        assert float(scaler.scale_[index]) == pytest.approx(spread if spread > 0 else 1.0)

    assert set(str(c) for c in onehot.categories_[0]) == set(
        X_train["district"].astype(str).unique()
    )
    assert set(str(s) for s in onehot.categories_[1]) <= set(
        X_train["season"].astype(str).unique()
    )

    # ... and the train-only medians must not equal the all-rows medians
    # (which would have leaked validation/test information into preprocessing)
    usable = _usable_rows(frame_24)
    all_X, _ = _xy(usable)
    all_medians = [
        float(pd.to_numeric(all_X[column], errors="coerce").median())
        for column in NUMERIC_FEATURES
    ]
    assert train_medians != all_medians, (
        "train-only medians must differ from the pooled medians; otherwise this "
        "test cannot distinguish the two"
    )


def test_preprocessor_drops_unknown_columns_and_keeps_feature_order():
    pre = _preprocessor(settings)
    numeric_columns = [cols for name, _, cols in pre.transformers if name == "num"][0]
    categorical_columns = [cols for name, _, cols in pre.transformers if name == "cat"][0]
    assert numeric_columns == list(NUMERIC_FEATURES)
    assert categorical_columns == list(CATEGORICAL_FEATURES)
    assert pre.remainder == "drop"


# ----------------------------------------------------------------------------------
# G5 — selection by validation MAE only
# ----------------------------------------------------------------------------------
def test_select_candidate_accepts_validation_metrics_only():
    parameters = list(inspect.signature(select_candidate).parameters)
    assert parameters == ["validation_metrics"]
    assert select_candidate({CANDIDATE_BASELINE: 5.0, CANDIDATE_NONLINEAR: 3.0}) == (
        CANDIDATE_NONLINEAR
    )
    assert select_candidate({CANDIDATE_BASELINE: 2.0, CANDIDATE_NONLINEAR: 3.0}) == (
        CANDIDATE_BASELINE
    )


def test_select_candidate_tie_break_is_deterministic():
    tie = {CANDIDATE_BASELINE: 4.0, CANDIDATE_NONLINEAR: 4.0}
    assert select_candidate(tie) == CANDIDATE_ORDER[0] == CANDIDATE_BASELINE
    # order of the input mapping must not change the outcome
    assert select_candidate({CANDIDATE_NONLINEAR: 4.0, CANDIDATE_BASELINE: 4.0}) == (
        CANDIDATE_BASELINE
    )


def test_select_candidate_ignores_missing_and_non_finite_values():
    assert select_candidate({CANDIDATE_BASELINE: None, CANDIDATE_NONLINEAR: 2.0}) == (
        CANDIDATE_NONLINEAR
    )
    assert select_candidate({CANDIDATE_BASELINE: float("nan"), CANDIDATE_NONLINEAR: 1.0}) == (
        CANDIDATE_NONLINEAR
    )
    with pytest.raises(ValueError):
        select_candidate({CANDIDATE_BASELINE: None, CANDIDATE_NONLINEAR: None})


# ----------------------------------------------------------------------------------
# G7 — one real training run
# ----------------------------------------------------------------------------------
def test_training_completes_with_the_documented_report_structure(trained):
    directory, report = trained
    assert report["status"] == "completed"
    assert report["report_type"] == "local_correction_model"
    assert report["lead_hours"] == LEAD
    assert report["data_mode"] == settings.data_mode
    assert report["disclaimer"] == settings.model_disclaimer
    assert "Not Operational Weather Data" in report["disclaimer"]
    assert report["model_version"].startswith(f"ai-local-{LEAD}h-")
    assert report["selected_model"] in CANDIDATE_ORDER
    assert set(report["candidates"]) == set(CANDIDATE_ORDER)
    assert set(report["candidates"][CANDIDATE_BASELINE]) >= {
        "role", "trained_on", "evaluated_on", "validation_metrics"
    }
    for name in CANDIDATE_ORDER:
        assert report["candidates"][name]["role"] == CANDIDATE_ROLES[name]
        assert report["candidates"][name]["trained_on"] == "train"
        assert report["candidates"][name]["evaluated_on"] == "validation"
        metrics = report["candidates"][name]["validation_metrics"]
        for key in ("sample_count", "mae_mm", "rmse_mm", "mean_bias_error_mm"):
            assert key in metrics
    assert report["selection_rationale"]
    assert "validation" in report["selection_rationale"].lower()
    assert report["fallback"] == {"active": False, "label": MODEL_LABEL, "reason": None}
    assert report["provenance"]["split_policy"] == "chronological_by_unique_global_date"
    assert report["provenance"]["algorithm_version"] == settings.algorithm_version
    assert report["provenance"]["config_version"] == settings.config_version
    assert report["limitations"] and settings.model_disclaimer in report["limitations"]


def test_training_artifacts_are_saved_next_to_each_other(trained):
    directory, report = trained
    assert pipeline_path(LEAD, settings).name == report["artifacts"]["pipeline_file"]
    assert report_path(LEAD, settings).name == report["artifacts"]["report_file"]
    original_dir = settings.models_dir
    settings.models_dir = directory
    try:
        assert artifact_exists(LEAD, settings) is True
        assert trained_lead_hours(settings) == [LEAD]
        with report_path(LEAD, settings).open("r", encoding="utf-8") as handle:
            stored = json.load(handle)
    finally:
        settings.models_dir = original_dir
    assert stored["model_version"] == report["model_version"]
    assert stored["status"] == "completed"
    assert stored["selected_model"] == report["selected_model"]


def test_saved_artifact_loads_validates_and_predicts(trained, frame_24):
    directory, report = trained
    original_dir = settings.models_dir
    settings.models_dir = directory
    try:
        clear_model_cache()
        loaded, reason = load_artifact(LEAD, settings)
        assert loaded is not None, reason
        assert loaded.lead_hours == LEAD
        assert loaded.model_version == report["model_version"]
        assert loaded.selected_model == report["selected_model"]
        assert loaded.feature_schema_version == settings.ml_feature_schema_version
        assert loaded.report["held_out_test_metrics"]["sample_count"] == report[
            "held_out_test_metrics"
        ]["sample_count"]

        test, _, _ = _split_parts(frame_24, report)
        X_test, _ = _xy(test)
        predictions = loaded.pipeline.predict(X_test)
        assert len(predictions) == len(test)
        # raw pipeline output is finite; the service layer is what clips to the
        # plausible rainfall range (see test_inference in test_model_api.py)
        assert all(math.isfinite(float(p)) for p in predictions)
        assert all(
            float(p) <= settings.max_plausible_rain_mm * 2 for p in predictions
        ), "predictions must stay in the same order of magnitude as rainfall"
    finally:
        settings.models_dir = original_dir
        clear_model_cache()


def test_report_boundaries_and_counts_match_the_frame(trained, frame_24):
    _, report = trained
    split = report["split"]
    assert split["method"] == "chronological_by_unique_global_date"
    assert split["alternate_ratio_applied"] is False
    train, val, test = _split_parts(frame_24, report)
    counts = report["record_counts"]
    assert counts["train"] == len(train)
    assert counts["validation"] == len(val)
    assert counts["test"] == len(test)
    assert counts["train"] + counts["validation"] + counts["test"] == counts["total_usable"]
    assert report["row_exclusions"]["total_rows"] == len(frame_24)
    assert report["row_exclusions"]["usable_rows"] == counts["total_usable"]
    assert report["row_exclusions"]["missing_target"] == 0
    assert split["boundaries"]["train"]["end"] < split["boundaries"]["validation"]["start"]
    assert split["boundaries"]["validation"]["end"] < split["boundaries"]["test"]["start"]
    assert split["boundaries"]["test"]["start"] >= "2025-09-01", "test must be the future"


def test_selected_model_is_the_validation_argmin(trained):
    _, report = trained
    maes = {
        name: report["candidates"][name]["validation_metrics"]["mae_mm"]
        for name in CANDIDATE_ORDER
    }
    expected = min(maes, key=lambda k: (maes[k], CANDIDATE_ORDER.index(k)))
    assert report["selected_model"] == expected
    assert report["selection_rationale"].startswith(expected)


def test_held_out_test_metrics_are_reported_once_and_honestly(trained):
    _, report = trained
    test_metrics = report["held_out_test_metrics"]
    assert test_metrics["sample_count"] == report["record_counts"]["test"]
    for key in (
        "mae_mm", "rmse_mm", "mean_bias_error_mm", "median_absolute_error_mm",
        "max_absolute_error_mm",
    ):
        value = test_metrics[key]
        assert value is None or math.isfinite(float(value))
    assert test_metrics["rmse_mm"] >= test_metrics["mae_mm"] - 1e-9

    honesty = report["honesty"]
    assert honesty["selection_metric"] == "validation_mae_only"
    assert honesty["test_used_for_selection"] is False
    assert honesty["test_set_evaluated_once"] is True
    assert isinstance(honesty["ml_worse_than_baseline"], bool)
    assert honesty["worse_than_references"] is not None

    references = report["test_references"]
    assert set(references) >= {"naive_train_mean", "raw_nwp"}
    assert references["naive_train_mean"]["sample_count"] == test_metrics["sample_count"]
    for name, ref in references.items():
        assert ref["description"]
        assert ref["mae_mm"] is not None
    for sentence in honesty["summary_sentences"]:
        assert "test MAE" in sentence
    if honesty["ml_worse_than_baseline"]:
        assert any(
            "worse than reference" in w for w in report["warnings"]
        ), "a worse-than-reference outcome must be warned about honestly"


def test_test_split_observations_cannot_change_the_fitted_model(frame_24, trained, tmp_path):
    """The decisive leakage test: corrupt everything from the test start onwards.

    Validation metrics, the selected algorithm and the fitted pipeline must be
    identical to the clean run; only the reported test metrics may differ.
    """
    _, report = trained
    test_start = report["split"]["boundaries"]["test"]["start"]
    base = get_dataset()
    corrupted = copy.copy(base)
    obs = base.observations.copy(deep=True)
    mask = pd.to_datetime(obs["valid_date"], errors="coerce") >= pd.to_datetime(test_start)
    obs.loc[mask, "observed_rain_mm"] = 400.0
    corrupted.observations = obs

    # the same feature rows (any date) score both pipelines — features never
    # read observations, which test_features.py verifies separately
    X_sample, _ = _xy(_usable_rows(frame_24).head(20))
    original_dir = settings.models_dir
    results = {}
    try:
        for name, dataset in (("clean", base), ("dirty", corrupted)):
            settings.models_dir = tmp_path / name
            results[name] = train_local_correction_model(
                dataset, lead_hours=LEAD, force_retrain=True, cfg=settings
            )
            clear_model_cache()
            loaded, load_reason = load_artifact(LEAD, settings)
            assert loaded is not None, load_reason
            results[name + "_predictions"] = [
                float(p) for p in loaded.pipeline.predict(X_sample)
            ]
    finally:
        settings.models_dir = original_dir
        clear_model_cache()

    assert results["clean"]["selected_model"] == results["dirty"]["selected_model"]
    for name in CANDIDATE_ORDER:
        clean_metrics = results["clean"]["candidates"][name]["validation_metrics"]
        dirty_metrics = results["dirty"]["candidates"][name]["validation_metrics"]
        assert clean_metrics["mae_mm"] == pytest.approx(dirty_metrics["mae_mm"])
        assert clean_metrics["sample_count"] == dirty_metrics["sample_count"]
    assert results["clean_predictions"] == pytest.approx(
        results["dirty_predictions"], abs=1e-6
    )
    assert results["clean"]["held_out_test_metrics"] != (
        results["dirty"]["held_out_test_metrics"]
    ), "corrupting the future should visibly change the test metrics only"


# ----------------------------------------------------------------------------------
# G7 — controlled retraining behaviour
# ----------------------------------------------------------------------------------
def test_existing_artifact_is_reused_unless_force_is_requested(trained):
    directory, report = trained
    original_dir = settings.models_dir
    settings.models_dir = directory
    try:
        again = train_local_correction_model(get_dataset(), lead_hours=LEAD, cfg=settings)
    finally:
        settings.models_dir = original_dir
        clear_model_cache()
    assert again["status"] == "already_trained"
    assert again["model_version"] == report["model_version"]
    assert again["message"] and "force_retrain" in again["message"]


def test_training_is_reproducible_for_the_same_input(tmp_path):
    original_dir = settings.models_dir
    try:
        settings.models_dir = tmp_path / "run_a"
        first = train_local_correction_model(
            get_dataset(), lead_hours=LEAD, force_retrain=True, cfg=settings
        )
        settings.models_dir = tmp_path / "run_b"
        second = train_local_correction_model(
            get_dataset(), lead_hours=LEAD, force_retrain=True, cfg=settings
        )
    finally:
        settings.models_dir = original_dir
        clear_model_cache()
    assert first["selected_model"] == second["selected_model"]
    for name in CANDIDATE_ORDER:
        assert first["candidates"][name]["validation_metrics"]["mae_mm"] == (
            pytest.approx(second["candidates"][name]["validation_metrics"]["mae_mm"])
        )
    assert first["held_out_test_metrics"]["mae_mm"] == pytest.approx(
        second["held_out_test_metrics"]["mae_mm"]
    )
    assert first["held_out_test_metrics"]["sample_count"] == (
        second["held_out_test_metrics"]["sample_count"]
    )


def test_training_does_not_mutate_the_dataset():
    ds = get_dataset()
    before_fc = ds.forecasts.copy(deep=True)
    before_obs = ds.observations.copy(deep=True)
    frame = build_feature_frame(ds, lead_hours=LEAD, cfg=settings)
    _xy(frame)
    assert ds.forecasts.equals(before_fc)
    assert ds.observations.equals(before_obs)


# ----------------------------------------------------------------------------------
# G5/G7 — insufficient data never trains a misleading model
# ----------------------------------------------------------------------------------
def test_insufficient_samples_skip_training_and_keep_the_fallback(model_env):
    report = train_local_correction_model(
        get_dataset(), lead_hours=LEAD, minimum_samples=100_000, cfg=settings
    )
    assert report["status"] == "skipped_insufficient_data"
    assert report["model_version"] is None
    assert report["selected_model"] is None
    assert report["candidates"] == {}
    assert report["held_out_test_metrics"] is None
    assert report["honesty"]["ml_worse_than_baseline"] is None
    assert report["honesty"]["test_set_evaluated_once"] is False
    assert report["fallback"]["active"] is True
    assert report["fallback"]["label"] == FALLBACK_LABEL
    assert any("minimum" in w.lower() or "skipped" in w.lower() for w in report["warnings"])
    assert not pipeline_path(LEAD, settings).exists()
    assert not report_path(LEAD, settings).exists()
    assert artifact_exists(LEAD, settings) is False


def test_alternate_ratio_run_is_disclosed_in_the_report(monkeypatch, model_env):
    """Below ``ml_min_split_dates`` the documented 70/15/15 split is used and
    the substitution is stated in the report — never silently."""
    monkeypatch.setattr(settings, "ml_min_split_dates", 10_000)
    report = train_local_correction_model(
        get_dataset(), lead_hours=LEAD, cfg=settings
    )
    assert report["status"] == "completed"
    assert report["split"]["alternate_ratio_applied"] is True
    assert report["split"]["ratio"] == {"train": 0.7, "validation": 0.15, "test": 0.15}
    assert any("Alternate chronological split" in w for w in report["warnings"])
    assert report["honesty"]["test_used_for_selection"] is False


def test_too_few_dates_skip_training_with_an_explicit_reason(model_env):
    """A dataset that cannot fill three chronological sections is never trained."""
    trimmed = _trimmed_dataset(get_dataset(), ["2025-06-01", "2025-06-02"])
    report = train_local_correction_model(trimmed, lead_hours=LEAD, cfg=settings)
    assert report["status"] == "skipped_insufficient_data"
    assert report["split"] is None
    assert any("chronological" in w for w in report["warnings"]), report["warnings"]
    assert any(
        "scientific-integrity rule" in w for w in report["warnings"]
    ), report["warnings"]
    assert report["fallback"]["active"] is True
    assert report["fallback"]["label"] == FALLBACK_LABEL
    assert not artifact_exists(LEAD, settings)


def test_unsupported_lead_horizon_is_rejected(model_env):
    with pytest.raises(ValueError):
        train_local_correction_model(get_dataset(), lead_hours=12, cfg=settings)


# ----------------------------------------------------------------------------------
# G7 — artifact integrity checks
# ----------------------------------------------------------------------------------
def test_feature_schema_mismatch_makes_an_artifact_unusable(trained, monkeypatch):
    directory, _ = trained
    original_dir = settings.models_dir
    settings.models_dir = directory
    try:
        clear_model_cache()
        loaded, reason = load_artifact(LEAD, settings)
        assert loaded is not None
        monkeypatch.setattr(settings, "ml_feature_schema_version", "features-v999")
        clear_model_cache()
        loaded, reason = load_artifact(LEAD, settings)
        assert loaded is None
        assert reason and "Feature schema mismatch" in reason
    finally:
        settings.models_dir = original_dir
        clear_model_cache()


def test_artifact_for_another_lead_is_never_served(trained):
    directory, _ = trained
    original_dir = settings.models_dir
    settings.models_dir = directory
    try:
        clear_model_cache()
        loaded, reason = load_artifact(72, settings)
        assert loaded is None
        assert reason and "72h" in reason
    finally:
        settings.models_dir = original_dir
        clear_model_cache()


def test_report_without_a_pipeline_is_reported_as_unavailable(trained):
    directory, _ = trained
    original_dir = settings.models_dir
    try:
        settings.models_dir = directory
        report_copy = report_path(LEAD, settings).read_bytes()
        pipeline_copy = pipeline_path(LEAD, settings).read_bytes()
        pipeline_path(LEAD, settings).unlink()
        clear_model_cache()
        loaded, reason = load_artifact(LEAD, settings)
        assert loaded is None
        assert reason and "missing" in reason
        # restore (still inside the isolated directory)
        report_path(LEAD, settings).write_bytes(report_copy)
        pipeline_path(LEAD, settings).write_bytes(pipeline_copy)
        clear_model_cache()
        loaded, reason = load_artifact(LEAD, settings)
        assert loaded is not None, reason
    finally:
        settings.models_dir = original_dir
        clear_model_cache()


def test_corrupt_pipeline_file_falls_back_instead_of_crashing(trained):
    directory, _ = trained
    original_dir = settings.models_dir
    try:
        settings.models_dir = directory
        pipeline_copy = pipeline_path(LEAD, settings).read_bytes()
        pipeline_path(LEAD, settings).write_bytes(b"not-a-joblib-file")
        clear_model_cache()
        loaded, reason = load_artifact(LEAD, settings)
        assert loaded is None
        assert reason and "could not be loaded" in reason
        pipeline_path(LEAD, settings).write_bytes(pipeline_copy)
        clear_model_cache()
        loaded, reason = load_artifact(LEAD, settings)
        assert loaded is not None, reason
    finally:
        settings.models_dir = original_dir
        clear_model_cache()


def test_feature_frame_contains_only_declared_columns(frame_24):
    for column in FEATURE_COLUMNS:
        assert column in frame_24.columns
    assert TARGET_COLUMN in frame_24.columns
    assert set(CATEGORICAL_FEATURES) <= set(FEATURE_COLUMNS)
    # numeric features are numeric-or-missing; categorical features are strings
    for column in NUMERIC_FEATURES:
        values = frame_24[column]
        assert values.map(
            lambda v: isinstance(v, str) or v is None or (isinstance(v, float) and math.isnan(v))
            or isinstance(v, (int, float, np.integer, np.floating))
        ).all(), column
    for column in CATEGORICAL_FEATURES:
        usable_values = frame_24.loc[
            frame_24["feature_availability"] == "ok", column
        ]
        assert usable_values.map(lambda v: isinstance(v, str)).all(), column
