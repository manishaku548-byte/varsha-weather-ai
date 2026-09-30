# Data Dictionary — VARSHA Weather AI (Phases 1 & 4)

> ⚠️ **Synthetic Development Dataset — Not Operational Weather Data.**
> These files are generated locally by `backend/app/data/synthetic_generator.py`
> with a fixed seed. They are **not** IMD, NCMRWF, Open-Meteo or any other real
> data source and must never be presented as operational data.
>
> **Decision-Support Prototype — Not an Official Weather Warning.**

## Files

| File | Rows (default) | Grain |
|------|----------------|-------|
| `data/districts.csv` | 5 | One row per MVP district |
| `data/districts.csv` → `data/observations_synthetic.csv` | 1 800 | district × valid_date × lead_hours |
| `data/historical_forecasts_synthetic.csv` | 5 400 | district × valid_date × lead_hours × source |

Default coverage: **2025-06-01 → 2025-09-28** (120 valid dates per district),
lead hours **6 / 24 / 72**.

---

## Time convention (important)

`valid_date` is the **end of the accumulation window** (rainfall *ending on*
that date), therefore:

```
issue_time = valid_date - lead_hours
```

| Lead | Window represented by `observed_rain_mm` |
|------|------------------------------------------|
| 6 h  | The last 6 hours of the calendar day before `valid_date` |
| 24 h | The full calendar day before `valid_date` |
| 72 h | The three calendar days ending at `valid_date` |

A test (`test_issue_time_plus_lead_equals_valid_time`) enforces
`issue_time + lead_hours == valid_date` for every row — this is the first line
of defence against future-data leakage.

---

## `districts.csv`

| Column | Type | Description |
|--------|------|-------------|
| `district_id` | string | Stable slug (`prayagraj`, `lucknow`, `varanasi`, `kanpur-nagar`, `gorakhpur`) |
| `district_name` | string | Display name |
| `state` | string | Always `Uttar Pradesh` in the MVP |
| `latitude` | float | District centroid latitude (prototype placeholder) |
| `longitude` | float | District centroid longitude (prototype placeholder) |

## `observations_synthetic.csv`

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `district_id` | string | – | FK to `districts.csv` |
| `valid_date` | date `YYYY-MM-DD` | – | End of the accumulation window |
| `lead_hours` | int | h | 6, 24 or 72 |
| `observed_rain_mm` | float | mm | Accumulated rainfall for the window (0 for dry days) |
| `observed_temp_c` | float | °C | Daily temperature (≥40 °C on heatwave days) |
| `observed_humidity_pct` | float | % | Relative humidity, clipped 15–98 |
| `observed_wind_kmph` | float | km/h | Wind speed, higher on heavy-rain days |
| `unit` | string | – | Always `mm` (rainfall unit contract) |

**Observations are the ground truth** used for verification, bias history and
metric calculation. They are never blended as a forecast source.

## `historical_forecasts_synthetic.csv`

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `district_id` | string | – | FK to `districts.csv` |
| `valid_date` | date `YYYY-MM-DD` | – | End of the accumulation window |
| `lead_hours` | int | h | 6, 24 or 72 |
| `source_id` | string | – | `nwp_model_a` \| `ensemble_mean` \| `ai_local_v1` |
| `issue_time` | ISO-8601 UTC | – | `valid_date - lead_hours` |
| `forecast_rain_mm` | float | mm | Raw forecast value (empty when `status=unavailable`) |
| `unit` | string | – | Always `mm` |
| `status` | string | – | `ok` \| `delayed` \| `unavailable` \| `anomalous` |
| `quality_flag` | string | – | `good` \| `low_confidence` \| `missing` \| `suspect` |
| `ensemble_spread_mm` | float | mm | Ensemble spread (**ensemble rows only**, otherwise empty) |
| `ensemble_p10_mm` | float | mm | 10th percentile (ensemble rows only) |
| `ensemble_p90_mm` | float | mm | 90th percentile (ensemble rows only) |

