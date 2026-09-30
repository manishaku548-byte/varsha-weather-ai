"""Phase 4 — training workflow for the local rainfall-correction model.

Scientific-integrity rules enforced by construction in this module:

1.  No fabricated quality numbers — every metric below is computed from the
    stored synthetic development dataset.
2.  Chronological splits only: unique global dates are cut 60/20/20 into
    train / validation / test (documented alternate 70/15/15 below
    ``ml_min_split_dates``). Random row splits are never used, and all
    districts of a date always land in the same split.
3.  No future-to-past prediction: features come from ``build_feature_frame``
    (strictly-prior lags/rollings only) and the target is only ever the label.
4./5. Preprocessing (imputer, scaler, one-hot encoder) lives inside the sklearn
    Pipeline and is fitted **on training rows only**.
6.  The final model is selected by **validation MAE only**
    (``select_candidate`` physically receives nothing else).
7.  The selected candidate is refit on train+validation and evaluated on the
    held-out future test set **exactly once**.
8.  Test metrics never feed back into selection or hyperparameters.
9.  ``honesty.ml_worse_than_baseline`` reports when the model is worse than
    simple references (naive mean, raw NWP, the precomputed AI source).
10. When dates/rows are insufficient, training is *skipped* with a clear
    warning and the rule-based fallback source stays active — no misleading
    model is trained.

Training runs only on demand (POST /model/train or ``python -m
app.train_model``); importing this module or starting the API never trains.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ..config import Settings, settings as default_settings
from .features import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    FEATURE_DOCS,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    build_feature_frame,
)
from .metrics import regression_metrics
from .model_store import (
    artifact_exists,
    load_artifact,
    pipeline_path,
    report_path,
    save_artifacts,
)

# --- candidate identifiers (stable strings used in reports/responses) --------------
CANDIDATE_BASELINE = "linear_regression"
CANDIDATE_NONLINEAR = "hist_gradient_boosting"
CANDIDATE_ROLES: dict[str, str] = {
    CANDIDATE_BASELINE: "baseline",
    CANDIDATE_NONLINEAR: "non_linear_candidate",
}
#: Candidate evaluation order (also the deterministic tie-break on validation MAE).
CANDIDATE_ORDER: tuple[str, ...] = (CANDIDATE_BASELINE, CANDIDATE_NONLINEAR)

SPLIT_METHOD = "chronological_by_unique_global_date"


class InsufficientSplitError(RuntimeError):
    """The date range cannot produce three non-empty chronological splits."""


# --------------------------------------------------------------------------------------
# Chronological split (rule 2)
# --------------------------------------------------------------------------------------
@dataclass
class ChronologicalSplit:
    train_dates: list[str]
    val_dates: list[str]
    test_dates: list[str]
    train_fraction: float
    val_fraction: float
    test_fraction: float
    alternate_ratio_applied: bool = False
    warning: str | None = None

    def payload(self) -> dict:
        def bounds(dates: list[str]) -> dict:
            return {
                "start": dates[0] if dates else None,
                "end": dates[-1] if dates else None,
                "dates": len(dates),
            }

        return {
            "method": SPLIT_METHOD,
            "description": (
                "Unique valid dates sorted ascending and cut chronologically; all "
                "districts of a date belong to the same split; rows are assigned "
                "to a split by their date only."
            ),
            "ratio": {
                "train": self.train_fraction,
                "validation": self.val_fraction,
                "test": self.test_fraction,
            },
            "alternate_ratio_applied": self.alternate_ratio_applied,
            "warning": self.warning,
            "boundaries": {
                "train": bounds(self.train_dates),
                "validation": bounds(self.val_dates),
                "test": bounds(self.test_dates),
            },
        }


def chronological_split(
    unique_dates, cfg: Settings | None = None
) -> ChronologicalSplit:
    """Deterministic 60/20/20 (or documented 70/15/15 alternate) date split."""
    s = cfg or default_settings
    dates = sorted({str(d) for d in unique_dates})
    n = len(dates)

    default_note = (
        f"{s.ml_split_train_fraction:.0%}/"
        f"{s.ml_split_val_fraction:.0%}/"
        f"{1.0 - s.ml_split_train_fraction - s.ml_split_val_fraction:.0%}"
    )
    if n >= int(s.ml_min_split_dates):
        train_frac, val_frac = s.ml_split_train_fraction, s.ml_split_val_fraction
        alternate = False
        warning = None
    else:
        train_frac, val_frac = s.ml_alternate_train_fraction, s.ml_alternate_val_fraction
        alternate = True
        alt_note = (
            f"{train_frac:.0%}/{val_frac:.0%}/"
            f"{1.0 - train_frac - val_frac:.0%}"
        )
        warning = (
            f"Alternate chronological split {alt_note} applied because only {n} "
            f"unique dates are available (< {int(s.ml_min_split_dates)} required "
            f"for the default {default_note} split)."
        )

    n_train = int(n * train_frac)
    n_val = int(n * val_frac)
    n_test = n - n_train - n_val
    if min(n_train, n_val, n_test) < 1:
        raise InsufficientSplitError(
            f"{n} unique dates cannot produce three non-empty chronological "
            f"splits (train={n_train}, validation={n_val}, test={n_test})."
        )

    return ChronologicalSplit(
        train_dates=dates[:n_train],
        val_dates=dates[n_train : n_train + n_val],
        test_dates=dates[n_train + n_val :],
        train_fraction=train_frac,
        val_fraction=val_frac,
        test_fraction=round(1.0 - train_frac - val_frac, 6),
        alternate_ratio_applied=alternate,
        warning=warning,
    )


# --------------------------------------------------------------------------------------
# Model selection (rules 6 + 8): receives validation MAE only, by design.
# --------------------------------------------------------------------------------------
def select_candidate(validation_metrics: dict[str, float | None]) -> str:
    """Return the candidate with the lowest validation MAE.

    The signature deliberately accepts *only* validation metrics — test
    results cannot influence selection because they are never passed in.
    Ties resolve deterministically to CANDIDATE_ORDER (first-seen wins).
    """
    best_name: str | None = None
    best_mae: float | None = None
    for name in CANDIDATE_ORDER:
        mae = validation_metrics.get(name)
        if mae is None:
            continue
        value = float(mae)
        if math.isnan(value) or math.isinf(value):
            continue
        if best_mae is None or value < best_mae:
            best_name, best_mae = name, value
    if best_name is None:
        raise ValueError("No finite validation MAE available for selection.")
    return best_name


# --------------------------------------------------------------------------------------
# Pipelines (rules 4 + 5: preprocessing fitted on train only, inside the Pipeline)
# --------------------------------------------------------------------------------------
def _preprocessor(cfg: Settings) -> ColumnTransformer:
    numeric_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "onehot",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            ),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, list(NUMERIC_FEATURES)),
            ("cat", categorical_pipe, list(CATEGORICAL_FEATURES)),
        ],
        remainder="drop",
        sparse_threshold=0.0,
    )


def candidate_pipelines(cfg: Settings | None = None) -> dict[str, Pipeline]:
    """Fresh (unfitted) pipelines for both candidates."""
    s = cfg or default_settings
    return {
        CANDIDATE_BASELINE: Pipeline(
            steps=[
                ("preprocess", _preprocessor(s)),
                ("model", LinearRegression()),
            ]
        ),
        CANDIDATE_NONLINEAR: Pipeline(
            steps=[
                ("preprocess", _preprocessor(s)),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        random_state=int(s.ml_random_state),
                        max_iter=int(s.ml_hgb_max_iter),
                    ),
                ),
            ]
        ),
    }


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _clip(values, cfg: Settings | None = None) -> np.ndarray:
    """Rainfall predictions are clipped to the plausible range (never negative)."""
    s = cfg or default_settings
    return np.clip(np.asarray(values, dtype=float), 0.0, s.max_plausible_rain_mm)


def _xy(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    X = frame[FEATURE_COLUMNS].copy()
    for column in NUMERIC_FEATURES:
        X[column] = pd.to_numeric(X[column], errors="coerce")
    for column in CATEGORICAL_FEATURES:
        X[column] = X[column].astype(str)
    y = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce").astype(float)
    return X, y


def _metric_payload(pairs: list[tuple[float, float]]) -> dict:
    metrics = regression_metrics(pairs)
    return {
        "sample_count": metrics.sample_count,
        "mae_mm": metrics.mae_mm,
        "rmse_mm": metrics.rmse_mm,
        "mean_bias_error_mm": metrics.mean_bias_error_mm,
        "median_absolute_error_mm": metrics.median_absolute_error_mm,
        "max_absolute_error_mm": metrics.max_absolute_error_mm,
    }


def default_model_limitations(cfg: Settings) -> list[str]:
    """Static caveats attached to every model report/response."""
    return [
        cfg.model_disclaimer,
        "Single synthetic development dataset and a single 120-day monsoon period "
        "(2025-06-01 to 2025-09-28) — one deterministic sample, no cross-validation "
        "or multi-season sampling.",
        "No operational validation: these metrics are computed against a synthetic "
        "replay dataset and are not IMD/NCMRWF skill scores; they carry no "
        "official-warning meaning.",
        "The artifact is trained once from a controlled chronological split via "
        "POST /model/train; rolling-origin ML retraining per backtest date is "
        "future scope, not part of this MVP.",
        "Only two candidate algorithms are trained (LinearRegression as the "
        "baseline, HistGradientBoostingRegressor as the non-linear candidate); "
        "no hyperparameter search is performed.",
        "MAE/RMSE on small samples are sensitive to a few extreme rainfall days; "
        "read the sample counts together with every metric.",
    ]


# --------------------------------------------------------------------------------------
# Training entry point
# --------------------------------------------------------------------------------------
def train_local_correction_model(
    ds,
    *,
    lead_hours: int,
    minimum_samples: int | None = None,
    force_retrain: bool = False,
    cfg: Settings | None = None,
) -> dict:
    """Train, select, evaluate-once and persist the local correction model.

    Returns the report/response payload (status: ``completed`` |
    ``already_trained`` | ``skipped_insufficient_data``).
    """
    s = cfg or default_settings
    lead_hours = int(lead_hours)
    if lead_hours not in (6, 24, 72):
        raise ValueError("lead_hours must be one of 6, 24 or 72.")

    now = datetime.now(timezone.utc)
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- already trained? (force_retrain controls retraining) ----------------------
    if artifact_exists(lead_hours, s) and not force_retrain:
        loaded, reason = load_artifact(lead_hours, s)
        if loaded is not None:
            existing = dict(loaded.report)
            existing["status"] = "already_trained"
            existing["message"] = (
                f"A trained artifact already exists for {lead_hours}h lead "
                f"({loaded.model_version}); set force_retrain=true to retrain."
            )
            return existing
        # Corrupt/mismatched artifact — fall through and retrain.
        existing_warning = f"Existing artifact unusable ({reason}); retraining."
    else:
        existing_warning = None

    # --- feature frame (strictly-prior features only) -------------------------------
    frame = build_feature_frame(ds, lead_hours=lead_hours, cfg=s)
    availability_counts = {
        str(k): int(v)
        for k, v in frame["feature_availability"].value_counts().items()
    }
    ok_rows = frame[frame["feature_availability"] == "ok"]
    missing_target = int(ok_rows[TARGET_COLUMN].isna().sum())
    row_exclusions = {
        "total_rows": int(len(frame)),
        "missing_forecast": availability_counts.get("missing_forecast", 0),
        "insufficient_history": availability_counts.get("insufficient_history", 0),
        "missing_target": missing_target,
        "usable_rows": int(len(ok_rows) - missing_target),
    }
    usable = ok_rows[ok_rows[TARGET_COLUMN].notna()].copy()

    # --- chronological split over the full dataset date range -----------------------
    all_dates = sorted(
        {
            ts.strftime("%Y-%m-%d")
            for ts in pd.to_datetime(
                ds.forecasts["valid_date"], errors="coerce"
            ).dropna().unique()
        }
    )
    warnings: list[str] = []
    if existing_warning:
        warnings.append(existing_warning)

    try:
        split = chronological_split(all_dates, s)
    except InsufficientSplitError as exc:
        warnings.append(str(exc))
        warnings.append(
            "Training skipped: insufficient dates for a chronological "
            "train/validation/test split (scientific-integrity rule: do not train "
            "a misleading ML model on inadequate data)."
        )
        return _skipped_report(
            s, lead_hours, generated_at, row_exclusions, warnings,
            split_payload=None, retained_artifact=artifact_exists(lead_hours, s),
        )
    if split.warning:
        warnings.append(split.warning)

    split_payload = split.payload()
    split_payload["record_counts"] = {}  # filled after row assignment

    train_df = usable[usable["valid_date"].isin(split.train_dates)]
    val_df = usable[usable["valid_date"].isin(split.val_dates)]
    test_df = usable[usable["valid_date"].isin(split.test_dates)]

    split_payload["record_counts"] = {
        "train": int(len(train_df)),
        "validation": int(len(val_df)),
        "test": int(len(test_df)),
        "total_usable": int(len(usable)),
    }

    # --- minimum-sample guards (rule 10) --------------------------------------------
    min_train_rows = (
        int(minimum_samples)
        if minimum_samples is not None
        else int(s.ml_min_train_rows)
    )
    problems: list[str] = []
    if len(train_df) < min_train_rows:
        problems.append(
            f"train rows {len(train_df)} < required {min_train_rows}"
        )
    if len(val_df) < int(s.ml_min_val_rows):
        problems.append(
            f"validation rows {len(val_df)} < required {int(s.ml_min_val_rows)}"
        )
    if len(test_df) < int(s.ml_min_test_rows):
        problems.append(f"test rows {len(test_df)} < required {int(s.ml_min_test_rows)}")
    if problems:
        warnings.extend(
            [
                "Sample requirements not met: " + "; ".join(problems) + ".",
                "Training skipped — the deterministic fallback source "
                "(fallback_precomputed_ai_source) remains active for GET /forecast "
                "and no model artifact was written.",
            ]
        )
        return _skipped_report(
            s, lead_hours, generated_at, row_exclusions, warnings,
            split_payload=split_payload,
            retained_artifact=artifact_exists(lead_hours, s),
        )

    X_train, y_train = _xy(train_df)
    X_val, y_val = _xy(val_df)
    X_test, y_test = _xy(test_df)

    # --- candidates: fit on train only, evaluate on validation (rules 4-6) ----------
    pipelines = candidate_pipelines(s)
    validation_metrics: dict[str, dict] = {}
    validation_maes: dict[str, float | None] = {}
    for name in CANDIDATE_ORDER:
        pipe = pipelines[name]
        pipe.fit(X_train, y_train)
        val_pred = _clip(pipe.predict(X_val), s)
        metrics = _metric_payload(
            [(float(p), float(a)) for p, a in zip(val_pred, y_val)]
        )
        validation_metrics[name] = metrics
        validation_maes[name] = metrics["mae_mm"]

    selected = select_candidate(validation_maes)

    linear_val = validation_metrics[CANDIDATE_BASELINE]["mae_mm"]
    other_name = (
        CANDIDATE_NONLINEAR if selected == CANDIDATE_BASELINE else CANDIDATE_BASELINE
    )
    other_val = validation_metrics[other_name]["mae_mm"]
    rationale = (
        f"{selected} selected: lowest validation MAE "
        f"({validation_maes[selected]} mm) vs {other_name} "
        f"({other_val} mm). Selection used the validation split only — the "
        f"held-out test set was not consulted."
    )

    # --- refit selected on train + validation, evaluate ONCE on test (rules 7-8) ----
    final_pipeline = candidate_pipelines(s)[selected]
    X_tv = pd.concat([X_train, X_val], ignore_index=True)
    y_tv = pd.concat([y_train, y_val], ignore_index=True)
    final_pipeline.fit(X_tv, y_tv)

    test_pred = _clip(final_pipeline.predict(X_test), s)
    test_pairs = [
        (float(p), float(a)) for p, a in zip(test_pred, y_test)
    ]
    test_metrics = _metric_payload(test_pairs)
    test_mae = test_metrics["mae_mm"]

    # --- honest references on the same held-out rows (rule 9) -----------------------
    references: dict[str, dict] = {}
    worse_than: list[str] = []

    naive_mean = float(y_tv.mean())
    naive_metrics = _metric_payload([(naive_mean, float(a)) for a in y_test])
    references["naive_train_mean"] = {
        "description": "Predicts the train+validation mean rainfall for every test row.",
        **naive_metrics,
    }

    nwp_pairs = [
        (float(v), float(a))
        for v, a in zip(X_test["nwp_rain_mm"], y_test)
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    nwp_metrics = _metric_payload(nwp_pairs)
    references["raw_nwp"] = {
        "description": "Uses the raw NWP forecast as-is (no ML, no correction).",
        **nwp_metrics,
    }

    ai_lookup: dict[tuple[str, str], float | None] = {}
    ai_rows = ds.forecasts[
        (ds.forecasts["source_id"].astype(str) == "ai_local_v1")
        & (pd.to_numeric(ds.forecasts["lead_hours"], errors="coerce") == lead_hours)
    ]
    for record in ai_rows.to_dict("records"):
        key_date = pd.to_datetime(record.get("valid_date"), errors="coerce")
        if pd.isna(key_date):
            continue
        value = record.get("forecast_rain_mm")
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = None
        if number is not None and (math.isnan(number) or math.isinf(number)):
            number = None
        if number is not None and not (0.0 <= number <= s.max_plausible_rain_mm):
            number = None
        ai_lookup[(str(record.get("district_id")), key_date.strftime("%Y-%m-%d"))] = number

    ai_pairs: list[tuple[float, float]] = []
    for district, date, actual in zip(
        test_df["district_id"], test_df["valid_date"], y_test
    ):
        value = ai_lookup.get((str(district), str(date)))
        if value is not None:
            ai_pairs.append((value, float(actual)))
    ai_metrics = _metric_payload(ai_pairs) if ai_pairs else None
    if ai_metrics is not None:
        references["precomputed_ai_source"] = {
            "description": (
                "The precomputed ai_rain_mm CSV source this model replaces "
                "(the fallback source)."
            ),
            **ai_metrics,
        }

    comparison_sentences: list[str] = []
    for ref_name, ref in references.items():
        ref_mae = ref.get("mae_mm")
        if test_mae is None or ref_mae is None:
            continue
        if test_mae > ref_mae:
            worse_than.append(ref_name)
            relation = "higher (worse) than"
        else:
            relation = "lower (better) than"
        comparison_sentences.append(
            f"Held-out test MAE {test_mae} mm is {relation} the "
            f"{ref_name} reference ({ref_mae} mm)."
        )
    ml_worse_than_baseline = bool(worse_than)
    if ml_worse_than_baseline:
        warnings.append(
            "The selected model's held-out test MAE is worse than reference "
            f"predictor(s): {', '.join(worse_than)}. The trained model does NOT "
            "improve on these baselines for this lead horizon; the fallback "
            "source remains the safer input."
        )

    # --- persist artifacts (pipeline bundle + report JSON) --------------------------
    model_version = f"ai-local-{lead_hours}h-{now.strftime('%Y%m%dT%H%M%SZ')}"
    candidates_payload: dict[str, dict] = {}
    for name in CANDIDATE_ORDER:
        candidates_payload[name] = {
            "role": CANDIDATE_ROLES[name],
            "trained_on": "train",
            "evaluated_on": "validation",
            "validation_metrics": validation_metrics[name],
        }

    report: dict = {
        "report_type": "local_correction_model",
        "status": "completed",
        "generated_at": generated_at,
        "data_mode": s.data_mode,
        "disclaimer": s.model_disclaimer,
        "lead_hours": lead_hours,
        "model_version": model_version,
        "selected_model": selected,
        "selection_rationale": rationale,
        "split": split_payload,
        "record_counts": split_payload["record_counts"],
        "row_exclusions": row_exclusions,
        "feature_schema": {
            "version": s.ml_feature_schema_version,
            "numeric_features": list(NUMERIC_FEATURES),
            "categorical_features": list(CATEGORICAL_FEATURES),
            "feature_columns": list(FEATURE_COLUMNS),
            "target": TARGET_COLUMN,
            "feature_availability_values": ["ok", "missing_forecast", "insufficient_history"],
            "feature_docs": FEATURE_DOCS,
        },
        "candidates": candidates_payload,
        "held_out_test_metrics": test_metrics,
        "test_references": references,
        "honesty": {
            "selection_metric": "validation_mae_only",
            "test_set_evaluated_once": True,
            "test_used_for_selection": False,
            "ml_worse_than_baseline": ml_worse_than_baseline,
            "worse_than_references": worse_than,
            "summary_sentences": comparison_sentences,
        },
        "fallback": {
            "active": False,
            "label": "trained_local_correction_model",
            "reason": None,
        },
        "provenance": {
            "training_data": (
                "Synthetic Development Dataset (seed 42) loaded from stored CSVs — "
                "development/testing only, not operational weather data."
            ),
            "split_policy": SPLIT_METHOD,
            "selection_policy": "Final model selected by validation MAE only.",
            "test_policy": (
                "Held-out future test split evaluated exactly once after selection; "
                "never used for hyperparameter or model selection."
            ),
            "preprocessing_policy": (
                "Imputer, scaler and one-hot encoder are fitted on training rows "
                "only (single sklearn Pipeline fitted inside the train step)."
            ),
            "retraining_policy": (
                "Trained once through POST /model/train; rolling-origin retraining "
                "is future scope (not in this MVP)."
            ),
            "algorithm_version": s.algorithm_version,
            "config_version": s.config_version,
        },
        "warnings": warnings,
        "limitations": default_model_limitations(s),
    }

    p_path, r_path = pipeline_path(lead_hours, s), report_path(lead_hours, s)
    report["artifacts"] = {
        "pipeline_file": p_path.name,
        "report_file": r_path.name,
        "pipeline_path": str(p_path),
        "report_path": str(r_path),
    }
    save_artifacts(final_pipeline, report, cfg=s)
    return report


def _skipped_report(
    cfg: Settings,
    lead_hours: int,
    generated_at: str,
    row_exclusions: dict,
    warnings: list[str],
    *,
    split_payload: dict | None,
    retained_artifact: bool,
) -> dict:
    """Deterministic 'do not train' outcome — fallback stays active."""
    if retained_artifact:
        warnings.append(
            "An existing trained artifact was left untouched by this skipped run."
        )
    payload: dict = {
        "report_type": "local_correction_model",
        "status": "skipped_insufficient_data",
        "generated_at": generated_at,
        "data_mode": cfg.data_mode,
        "disclaimer": cfg.model_disclaimer,
        "lead_hours": int(lead_hours),
        "model_version": None,
        "selected_model": None,
        "selection_rationale": (
            "No model selected — training did not run because data/split "
            "requirements were not met."
        ),
        "split": split_payload,
        "row_exclusions": row_exclusions,
        "feature_schema": {
            "version": cfg.ml_feature_schema_version,
            "numeric_features": list(NUMERIC_FEATURES),
            "categorical_features": list(CATEGORICAL_FEATURES),
            "feature_columns": list(FEATURE_COLUMNS),
            "target": TARGET_COLUMN,
        },
        "candidates": {},
        "held_out_test_metrics": None,
        "honesty": {
            "selection_metric": "validation_mae_only",
            "test_set_evaluated_once": False,
            "test_used_for_selection": False,
            "ml_worse_than_baseline": None,
            "worse_than_references": [],
            "summary_sentences": [],
        },
        "fallback": {
            "active": True,
            "label": "fallback_precomputed_ai_source",
            "reason": (
                "Training skipped — GET /forecast keeps the deterministic "
                "rule-based fallback source (precomputed ai_rain_mm CSV)."
            ),
        },
        "warnings": warnings,
        "limitations": default_model_limitations(cfg),
    }
    return payload
