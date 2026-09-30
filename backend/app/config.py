"""Central configuration for VARSHA Weather AI.

Every threshold, label and path used by the prototype is configurable here
(SRS BR-12: event thresholds must be configurable). Values can be overridden
with environment variables where noted.

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]  # .../varsha-weather-ai/backend
PROJECT_ROOT = BACKEND_DIR.parent  # .../varsha-weather-ai


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    """Immutable-by-convention runtime settings (tests may patch attributes)."""

    # --- Identity and positioning -------------------------------------------------
    app_name: str = "VARSHA Weather AI"
    app_full_form: str = "Verified Adaptive Regime-aware Skill-weighted Hybrid Analytics"
    problem_statement_id: str = "SIH26081"
    version: str = "0.4.0"
    phase: str = "Phase 4: AI/ML Local Correction Model"

    # --- Audit-friendly versioning (returned with every forecast) -----------------
    algorithm_version: str = "varsha-blend-2.0.0"   # blending math unchanged in Phase 4
    config_version: str = "phase2-defaults-v1"      # thresholds/weights unchanged in Phase 4

    # --- Mandatory disclaimers ----------------------------------------------------
    decision_support_disclaimer: str = (
        "Decision-Support Prototype — Synthetic Development Dataset — "
        "Not Operational Weather Data — Not an Official Weather Warning."
    )
    data_mode: str = _env("VARSHA_DATA_MODE", "synthetic")
    synthetic_data_label: str = (
        "Synthetic Development Dataset — Not Operational Weather Data"
    )

    # --- Paths --------------------------------------------------------------------
    data_dir: Path = Path(_env("VARSHA_DATA_DIR", str(PROJECT_ROOT / "data")))
    database_url: str = _env(
        "VARSHA_DB_URL",
        f"sqlite:///{(BACKEND_DIR / 'varsha_weather_ai.db').as_posix()}",
    )

    # --- Runtime port (deployment friendly) ----------------------------------------
    # Render/Railway inject PORT when it starts the process; the local (and
    # fallback) default stays 8001 so the Phase 5 dashboard demo is unchanged.
    port: int = int(_env("PORT", "8001"))

    # --- Phase 5: local frontend CORS ----------------------------------------------
    # Local dev origins only — never a wildcard. Override with
    # VARSHA_CORS_ORIGINS="http://a,http://b" when the dashboard runs elsewhere.
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in _env(
            "VARSHA_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    )

    # --- Dataset contract ---------------------------------------------------------
    districts_file: str = "districts.csv"
    forecasts_file: str = "historical_forecasts_synthetic.csv"
    observations_file: str = "observations_synthetic.csv"
    allowed_lead_hours: tuple[int, ...] = (6, 24, 72)
    primary_lead_hours: int = 24
    forecast_unit: str = "mm"
    min_daily_records_per_district: int = 90
    max_plausible_rain_mm: float = 500.0  # physically implausible for a 24h district total
    valid_forecast_statuses: tuple[str, ...] = ("ok", "delayed", "unavailable", "anomalous")

    # --- Rainfall categories (IMD-style 24h categories as configurable defaults) ---
    light_max_mm: float = 15.5
    moderate_max_mm: float = 64.4
    heavy_max_mm: float = 115.5
    very_heavy_max_mm: float = 204.4

    # --- Source health ------------------------------------------------------------
    source_health_window_days: int = int(_env("VARSHA_HEALTH_WINDOW_DAYS", "14"))
    health_unavailable_ratio: float = 0.50
    health_anomalous_ratio: float = 0.15
    health_delayed_ratio: float = 0.15

    # --- Audit ---------------------------------------------------------------------
    audit_retention_days: int = 365

    # =============================================================================
    # Phase 2 — Forecast Intelligence Engine (all values configurable)
    # =============================================================================

    # --- Bias correction (A) -------------------------------------------------------
    bias_method: str = "mean_bias_prior_only"
    min_bias_history_records: int = int(_env("VARSHA_MIN_BIAS_HISTORY", "10"))

    # --- Thresholds: India 24h rainfall categories as prototype defaults ----------
    # Scaled by (lead_hours / 24) when scale_thresholds_by_lead is True.
    base_thresholds_24h_mm: dict = field(
        default_factory=lambda: {
            "moderate": 15.6,
            "heavy": 64.5,
            "very_heavy": 115.6,
            "extreme": 204.5,
        }
    )
    scale_thresholds_by_lead: bool = True

    # --- Regime detection (B) -----------------------------------------------------
    heatwave_temp_c: float = 40.0
    active_monsoon_ensemble_mm_factor: float = 1.0  # x moderate threshold for the lead
    active_monsoon_trailing_3day_mm: float = 40.0  # sum of 24h obs, 3 days before date
    active_monsoon_humidity_pct: float = 80.0

    # --- Dynamic Trust Engine (C) -------------------------------------------------
    trust_weights: dict = field(
        default_factory=lambda: {
            "historical_skill": 0.40,
            "recent_skill": 0.25,
            "health": 0.20,
            "agreement": 0.15,
        }
    )
    skill_mae_scale_mm: float = 25.0
    skill_score_when_no_history: float = 0.5
    recent_skill_records: int = 14
    health_score_map: dict = field(
        default_factory=lambda: {
            "Healthy": 1.0,
            "Delayed": 0.6,
            "Anomalous": 0.3,
            "Unavailable": 0.0,
        }
    )
    agreement_scale_mm: float = 10.0
    # Prototype context priors (transparent, configurable, NOT learned):
    # multiplicative adjustment by weather regime and lead time.
    context_regime_factors: dict = field(
        default_factory=lambda: {
            "nwp_model_a": {"Heavy-Rain Risk": 0.95},
            "ensemble_mean": {"Heavy-Rain Risk": 1.05},
            "ai_local_v1": {"Heavy-Rain Risk": 0.90},
        }
    )
    context_lead_factors: dict = field(
        default_factory=lambda: {
            "nwp_model_a": {"6": 0.95, "72": 1.05},
            "ensemble_mean": {"72": 1.02},
            "ai_local_v1": {"6": 1.05, "72": 0.95},
        }
    )

    # --- Confidence and uncertainty (E) -------------------------------------------
    confidence_weights: dict = field(
        default_factory=lambda: {
            "available_sources": 0.25,
            "historical_skill": 0.25,
            "health": 0.15,
            "agreement": 0.20,
            "ensemble_spread": 0.15,
        }
    )
    confidence_cap_single_source: int = 39   # Low band upper bound
    confidence_cap_degraded: int = 69        # Medium band upper bound
    spread_score_scale_mm: float = 20.0

    # --- Risk engine (F) ----------------------------------------------------------
    risk_levels: tuple = ("Low", "Moderate", "High", "Critical")
    risk_disclaimer: str = "Decision-support output only; not an official warning."
    preparedness_actions: dict = field(
        default_factory=lambda: {
            "Low": [
                "Continue routine monitoring of district reports.",
                "No additional preparedness action suggested by this prototype.",
            ],
            "Moderate": [
                "Review drainage channels and low-lying area lists.",
                "Keep field contact lists current for the next 24 hours.",
            ],
            "High": [
                "Brief field teams to avoid low-lying crossings.",
                "Pre-check pumps, boats and shelter desks with local authorities.",
            ],
            "Critical": [
                "Escalate to the district control room for expert verification.",
                "Prepare assistance plans for chronically flood-prone pockets.",
            ],
        }
    )

    # ==============================================================================
    # Phase 3 — Historical backtesting, numeric evaluation, report export
    # ==============================================================================

    # Mandatory Phase-3 label carried by every backtest response and report file.
    backtest_disclaimer: str = (
        "Synthetic Development Dataset — Development/Testing Only — "
        "Not Operational Weather Data — Not an Official Weather Warning."
    )

    # Walk-forward evaluation controls
    default_minimum_history_days: int = int(_env("VARSHA_MIN_HISTORY_DAYS", "14"))
    max_backtest_dates: int = int(_env("VARSHA_MAX_BACKTEST_DATES", "366"))
    reports_dir: Path = Path(
        _env("VARSHA_REPORTS_DIR", str(PROJECT_ROOT / "data" / "reports"))
    )

    # Honest-comparison controls
    min_comparison_sample: int = 20
    low_event_sample_threshold: int = 5
    comparison_similar_tolerance_mm: float = 0.5

    # ==============================================================================
    # Phase 4 — AI/ML Local Rainfall-Correction Model
    # ==============================================================================

    # Mandatory Phase-4 label (same wording required by the spec) carried by every
    # model report, training response and model endpoint response.
    model_disclaimer: str = (
        "Synthetic Development Dataset — Development/Testing Only — "
        "Not Operational Weather Data — Not an Official Weather Warning."
    )

    # Artifact storage (pipeline + JSON report per lead horizon)
    models_dir: Path = Path(_env("VARSHA_MODELS_DIR", str(PROJECT_ROOT / "data" / "models")))

    # Master switch for ML inference inside GET /forecast (tests toggle this).
    # When false, or when no artifact exists, the engine uses the precomputed
    # ai_rain_mm CSV source and discloses it (fallback_precomputed_ai_source).
    ml_inference_enabled: bool = _env("VARSHA_ML_INFERENCE", "true").lower() != "false"

    # --- Feature engineering --------------------------------------------------------
    ml_feature_schema_version: str = "features-v1"
    ml_min_feature_history_days: int = 7  # prior usable obs days required for rolling features

    # --- Chronological split (by unique global date, never random rows) ------------
    ml_split_train_fraction: float = 0.60
    ml_split_val_fraction: float = 0.20  # test = the remaining 20%
    ml_min_split_dates: int = 30  # below this: documented alternate 70/15/15 + warning
    ml_alternate_train_fraction: float = 0.70
    ml_alternate_val_fraction: float = 0.15

    # --- Minimum-sample guards (training refuses to run below these) ---------------
    ml_min_train_rows: int = int(_env("VARSHA_ML_MIN_TRAIN_ROWS", "200"))
    ml_min_val_rows: int = int(_env("VARSHA_ML_MIN_VAL_ROWS", "50"))
    ml_min_test_rows: int = int(_env("VARSHA_ML_MIN_TEST_ROWS", "50"))

    # --- Candidate models ------------------------------------------------------------
    ml_random_state: int = 42  # dataset seed and HistGradientBoosting reproducibility
    ml_hgb_max_iter: int = 200


settings = Settings()


def thresholds_for_lead(lead_hours: int, cfg: Settings | None = None) -> dict[str, float]:
    """Rainfall thresholds (mm) for a lead time.

    Prototype defaults are India-style 24-hour categories. When
    ``scale_thresholds_by_lead`` is enabled they are scaled linearly by
    ``lead_hours / 24`` so a 6-hour horizon uses 6-hour thresholds.
    """
    s = cfg or settings
    factor = (lead_hours / 24.0) if s.scale_thresholds_by_lead else 1.0
    return {name: value * factor for name, value in s.base_thresholds_24h_mm.items()}

# Source registry (SRS FR-SRC-01/02). Phase 1 ships three synthetic sources plus
# the observation dataset; real providers plug in through the adapter interface.
SOURCE_DEFINITIONS: dict[str, dict[str, str]] = {
    "nwp_model_a": {
        "source_type": "NWP",
        "display_name": "NWP Model A (synthetic)",
        "description": "Physics-based model replay; underpredicts some heavy rainfall events.",
    },
    "ensemble_mean": {
        "source_type": "Ensemble",
        "display_name": "Ensemble Mean (synthetic)",
        "description": "Multi-member ensemble mean with spread and percentile columns.",
    },
    "ai_local_v1": {
        "source_type": "AI_ML",
        "display_name": "AI Local Correction v1 (synthetic)",
        "description": "Local statistical correction; skilled in moderate rain, weaker in extremes.",
    },
}

# Observation source metadata (observations are truth for verification).
OBSERVATION_SOURCE: dict[str, str] = {
    "source_id": "observations_replay",
    "source_type": "Observation",
    "display_name": "Historical replay observations (synthetic)",
    "description": "Used for verification and bias history only; never blended as a forecast.",
}

FIELD = field  # re-export for convenience in schema extensions