### Simulated source behaviour (by design)

| Source | Simulated characteristics |
|--------|---------------------------|
| `nwp_model_a` (NWP) | Systematically **underpredicts** heavy rainfall events; occasional small false alarm on dry days; a recent **delay burst** makes its health show *Delayed*. |
| `ensemble_mean` (Ensemble) | Well-calibrated mean with spread that grows with rainfall intensity; percentiles are consistent with the mean. Usually **Healthy**. |
| `ai_local_v1` (AI/ML) | Excellent skill for light/moderate rain, but misses ~35 % of extreme events; a recent **anomaly burst** (implausible raw values) makes its health show *Anomalous*. |
| All sources | Scattered `unavailable` (~1.5 %), `delayed` and `anomalous` records so degraded-operation paths are exercised. |

### Rainfall categories (configurable defaults)

| Bucket | Range (24 h, mm) |
|--------|------------------|
| dry | < 0.1 |
| light | 0.1 – 15.5 |
| moderate | 15.6 – 64.4 |
| heavy | 64.5 – 115.5 |
| very heavy | 115.6 – 204.4 |
| extreme | > 204.4 |

Thresholds are prototype defaults in `backend/app/config.py`
(`Settings.light_max_mm`, `moderate_max_mm`, `heavy_max_mm`,
`very_heavy_max_mm`) and may be changed without touching engine logic.

### Source health rules (configurable)

Evaluated over the most recent `VARSHA_HEALTH_WINDOW_DAYS` (default 14) days,
cascade order **Unavailable → Anomalous → Delayed → Healthy**:

| Status | Rule |
|--------|------|
| Unavailable | ≥ 50 % of window records are `unavailable`, or the source has no records |
| Anomalous | ≥ 15 % of window records are `anomalous` |
| Delayed | ≥ 15 % of window records are `delayed` |
| Healthy | otherwise |

---

## Model features and artifacts (Phase 4)

The local correction model is trained on **features derived from the files
above** — never on the target of the date being predicted. Features are built by
`backend/app/services/features.py`; the full machine-readable version of this
table is returned in `feature_schema.feature_docs` by `GET /model/report`.

**Target column:** `target_observed_rain_mm` = `observed_rain_mm` of the same
`(district_id, valid_date, lead_hours)` row. It is attached to the training
frame **only as a label** and is never part of any feature vector.

**Feature schema version:** `features-v1` (in artifacts; a schema change
invalidates old artifacts instead of silently reusing them).

### Features (16)

| Feature | Type | Source | Timing | Why it cannot leak the target |
|---------|------|--------|--------|------------------------------|
| `nwp_rain_mm` | numeric | `historical_forecasts_synthetic.csv` (`nwp_model_a.forecast_rain_mm`) | raw forecast for date D, issued at D − lead | raw value only; never bias-corrected or blended; contains no observation |
| `ensemble_mean_mm` | numeric | same file (`ensemble_mean.forecast_rain_mm`) | raw forecast for date D, issued at D − lead | raw value only; no observation enters this column |
| `ensemble_spread_mm` | numeric | same file (`ensemble_spread_mm`) | published with the ensemble forecast for D | forecast-side statistic; imputed with the train-split median when absent |
| `prior_temp_c` | numeric | `observations_synthetic.csv` (`observed_temp_c`, lead 24 series) | latest observation strictly before D | window is `date < D`; the value on D itself is never read |
| `prior_wind_kmph` | numeric | same file (`observed_wind_kmph`, lead 24 series) | latest observation strictly before D | window is `date < D` |
| `prior_rain_1d_mm` | numeric | same file (`observed_rain_mm`, lead 24 series) | observation on D−1 only | lag-1 shift |
| `prior_rain_3d_total_mm` | numeric | same file (lead 24 series) | sum over [D−3, D−1] | rolling window ends at D−1 |
| `prior_rain_3d_mean_mm` | numeric | same file (lead 24 series) | mean over [D−3, D−1] | rolling window ends at D−1 |
| `prior_rain_7d_total_mm` | numeric | same file (lead 24 series) | sum over [D−7, D−1] | rolling window ends at D−1 |
| `prior_rain_7d_mean_mm` | numeric | same file (lead 24 series) | mean over [D−7, D−1] | rolling window ends at D−1 |
| `nwp_prior_ok_ratio` | numeric | `historical_forecasts_synthetic.csv` (`status`, `nwp_model_a`) | share of `status == "ok"` over [D−14, D−1] | forecast status only (no observations), window strictly before D |
| `ensemble_prior_ok_ratio` | numeric | same file (`status`, `ensemble_mean`) | share of `status == "ok"` over [D−14, D−1] | forecast status only, window strictly before D |
| `month` | numeric | derived from `valid_date` | known at issue time | pure calendar feature |
| `lead_hours` | numeric | request parameter (6 / 24 / 72) | known at issue time | configuration value (constant per trained model) |
| `district` | categorical | `districts.csv` (`district_id`) | known at issue time | one-hot encoded with train-fitted categories (`handle_unknown="ignore"`) |
| `season` | categorical | derived from the month of `valid_date` | known at issue time | pure calendar feature (Monsoon / Post-monsoon / Winter / Pre-monsoon) |

