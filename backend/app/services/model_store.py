"""Phase 4 — artifact persistence, integrity checks and status for the local model.

Artifacts live in ``data/models/`` (configurable via ``VARSHA_MODELS_DIR``):

* ``varsha_ai_local_<lead>h.joblib``   — joblib bundle (fitted sklearn pipeline
  + model_version + lead + feature-schema fingerprint)
* ``varsha_ai_local_<lead>h_report.json`` — the full training/model report

Loading validates that the bundle and the report agree with each other and
with the current configuration (lead horizon and feature-schema version);
any mismatch is reported as *unavailable* with an explicit reason instead of
being used silently. A tiny mtime-based cache keeps repeated inference calls
cheap while still picking up retrains and deletions.

Training never happens implicitly: importing this module or starting the app
only *reads* artifacts.

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib

from ..config import Settings, settings as default_settings

# --- cache: path -> (mtime_ns, size, loaded) ------------------------------------
_CACHE: dict[str, tuple[int, int, "LoadedModel"]] = {}


def pipeline_path(lead_hours: int, cfg: Settings | None = None) -> Path:
    s = cfg or default_settings
    return Path(s.models_dir).expanduser() / f"varsha_ai_local_{int(lead_hours)}h.joblib"


def report_path(lead_hours: int, cfg: Settings | None = None) -> Path:
    s = cfg or default_settings
    return Path(s.models_dir).expanduser() / f"varsha_ai_local_{int(lead_hours)}h_report.json"


@dataclass
class LoadedModel:
    """A validated, ready-to-use artifact set for one lead horizon."""

    lead_hours: int
    model_version: str
    selected_model: str
    feature_schema_version: str
    trained_at: str
    pipeline: object
    report: dict


def clear_model_cache() -> None:
    """Drop the artifact cache (tests, and after moving/deleting artifacts)."""
    _CACHE.clear()


def artifact_exists(lead_hours: int, cfg: Settings | None = None) -> bool:
    return pipeline_path(lead_hours, cfg).is_file() and report_path(lead_hours, cfg).is_file()


def trained_lead_hours(cfg: Settings | None = None) -> list[int]:
    """Lead horizons that have both artifact files on disk, ascending."""
    leads: list[int] = []
    for lead in (6, 24, 72):
        if artifact_exists(lead, cfg):
            leads.append(lead)
    return leads


def latest_trained_lead(cfg: Settings | None = None) -> int | None:
    """The most recently trained lead horizon (by report file mtime)."""
    candidates: list[tuple[float, int]] = []
    for lead in trained_lead_hours(cfg):
        try:
            candidates.append((report_path(lead, cfg).stat().st_mtime, lead))
        except OSError:
            continue
    if not candidates:
        return None
    return max(candidates)[1]


def load_artifact(
    lead_hours: int, cfg: Settings | None = None
) -> tuple[LoadedModel | None, str | None]:
    """Load + validate an artifact set. Returns ``(loaded, None)`` or ``(None, reason)``."""
    s = cfg or default_settings
    p_path = pipeline_path(lead_hours, s)
    r_path = report_path(lead_hours, s)

    if not p_path.is_file():
        return None, f"No trained model artifact for {lead_hours}h lead ({p_path.name} missing)."
    if not r_path.is_file():
        return None, f"Model report missing for {lead_hours}h lead ({r_path.name})."

    # mtime-keyed cache (invalidated automatically on retrain/delete)
    try:
        stat = p_path.stat()
        key = str(p_path)
        hit = _CACHE.get(key)
        if hit is not None and hit[0] == stat.st_mtime_ns and hit[1] == stat.st_size:
            return hit[2], None
    except OSError:
        stat = None  # type: ignore[assignment]

    try:
        bundle = joblib.load(p_path)
    except Exception as exc:  # pragma: no cover - corrupt-artifact guard
        return None, f"Model pipeline could not be loaded: {exc}"
    if not isinstance(bundle, dict) or "pipeline" not in bundle:
        return None, "Model pipeline file is not a valid VARSHA bundle."

    try:
        with r_path.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"Model report could not be read: {exc}"
    if not isinstance(report, dict):
        return None, "Model report is not a JSON object."

    # --- integrity checks ------------------------------------------------------
    if int(bundle.get("lead_hours", -1)) != int(lead_hours):
        return None, (
            f"Artifact lead mismatch: bundle says {bundle.get('lead_hours')}h, "
            f"requested {lead_hours}h."
        )
    schema = str(bundle.get("feature_schema_version", ""))
    if schema != str(s.ml_feature_schema_version):
        return None, (
            f"Feature schema mismatch: artifact was trained with '{schema}', "
            f"current schema is '{s.ml_feature_schema_version}'."
        )
    version = str(bundle.get("model_version", ""))
    if not version or version != str(report.get("model_version")):
        return None, (
            "Bundle and report model_version do not match "
            f"('{version}' vs '{report.get('model_version')}')."
        )

    loaded = LoadedModel(
        lead_hours=int(lead_hours),
        model_version=version,
        selected_model=str(bundle.get("selected_model", "")),
        feature_schema_version=schema,
        trained_at=str(bundle.get("trained_at", "")),
        pipeline=bundle["pipeline"],
        report=report,
    )
    if stat is not None:
        _CACHE[str(p_path)] = (stat.st_mtime_ns, stat.st_size, loaded)
    return loaded, None


def save_artifacts(
    pipeline: object,
    report: dict,
    cfg: Settings | None = None,
) -> tuple[Path, Path]:
    """Persist the fitted pipeline bundle and its JSON report atomically enough
    for a single-process prototype (write temp file, then replace)."""
    s = cfg or default_settings
    lead = int(report["lead_hours"])
    p_path = pipeline_path(lead, s)
    r_path = report_path(lead, s)
    p_path.parent.mkdir(parents=True, exist_ok=True)

    bundle = {
        "pipeline": pipeline,
        "model_version": report["model_version"],
        "lead_hours": lead,
        "feature_schema_version": report["feature_schema"]["version"],
        "selected_model": report["selected_model"],
        "trained_at": report["generated_at"],
        "data_mode": report.get("data_mode", s.data_mode),
        "disclaimer": report.get("disclaimer", s.model_disclaimer),
    }
    joblib.dump(bundle, p_path)

    tmp = r_path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    tmp.replace(r_path)

    clear_model_cache()  # make sure the next load sees the new files
    return p_path, r_path


def model_status(cfg: Settings | None = None) -> dict:
    """Payload for GET /model/status (computed from disk + config, never stale)."""
    s = cfg or default_settings
    leads = trained_lead_hours(s)
    per_lead: dict[str, dict] = {}
    latest_version: str | None = None
    latest_trained_at: str | None = None

    for lead in (6, 24, 72):
        exists = lead in leads
        entry: dict = {
            "artifact_exists": exists,
            "model_version": None,
            "trained_at": None,
            "selected_model": None,
            "held_out_test_mae_mm": None,
            "inference_ready": bool(exists and s.ml_inference_enabled),
        }
        if exists:
            loaded, reason = load_artifact(lead, s)
            if loaded is not None:
                test_metrics = loaded.report.get("held_out_test_metrics") or {}
                entry.update(
                    model_version=loaded.model_version,
                    trained_at=loaded.trained_at,
                    selected_model=loaded.selected_model,
                    held_out_test_mae_mm=test_metrics.get("mae_mm"),
                )
                if latest_trained_at is None or loaded.trained_at >= latest_trained_at:
                    latest_trained_at = loaded.trained_at
                    latest_version = loaded.model_version
            else:
                entry["artifact_error"] = reason
        per_lead[str(lead)] = entry

    inference_ready = bool(leads and s.ml_inference_enabled)
    return {
        "artifact_exists": bool(leads),
        "model_version": latest_version,
        "trained_lead_hours": leads,
        "inference_enabled": bool(s.ml_inference_enabled),
        "inference_ready": inference_ready,
        "last_training_time": latest_trained_at,
        "data_mode": s.data_mode,
        "disclaimer": s.model_disclaimer,
        "models_dir": str(Path(s.models_dir).expanduser()),
        "per_lead": per_lead,
        "fallback_status": {
            "active": not inference_ready,
            "label": (
                "fallback_precomputed_ai_source"
                if not inference_ready
                else "trained_local_correction_model"
            ),
            "reason": (
                "ML inference disabled by configuration (VARSHA_ML_INFERENCE=false); "
                "GET /forecast uses the precomputed ai_rain_mm CSV source."
                if not s.ml_inference_enabled
                else (
                    "No trained model artifact exists yet; POST /model/train first; "
                    "GET /forecast uses the precomputed ai_rain_mm CSV source."
                    if not leads
                    else "Trained model artifact available; GET /forecast uses the "
                    "trained local correction model for trained lead horizons."
                )
            ),
        },
        "note": (
            "Training is never triggered at startup — it only runs through "
            "POST /model/train (or the app.train_model CLI)."
        ),
    }