**Explicitly excluded:** the observation of date D or later, the bias-corrected
or blended values, the Phase 2 trust weights, the regime label of D, any
confidence or risk output, and every Phase 3 backtest metric.

### Per-row availability flags

Every feature row carries a `feature_availability` value and, when it is not
`ok`, a `feature_skip_reason`. The value depends only on **feature-side**
inputs, so it is identical at training and at inference time:

| `feature_availability` | Meaning |
|------------------------|---------|
| `ok` | all 16 features are available |
| `missing_forecast` | the NWP or ensemble input for date D is absent, `unavailable`/`anomalous`, or outside the plausible range |
| `insufficient_history` | fewer than `ml_min_feature_history_days` (default 7) usable prior observation days before D |

Rows that are not `ok` are excluded from training and, at inference time, cause
the disclosed `fallback_precomputed_ai_source` path with the reason echoed in
the forecast response.

### Training frame row counts (default dataset, 24 h horizon)

| Bucket | Rows |
|--------|------|
| total (5 districts × 120 dates) | 600 |
| `insufficient_history` | 31 (the first 7 dates) |
| `missing_forecast` | 44 (scattered `unavailable` records) |
| usable (features + target) | 525 → 302 train / 113 validation / 110 test |

### Artifacts (`data/models/`, configurable via `VARSHA_MODELS_DIR`)

| File | Content |
|------|---------|
| `varsha_ai_local_<lead>h.joblib` | joblib bundle: fitted sklearn `Pipeline` (imputer + scaler / one-hot + regressor), `model_version`, `lead_hours`, `feature_schema_version`, `selected_model`, `trained_at`, data mode, disclaimer |
| `varsha_ai_local_<lead>h_report.json` | the full training report: split boundaries and record counts, per-candidate validation metrics, selection rationale, the single held-out test evaluation, reference comparisons, honesty flags, provenance, warnings, limitations |

One model is trained **per lead horizon** (6 / 24 / 72). The `.joblib` files are
git-ignored; they are regenerated by `POST /model/train` or
`python -m app.train_model`.

---
## Replacing the synthetic data later

All data access goes through `backend/app/adapters/base.py`
(`HistoricalReplayAdapter`). To switch to real replay or authorised live data:

1. Implement a new adapter with `load_districts()`, `load_forecasts()`,
   `load_observations()` and `describe()`.
2. Set `VARSHA_DATA_MODE=historical_replay` and point `VARSHA_DATA_DIR` (or the
   adapter) at the new source.
3. Keep the same column contract documented above.

No service, router or test needs to change.
