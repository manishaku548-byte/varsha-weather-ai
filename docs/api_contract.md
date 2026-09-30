# API Contract — VARSHA Weather AI (Phases 1–5)

> **Decision-Support Prototype — Synthetic Development Dataset — Not
> Operational Weather Data — Not an Official Weather Warning.**

Base URL (local): `http://127.0.0.1:8000` (or `--port 8001`)
Interactive documentation: `/docs` · Raw schema: `/openapi.json`

Every response carries these two fields (or their parent object does):

| Field | Value |
|-------|-------|
| `disclaimer` | `Decision-Support Prototype — Synthetic Development Dataset — Not Operational Weather Data — Not an Official Weather Warning.` |
| `data_label` | `Synthetic Development Dataset — Not Operational Weather Data` |

Error shape follows FastAPI conventions: `{"detail": "<message>"}`. Phase 2
forecast errors use a structured detail object (see the error tables below).

---

## Phase 1 — implemented and tested

### GET /health

Service liveness plus dataset/database status. Works even when the dataset is
unavailable (`status = "degraded"`).

```json
{
  "status": "ok",
  "service": "VARSHA Weather AI",
  "version": "0.4.0",
  "phase": "Phase 4: AI/ML Local Correction Model",
  "problem_statement_id": "SIH26081",
  "data_mode": "synthetic",
  "data_label": "Synthetic Development Dataset — Not Operational Weather Data",
  "disclaimer": "Decision-Support Prototype — Synthetic Development Dataset — Not Operational Weather Data — Not an Official Weather Warning.",
  "dataset_loaded": true,
  "database_status": "connected",
  "records": {"districts": 5, "forecast_records": 5400, "observation_records": 1800}
}
```

### GET /districts

The five configured MVP districts.

Response: `{ data_mode, data_label, disclaimer, count, districts: [...] }` where
each district is `{ district_id, district_name, state, latitude, longitude }`.

### GET /data/summary

Descriptive summary of the loaded dataset — **never a forecast**.

| Query param | Type | Required | Description |
|-------------|------|----------|-------------|
| `district` | string | no | District id **or** name filter (case-insensitive) |

Response highlights:

* `district_count`, `first_valid_date`, `last_valid_date`, `lead_hours`
* `total_forecast_records`, `total_observation_records`
* `sources[]` — source metadata (`source_id`, `source_type`, `display_name`, `description`)
* `source_record_counts` — rows per source
* `source_status_counts` — `source_id → status → count`
* `source_health[]` — `{ source_id, source_type, status, window_days,
  records_in_window, unavailable_ratio, delayed_ratio, anomalous_ratio, reason }`
  with `status ∈ {Healthy, Delayed, Unavailable, Anomalous}`
* `rainfall_24h_overall` and `districts[].rainfall_24h` — bucket counts
* `validation` — `{ structure_ok, blocking_issues[], quality_flags{}, checked_* }`

**Errors**

| Status | When | Example detail |
|--------|------|----------------|
| 404 | Unknown `district` value | `{ "error": "unknown_district", "message": …, "available_districts": [...] }` (from `/forecast`); string message from `/data/summary` |
| 503 | Dataset files missing | `Required dataset file 'districts.csv' not found …` (+ `hint` with the generator command) |

---

## Phase 2 — implemented and tested (Forecast Intelligence Engine)

All three endpoints compute everything from the stored replay dataset. The
same pipeline runs for each: **bias correction → regime detection → Dynamic
Trust Engine → blending → confidence/uncertainty → risk**.

* Bias, skill, health and regime context only ever read records **strictly
  earlier than the selected `date`** — never the selected date's own
  observations.
* Display rounding happens only in the API layer (mm → 2 decimals, weights →
  4 decimals with a residual fix so weights sum to exactly `1.0`).
* Audit fields: `algorithm_version` (blending algorithm) and
  `config_version` (thresholds/weights) are returned on every forecast
  response.

### GET /forecast

| Query param | Type | Required | Description |
|-------------|------|----------|-------------|
| `district` | string | yes | District id or name, e.g. `Prayagraj` |
| `date` | string | yes | Valid date `YYYY-MM-DD` inside the dataset range |
| `lead_hours` | int | yes | One of `6`, `24`, `72` |
| `simulate_failure_source` | string | no | `nwp` \| `ensemble` \| `ai` — excludes one source for this request |

Response structure (abridged — see `example_forecast` in the demo script for
a full payload):

```json
{
  "disclaimer": "Decision-Support Prototype — Synthetic Development Dataset — Not Operational Weather Data — Not an Official Weather Warning.",
  "data_mode": "synthetic",
  "data_label": "Synthetic Development Dataset — Not Operational Weather Data",
  "algorithm_version": "varsha-blend-2.0.0",
  "config_version": "phase2-defaults-v1",
  "district": {"district_id": "prayagraj", "district_name": "Prayagraj"},
  "valid_date": "2025-09-15",
  "lead_hours": 24,
  "issue_time": "2025-09-14T00:00:00Z",
  "validity_start": "2025-09-14T00:00:00Z",
  "validity_end": "2025-09-15T00:00:00Z",
  "simulate_failure_source": null,

  "data_availability": {
    "dataset_first_valid_date": "2025-06-01",
    "dataset_last_valid_date": "2025-09-28",
    "records_found_for_point": 3,
    "available_sources": ["nwp_model_a", "ensemble_mean", "ai_local_v1"],
    "unavailable_sources": [],
    "data_available": true
  },
  "prior_context": {
    "trailing_3day_mm": 0.0,
    "temp_c": 30.3,
    "humidity_pct": 62.8,
    "prior_observation_days": 106,
    "context_note": "Temperature, humidity and trailing rainfall are taken from observations strictly earlier than 2025-09-15."
  },

  "weather_regime": {
    "label": "Normal",
    "confidence": 0.822,
    "triggered_rules": [],
    "thresholds_used": {"heavy_rain_mm": 64.5, "heatwave_temp_c": 40.0, "…": 0},
    "reason": "No heavy-rain, heatwave or monsoon rule triggered (…); peak blend-input rainfall is 16.7 mm against a 64.5 mm heavy threshold.",
    "rule_version": "regime-rules-v1",
    "certification_note": "Prototype rule set — no meteorological operational certification claimed."
  },

  "source_health": [
    {"source_id": "nwp_model_a", "status": "Healthy", "window_days": 14, "records_in_window": 210, "…": 0, "reason": "… Window ends 2025-09-15."}
  ],

  "sources": [
    {
      "source_id": "nwp_model_a",
      "display_name": "NWP Model A (synthetic)",
      "available": true,
      "record_found": true,
      "status": "ok",
      "quality_flag": "good",
      "raw_forecast_mm": 5.3,
      "corrected_forecast_mm": 16.67,
      "bias": {
        "method": "mean_bias_prior_only",
        "bias_available": true,
        "bias_mm": 11.37,
        "raw_forecast_mm": 5.3,
        "corrected_forecast_mm": 16.67,
        "historical_record_count": 98,
        "reason": "Mean bias +11.37 mm computed from 98 record(s) strictly earlier than 2025-09-15 (mean_bias_prior_only)."
      },
      "trust": {
        "eligible": true,
        "health_status": "Healthy",
        "health_score": 1.0,
        "historical_mae_mm": 13.5,
        "historical_record_count": 98,
        "historical_skill": 0.6494,
        "recent_mae_mm": 13.53,
        "recent_record_count": 14,
        "recent_skill": 0.6489,
        "agreement": 0.0,
        "context_factor": 1.0,
        "trust_score": 0.622,
        "weight": 0.2607,
        "reason": "prior skill MAE 13.5 mm over 98 record(s); … Trust 0.622 -> weight 0.261."
      },
      "weight": 0.2607,
      "ensemble": null,
      "unavailable_reason": null
    }
  ],

  "blend": {
    "final_rainfall_mm": 4.61,
    "formula": "final_rainfall_mm = sum(weight x corrected_forecast)",
    "fallback_mode": "normal",
    "fallback_note": "normal blend: all three sources contributed with normalized weights.",
    "available_source_count": 3,
    "contributions": [
      {"source_id": "nwp_model_a", "weight": 0.2607, "corrected_mm": 16.67, "contribution_mm": 4.35}
    ],
    "unavailable_sources": []
  },
  "fallback_mode": "normal",

  "confidence": {
    "score": 87.5,
    "label": "High",
    "bands": "Low 0-39 | Medium 40-69 | High 70-100",
    "factors": {"available_sources": 1.0, "historical_skill": 0.7734, "health": 1.0, "agreement": 0.7158, "ensemble_spread": 0.9259},
    "explanation": ["available sources: 3/3 (100%)", "weighted historical skill: 0.77 (0-1, inverse MAE)", "…"],
    "uncertainty_lower_mm": 0.0,
    "uncertainty_upper_mm": 11.78,
    "uncertainty_half_width_mm": 7.17,
    "uncertainty_basis": "prototype heuristic interval = max(weighted source disagreement, ensemble spread, blend x (100 - confidence)/100); not a calibrated prediction interval"
  },

  "risk": {
    "event_type": "heavy_rainfall",
    "risk_level": "Low",
    "predicted_rainfall_mm": 4.61,
    "validity_start": "2025-09-14T00:00:00Z",
    "validity_end": "2025-09-15T00:00:00Z",
    "confidence_score": 87.5,
    "confidence_label": "High",
    "regime": "Normal",
    "escalated": false,
    "reasons": ["Amount: blended rainfall 4.6 mm < moderate threshold 15.6 mm.", "…"],
    "preparedness_actions": ["Continue routine monitoring of district reports.", "…"],
    "thresholds_used": {"moderate_mm": 15.6, "heavy_mm": 64.5, "very_heavy_mm": 115.6, "extreme_mm": 204.5},
    "disclaimer": "Decision-support output only; not an official warning."
  }
}
```

Field semantics:

* `sources[].bias` — raw forecast, bias amount, corrected forecast, prior
  record count and availability for **every** source; when history is too
  short: `bias_available=false`, `bias_mm=null`, `reason="Insufficient prior
  history"`, raw value kept unchanged.
* `sources[].trust` — every score component stored separately
  (`historical_skill`, `recent_skill`, `health_score`, `agreement`,
  `context_factor`) plus the combined `trust_score` and normalized `weight`.
* `blend.fallback_mode` — `normal` (3 sources) · `degraded` (2) ·
  `single_source` (1, weight exactly `1.0`, note says "single-source
  fallback").
* `weather_regime.label` — priority order Heavy-Rain Risk > Heatwave >
  Active Monsoon > Normal; `confidence` is 0–1; `triggered_rules` and
  `thresholds_used` expose the exact rules/values evaluated.
* `confidence.score` 0–100 → label bands Low 0–39 · Medium 40–69 · High
  70–100; caps: `single_source → ≤39`, `degraded → ≤69`.
* `risk` always includes the non-binding note
  `"Decision-support output only; not an official warning."`

**Errors**

| Status | When | Detail |
|--------|------|--------|
| 404 | Unknown district | `{"error": "unknown_district", "message": …, "available_districts": [...]}` |
| 404 | Date outside dataset range | `{"error": "date_out_of_range", "message": "Date '…' is outside the loaded dataset range 2025-06-01 to 2025-09-28.", "hint": …}` |
| 422 | Missing/invalid params, `lead_hours` not in {6,24,72}, bad failure alias | `{"error": "invalid_lead_hours", "message": …, "allowed": [6,24,72]}` or FastAPI validation detail |
| 503 | **No source valid** (all records missing/unusable/failed) | `{"error": "forecast_unavailable", "message": "Forecast unavailable — no usable source … <per-source reasons>", "hint": …, "disclaimer": …}` |

### GET /forecast/explain

Same query parameters as `/forecast`. Returns a compact plain-language view
built from the **same computed numbers**:

```json
{
  "disclaimer": "…",
  "data_mode": "synthetic",
  "data_label": "Synthetic Development Dataset — Not Operational Weather Data",
  "algorithm_version": "varsha-blend-2.0.0",
  "config_version": "phase2-defaults-v1",
  "district": {"district_id": "prayagraj", "district_name": "Prayagraj"},
  "valid_date": "2025-09-15",
  "lead_hours": 24,
  "headline": "Prayagraj: about 4.6 mm of rain blended for 2025-09-15 (24h lead) — Normal regime, Low risk, High confidence (88/100).",
  "final_rainfall_mm": 4.61,
  "regime": { "label": "Normal", "confidence": 0.822, "…": "…" },
  "confidence": { "score": 87.5, "label": "High", "…": "…" },
  "risk": { "risk_level": "Low", "event_type": "heavy_rainfall", "…": "…" },
  "top_weighted_source": {
    "source_id": "ensemble_mean",
    "display_name": "Ensemble Mean (synthetic)",
    "health_status": "Healthy",
    "corrected_forecast_mm": 0.67,
    "weight": 0.3894,
    "reason": "prior skill MAE 2.9 mm over 99 record(s); …"
  },
  "sources": [ "…one line per source…" ],
  "source_health_note": "Source health (window ending 2025-09-15): … . normal blend: …",
  "fallback_mode": "normal",
  "fallback_note": "normal blend: all three sources contributed with normalized weights.",
  "why_this_forecast_title": "Why this forecast?",
  "why_this_forecast": [
    "Blend: 4.6 mm = 0.26 x 16.7 mm + 0.39 x 0.7 mm + 0.35 x 0.0 mm (algorithm varsha-blend-2.0.0, config phase2-defaults-v1).",
    "Top-weighted source: Ensemble Mean (synthetic) (weight 0.39) — …",
    "Weather regime Normal (rule confidence 0.82): …",
    "Source health: NWP Model A (synthetic) = Healthy, … (window ending 2025-09-15).",
    "Confidence 88/100 (High): …",
    "Risk Low (heavy_rainfall): … Decision-support output only; not an official warning.",
    "Bias correction: NWP Model A (synthetic) +11.37 mm from 98 prior record(s); …",
    "normal blend: all three sources contributed with normalized weights.",
    "All bias, skill, health and regime context use records strictly earlier than 2025-09-15; no observation from the selected date or later is used."
  ]
}
```

Errors are identical to `/forecast` (same parameters, same pipeline).

### POST /forecast/simulate-source-failure

Request body:

```json
{
  "district": "Prayagraj",
  "date": "2025-09-15",
  "lead_hours": 24,
  "failed_source": "ensemble"
}
```

Response — normal run vs degraded run plus an explicit diff:

```json
{
  "disclaimer": "Decision-Support Prototype — Synthetic Development Dataset — Not Operational Weather Data — Not an Official Weather Warning.",
  "data_mode": "synthetic",
  "data_label": "Synthetic Development Dataset — Not Operational Weather Data",
  "algorithm_version": "varsha-blend-2.0.0",
  "config_version": "phase2-defaults-v1",
  "district": {"district_id": "prayagraj", "district_name": "Prayagraj"},
  "valid_date": "2025-09-15",
  "lead_hours": 24,
  "failed_source": "ensemble",
  "failed_source_id": "ensemble_mean",

  "normal": {
    "final_rainfall_mm": 4.61,
    "confidence_score": 87.5,
    "confidence_label": "High",
    "fallback_mode": "normal",
    "weights": {"nwp_model_a": 0.2607, "ensemble_mean": 0.3894, "ai_local_v1": 0.3499},
    "available_sources": ["nwp_model_a", "ensemble_mean", "ai_local_v1"],
    "regime": "Normal",
    "risk_level": "Low"
  },
  "degraded": {
    "final_rainfall_mm": 7.89,
    "confidence_score": 61.5,
    "confidence_label": "Medium",
    "fallback_mode": "degraded",
    "weights": {"nwp_model_a": 0.4734, "ensemble_mean": 0.0, "ai_local_v1": 0.5266},
    "available_sources": ["nwp_model_a", "ai_local_v1"],
    "regime": "Normal",
    "risk_level": "Low"
  },

  "weight_changes": [
    {"source_id": "nwp_model_a", "display_name": "NWP Model A (synthetic)", "weight_before": 0.2607, "weight_after": 0.4734, "delta": 0.2126, "trust_score_before": 0.622, "trust_score_after": 0.6469},
    {"source_id": "ensemble_mean", "display_name": "Ensemble Mean (synthetic)", "weight_before": 0.3894, "weight_after": 0.0, "delta": -0.3894, "trust_score_before": 0.9289, "trust_score_after": 0.0},
    {"source_id": "ai_local_v1", "display_name": "AI Local Correction v1 (synthetic)", "weight_before": 0.3499, "weight_after": 0.5266, "delta": 0.1767, "trust_score_before": 0.8347, "trust_score_after": 0.7197}
  ],
  "confidence_change": {"normal": 87.5, "degraded": 61.5, "delta": -26.0},
  "rainfall_change_mm": 3.28,
  "fallback_mode_change": {"normal": "normal", "degraded": "degraded"},
  "explanation": [
    "Simulated failure of 'ensemble' (Ensemble Mean (synthetic)): weight 0.39 -> 0.00 (trust forced to 0.0, weight 0.0).",
    "Weight redistribution: NWP Model A (synthetic) 0.26 -> 0.47 (+0.21); AI Local Correction v1 (synthetic) 0.35 -> 0.53 (+0.18).",
    "Confidence changed 88 -> 62 (-26 points); fallback mode normal -> degraded.",
    "Blended rainfall changed 4.6 -> 7.9 mm (+3.3 mm).",
    "Decision-Support Prototype — Synthetic Development Dataset — Not Operational Weather Data — Not an Official Weather Warning."
  ]
}
```

**Errors**

| Status | When |
|--------|------|
| 404 | Unknown district, or date outside the dataset range |
| 422 | Missing/invalid body fields, `failed_source` not in `nwp\|ensemble\|ai`, malformed `date` |

---

## Phase 3 — implemented and tested (Backtesting & Numeric Evaluation)

Every number below is computed from actual engine outputs and observations on
the stored synthetic dataset. Each date `D` runs the **Phase 2 engine in
strictly historical mode** — bias, skill, regime context and dynamic weights
may only use records **earlier than `D`**; the observation of `D` is used
solely as verification truth. Normal runs never mutate forecast data.

> Every response and report file carries:
> `Synthetic Development Dataset — Development/Testing Only — Not Operational Weather Data — Not an Official Weather Warning.`

### GET /backtest

| Query param | Type | Required | Default | Description |
|-------------|------|----------|---------|-------------|
| `district` | string | yes | — | District id or name |
| `lead_hours` | int | yes | — | `6`, `24` or `72` |
| `start_date` | string | yes | — | First date, `YYYY-MM-DD` (inclusive) |
| `end_date` | string | yes | — | Last date, `YYYY-MM-DD` (inclusive) |
| `minimum_history_days` | int | no | `14` | Skip dates with fewer prior history days |
| `heavy_rain_threshold_mm` | float | no | `64.5` | 24h-equivalent event threshold override (scaled by `lead_hours/24`) |
| `include_daily_rows` | bool | no | `false` | Include per-date rows in the response |

Response structure:

```json
{
  "data_mode": "synthetic",
  "disclaimer": "Synthetic Development Dataset — Development/Testing Only — Not Operational Weather Data — Not an Official Weather Warning.",
  "algorithm_version": "varsha-blend-2.0.0",
  "config_version": "phase2-defaults-v1",
  "request": {"district": "Prayagraj", "district_id": "prayagraj", "lead_hours": 24,
              "start_date": "2025-07-01", "end_date": "2025-07-20",
              "minimum_history_days": 14, "heavy_rain_threshold_mm": 64.5,
              "include_daily_rows": false},
  "data_range": {"dataset_first_valid_date": "2025-06-01", "dataset_last_valid_date": "2025-09-28",
                 "requested_start_date": "2025-07-01", "requested_end_date": "2025-07-20",
                 "dates_in_dataset_range": 20},
  "evaluation_summary": {
    "total_requested_dates": 20, "evaluated_dates": 20, "skipped_dates": 0,
    "skipped_reason_counts": {"missing_observation": 0, "missing_forecast": 0,
                              "invalid_data": 0, "insufficient_history": 0,
                              "no_valid_source": 0},
    "sufficient_sample_warning": null
  },
  "event_threshold": {"configured_threshold_mm": 64.5, "effective_threshold_mm": 64.5,
                      "lead_hours": 24, "scaling_applied": true, "basis": "…"},

  "methods": {
    "nwp": {
      "display_name": "NWP bias-corrected",
      "regression_metrics": {"sample_count": 19, "mae_mm": 19.9376, "rmse_mm": 24.9138,
                             "mean_bias_error_mm": -3.7441, "median_absolute_error_mm": 16.4,
                             "max_absolute_error_mm": 71.2, "note": null},
      "event_metrics": {"threshold_mm": 64.5, "sample_count": 19, "event_count": 6,
                        "predicted_event_count": 2, "true_positives": 2, "false_positives": 0,
                        "true_negatives": 13, "false_negatives": 4, "precision": 1.0,
                        "recall": 0.3333, "f1_score": 0.5, "false_alarm_rate": 0.0,
                        "missed_event_rate": 0.6667, "notes": [],
                        "low_event_sample_warning": "…statistically weak…"}
    },
    "ensemble": {"…": "…"},
    "ai_local": {"…": "…"},
    "equal_weight": {"…": "…"},
    "varsha_dynamic_blend": {"…": "…"}
  },

  "comparison_summary": {
    "delta_definition": "Deltas are VARSHA minus baseline: …",
    "outcome_basis": "Verdicts compare MAE with a ±0.5 mm similarity tolerance.",
    "best_method_by_metric": {"mae_mm": "ensemble", "rmse_mm": "ensemble", "…": "…"},
    "best_single_source": "ensemble",
    "varsha_vs_equal_weight_mae_delta_mm": -0.7334,
    "varsha_vs_best_single_source_mae_delta_mm": 3.0754,
    "varsha_vs_equal_weight_recall_delta": 0.0,
    "varsha_vs_best_single_source_recall_delta": -0.1667,
    "sufficient_sample": true,
    "note": null,
    "outcome_summary": [
      "VARSHA performed better than the equal-weight average for this selected synthetic evaluation period (MAE 5.916 mm vs 6.649 mm, delta -0.733 mm).",
      "VARSHA performed worse than the best single source (Ensemble forecast) for this selected synthetic evaluation period (MAE 5.916 mm vs 2.840 mm, delta +3.075 mm)."
    ]
  },

  "daily_rows": null,
  "limitations": ["Synthetic Development Dataset — Development/Testing Only — …", "…"],
  "report_files": {"csv": "backtest_prayagraj_24h_2025-07-01_2025-07-20.csv",
                   "json": "backtest_prayagraj_24h_2025-07-01_2025-07-20.json"}
}
```

Notes:

* **Methods** — `nwp` (bias-corrected), `ensemble`, `ai_local`,
  `equal_weight` (mean of valid available corrected sources) and
  `varsha_dynamic_blend`. Each method's metrics use only the included rows
  where **that method** produced a prediction, so `sample_count` may differ
  per method.
* **Skips** — a date is skipped with exactly one reason
  (`missing_observation` → `missing_forecast` → `invalid_data` →
  `insufficient_history` → `no_valid_source`, checked in that order) and the
  row is still listed in the CSV and (when requested) in `daily_rows`.
* **Empty metrics** — with no evaluated rows every metric is `null` with an
  explanatory `note`; zero-division event scores are `null` with `notes[]`.
* **Insufficient sample** — fewer than 20 evaluated dates sets
  `sufficient_sample_warning`/`note` to
  `"Insufficient evaluation sample for reliable comparison."` and the
  `outcome_summary` contains only that sentence.
* **Honesty guarantee** — `best_method_by_metric` and
  `best_single_source` are argmins/argmaxima of the returned metrics; VARSHA
  is never assumed to win (see the example above: the ensemble wins MAE).
* **Rounding** — API display rounds floats to 4 decimals; report files keep
  full precision.
* `daily_rows` is present only when `include_daily_rows=true`.

**Errors**

| Status | When | Detail |
|--------|------|--------|
| 404 | Unknown district | `{"error": "unknown_district", …, "available_districts": [...]}` |
| 422 | `lead_hours` not in {6,24,72} | `{"error": "invalid_lead_hours", "allowed": [6,24,72]}` |
| 422 | `start_date > end_date` | `{"error": "invalid_date_range", …}` |
| 422 | Range longer than 366 dates | `{"error": "backtest_range_too_large", "max_dates": 366, …}` |
| 422 | Negative `minimum_history_days` | `{"error": "invalid_minimum_history_days", …}` |
| 422 | `heavy_rain_threshold_mm <= 0`, missing params | FastAPI validation detail |

### GET /backtest/report

Same range parameters as `/backtest` (`minimum_history_days` and
`heavy_rain_threshold_mm` are honoured when the report has to be generated)
plus:

| Query param | Type | Required | Default | Description |
|-------------|------|----------|---------|-------------|
| `format` | string | no | `json` | `json` = report summary in the response, `csv` = file download |

* `format=json` returns the most recent matching stored report, otherwise
  generates it first. The response echoes the stored metadata plus
  `report_source: "stored" | "generated"`:

```json
{
  "report_type": "backtest",
  "report_source": "stored",
  "generated_at": "2026-09-28T00:00:00Z",
  "algorithm_version": "varsha-blend-2.0.0",
  "config_version": "phase2-defaults-v1",
  "data_mode": "synthetic",
  "disclaimer": "Synthetic Development Dataset — Development/Testing Only — Not Operational Weather Data — Not an Official Weather Warning.",
  "request": {"…": "…"},
  "data_range": {"…": "…"},
  "evaluation_summary": {"…": "…"},
  "event_threshold": {"…": "…"},
  "methods": {"nwp": {"regression_metrics": {"…": "…"}, "event_metrics": {"…": "…"}}},
  "metrics_table": [{"method": "nwp", "display_name": "NWP bias-corrected", "sample_count": 19, "mae_mm": 19.9376, "…": "…"}],
  "comparison_summary": {"…": "…"},
  "row_counts": {"total": 20, "evaluated": 20, "skipped": 0},
  "files": {"csv": "backtest_prayagraj_24h_2025-07-01_2025-07-20.csv",
            "json": "backtest_prayagraj_24h_2025-07-01_2025-07-20.json"},
  "limitations": ["…"]
}
```

* `format=csv` streams the stored CSV with
  `Content-Type: text/csv; charset=utf-8` and
  `Content-Disposition: attachment; filename="backtest_<…>.csv"`
  (generated first when missing).

**Report files** (deterministic names, written under `data/reports/`):

* `backtest_<district_slug>_<lead>h_<start>_<end>.csv` — columns:
  `date, district, lead_hours, actual_rain_mm, nwp_prediction_mm,
  ensemble_prediction_mm, ai_prediction_mm, equal_weight_prediction_mm,
  varsha_prediction_mm, regime, nwp_weight, ensemble_weight, ai_weight,
  confidence_score, confidence_label, risk_level, fallback_mode,
  included_in_evaluation, skip_reason, nwp_source_health,
  ensemble_source_health, ai_source_health, prior_history_days, data_mode,
  disclaimer` — one row per requested date (included **and** skipped).
* `backtest_<district_slug>_<lead>h_<start>_<end>.json` — the metadata
  payload shown above (full precision).

Filenames are sanitized and regex-validated; paths are re-checked against
`data/reports/`, so directory traversal is impossible. A report is only
reused when its stored request parameters (`minimum_history_days`,
`heavy_rain_threshold_mm`) match the request.

**Errors** — same as `/backtest`, plus `422` for `format` outside
`json|csv`.

---

## Phase 4 — implemented and tested (AI/ML Local Correction Model)

The synthetic `ai_rain_mm` column is no longer the only AI source. A **local
correction model** (scikit-learn, trained on the stored dataset only) supplies
the `ai_local_v1` value when a validated artifact exists, and the precomputed
column is used as an **explicitly labelled fallback** otherwise. Training never
happens at startup.

> Every response and report from this phase carries:
> `Synthetic Development Dataset — Development/Testing Only — Not Operational Weather Data — Not an Official Weather Warning.`

### AI-source labels

| `source_label` | `model_inference_available` | Meaning |
|----------------|-----------------------------|---------|
| `trained_local_correction_model` | `true` | the value is the trained pipeline's prediction for this point (clipped to `max_plausible_rain_mm`) |
| `fallback_precomputed_ai_source` | `false` | the value is the precomputed `ai_rain_mm` CSV column; `reason` says why |

The switch is never silent: `GET /forecast` and `GET /forecast/explain` both
return a `ml_model` block, and the AI source entry inside `sources[]` carries
`source_label`, `model_inference_available`, `model_version`,
`model_report_reference` and `model_inference_reason`. All other sources report
`null` for those fields.

### POST /model/train

The only training trigger. Also available as
`python -m app.train_model --lead-hours {6|24|72} [--force] [--minimum-samples N]`.

| Body field | Type | Default | Description |
|------------|------|---------|-------------|
| `lead_hours` | int | required | `6`, `24` or `72` — one model per horizon |
| `minimum_samples` | int | `null` | Minimum required training rows; overrides `ml_min_train_rows` |
| `force_retrain` | bool | `false` | Retrain even when a validated artifact already exists |

Response (abridged, values from a real 24 h run on the default dataset):

```json
{
  "report_type": "local_correction_model",
  "status": "completed",
  "model_version": "ai-local-24h-20260929T062009Z",
  "generated_at": "2026-09-29T06:20:09Z",
  "trained_at": "2026-09-29T06:20:09Z",
  "lead_hours": 24,
  "data_mode": "synthetic",
  "disclaimer": "Synthetic Development Dataset — Development/Testing Only — Not Operational Weather Data — Not an Official Weather Warning.",
  "selected_model": "linear_regression",

  "feature_schema": {
    "version": "features-v1",
    "feature_columns": ["nwp_rain_mm", "…": "… (16 total, exact pipeline column order)"],
    "numeric_features": ["nwp_rain_mm", "…": "… (14 total)"],
    "categorical_features": ["district", "season"],
    "target": "target_observed_rain_mm",
    "feature_availability_values": ["ok", "missing_forecast", "insufficient_history"],
    "feature_docs": [{"feature": "nwp_rain_mm", "type": "numeric", "source": "…", "timing": "…", "leakage_safeguard": "…"}]
  },

  "split": {
    "method": "chronological_by_unique_global_date",
    "description": "…",
    "ratio": {"train": 0.6, "validation": 0.2, "test": 0.2},
    "alternate_ratio_applied": false,
    "warning": null,
    "record_counts": {"total_unique_dates": 120, "…": "…"},
    "boundaries": {
      "train":      {"start": "2025-06-01", "end": "2025-08-11", "dates": 72},
      "validation": {"start": "2025-08-12", "end": "2025-09-04", "dates": 24},
      "test":       {"start": "2025-09-05", "end": "2025-09-28", "dates": 24}
    }
  },
  "record_counts": {"train": 302, "validation": 113, "test": 110, "total_usable": 525},
  "row_exclusions": {"total_rows": 600, "insufficient_history": 31, "missing_forecast": 44,
                     "missing_target": 0, "usable_rows": 525},

  "candidates": {
    "linear_regression": {
      "role": "baseline",
      "trained_on": "train",
      "evaluated_on": "validation",
      "validation_metrics": {"sample_count": 113, "mae_mm": 2.5628, "rmse_mm": 4.0366,
                             "mean_bias_error_mm": -0.4838, "…": "…"}
    },
    "hist_gradient_boosting": {
      "role": "nonlinear",
      "trained_on": "train",
      "evaluated_on": "validation",
      "validation_metrics": {"sample_count": 113, "mae_mm": 5.3089, "rmse_mm": 11.4023,
                             "mean_bias_error_mm": 2.2773, "…": "…"}
    }
  },
  "selection_rationale": "linear_regression selected: lowest validation MAE (2.562824307112073 mm) vs hist_gradient_boosting (5.308932521281937 mm). Selection used the validation split only — the held-out test set was not consulted.",

  "held_out_test_metrics": {"sample_count": 110, "mae_mm": 2.3692, "rmse_mm": 3.3161,
                            "mean_bias_error_mm": 1.9128, "median_absolute_error_mm": 1.8246,
                            "max_absolute_error_mm": 10.8589, "note": null},
  "test_references": {
    "naive_train_mean":       {"mae_mm": 35.952,  "description": "predict the mean of train+validation observed rainfall"},
    "raw_nwp":                {"mae_mm": 2.3191,  "description": "unmodified NWP value for the same rows"},
    "precomputed_ai_source":  {"mae_mm": 1.3878,  "description": "the precomputed synthetic ai_rain_mm value"}
  },
  "honesty": {
    "selection_metric": "validation_mae_only",
    "test_used_for_selection": false,
    "test_set_evaluated_once": true,
    "ml_worse_than_baseline": true,
    "worse_than_references": ["raw_nwp", "precomputed_ai_source"],
    "summary_sentences": [
      "Held-out test MAE 2.3691746339467485 mm is lower (better) than the naive_train_mean reference (35.95195618838992 mm).",
      "Held-out test MAE 2.3691746339467485 mm is higher (worse) than the raw_nwp reference (2.319090909090909 mm).",
      "Held-out test MAE 2.3691746339467485 mm is higher (worse) than the precomputed_ai_source reference (1.3877551020408165 mm)."
    ]
  },

  "fallback": {"active": false, "label": "trained_local_correction_model", "reason": null},
  "artifacts": {"pipeline_file": "varsha_ai_local_24h.joblib",
                "report_file": "varsha_ai_local_24h_report.json",
                "pipeline_path": "…\\data\\models\\varsha_ai_local_24h.joblib",
                "report_path": "…\\data\\models\\varsha_ai_local_24h_report.json"},
  "provenance": {
    "training_data": "Synthetic Development Dataset (seed 42) loaded from stored CSVs — development/testing only, not operational weather data.",
    "split_policy": "chronological_by_unique_global_date",
    "selection_policy": "Final model selected by validation MAE only.",
    "test_policy": "Held-out future test split evaluated exactly once after selection; never used for hyperparameter or model selection.",
    "preprocessing_policy": "Imputer, scaler and one-hot encoder are fitted on training rows only (single sklearn Pipeline fitted inside the train step).",
    "retraining_policy": "Trained once through POST /model/train; rolling-origin retraining is future scope (not in this MVP).",
    "algorithm_version": "varsha-blend-2.0.0",
    "config_version": "phase2-defaults-v1"
  },
  "warnings": ["The selected model's held-out test MAE is worse than reference predictor(s): raw_nwp, precomputed_ai_source. …"],
  "limitations": ["Synthetic Development Dataset — Development/Testing Only — …", "…"]
}
```

`status` values:

| `status` | When | Artifacts |
|----------|------|-----------|
| `completed` | training ran; the selected model was refit on train+validation and saved | written |
| `already_trained` | a valid artifact exists and `force_retrain` was not requested (echoes that report) | unchanged |
| `skipped_insufficient_data` | too few dates, or fewer than 200/50/50 train/validation/test rows | **none written** |

A skip is a first-class, honest outcome: `model_version` and
`held_out_test_metrics` are `null`, `warnings` explains the shortfall, and
`fallback.active` is `true` with label `fallback_precomputed_ai_source` — the
precomputed source keeps serving forecasts.

`already_trained` echoes the saved report with `status` rewritten and a
`message` such as
`A trained artifact already exists for 24h lead (ai-local-24h-20260929T070007Z); set force_retrain=true to retrain.`
The `message` key is `null` on a `completed` run. An existing artifact that
fails validation is not trusted: training re-runs and adds
`Existing artifact unusable (…); retraining.` to `warnings`.

**Errors**

| Status | When | Detail |
|--------|------|--------|
| 422 | `lead_hours` not in {6,24,72}, `minimum_samples < 1`, missing body | FastAPI validation detail (`loc` points at the field) |
| 422 | unsupported lead reaching the service | `{"error": "invalid_model_parameters", "message": "…"}` |

### GET /model/report

| Query param | Type | Required | Description |
|-------------|------|----------|-------------|
| `lead_hours` | int | no | `6`, `24` or `72`; defaults to the most recently trained horizon |

Returns the same payload as `POST /model/train` from the saved
`..._report.json` (full precision in the file, 4-decimal display rounding in the
API). It re-validates the artifact on read, so a bundle/report mismatch is
surfaced instead of being served.

**Errors**

| Status | When | Detail |
|--------|------|--------|
| 404 | nothing trained, or that horizon was never trained | `{"error": "model_not_trained", "message": "…", "lead_hours": 24}` |
| 404 | report file present but unreadable | `{"error": "model_report_unreadable", "message": "…"}` |
| 404 | report/pipeline mismatch (lead, feature schema, model version) | `{"error": "model_artifact_invalid", "message": "…", "lead_hours": 24}` |
| 422 | `lead_hours` not in {6,24,72} | `{"error": "invalid_lead_hours", "allowed": [6,24,72]}` |

### GET /model/status

No parameters; always available — including before anything has been trained.

```json
{
  "artifact_exists": true,
  "trained_lead_hours": [24],
  "model_version": "ai-local-24h-20260929T062009Z",
  "last_training_time": "2026-09-29T06:20:09Z",
  "inference_enabled": true,
  "inference_ready": true,
  "per_lead": {
    "6":  {"artifact_exists": false, "inference_ready": false, "model_version": null, "selected_model": null, "held_out_test_mae_mm": null},
    "24": {"artifact_exists": true,  "inference_ready": true,  "model_version": "ai-local-24h-20260929T062009Z", "selected_model": "linear_regression", "held_out_test_mae_mm": 2.3692},
    "72": {"artifact_exists": false, "inference_ready": false, "model_version": null, "selected_model": null, "held_out_test_mae_mm": null}
  },
  "fallback_status": {"active": false, "label": "trained_local_correction_model", "reason": null},
  "data_mode": "synthetic",
  "models_dir": "…\\data\\models",
  "note": "Training is never triggered at startup — it only runs through POST /model/train (or the app.train_model CLI).",
  "disclaimer": "Synthetic Development Dataset — Development/Testing Only — Not Operational Weather Data — Not an Official Weather Warning."
}
```

Before training, `artifact_exists=false`, `trained_lead_hours=[]`,
`inference_ready=false` and `fallback_status` is
`{"active": true, "label": "fallback_precomputed_ai_source", "reason": "No trained model artifact exists yet; POST /model/train first; GET /forecast uses the precomputed ai_rain_mm CSV source."}`.
Setting `VARSHA_ML_INFERENCE=false` while an artifact exists gives
`{"active": true, "label": "fallback_precomputed_ai_source", "reason": "ML inference disabled by configuration (VARSHA_ML_INFERENCE=false); GET /forecast uses the precomputed ai_rain_mm CSV source."}`.

### Phase 4 additions to existing endpoints

`GET /forecast` and `GET /forecast/explain` gain an additive `ml_model` block:

```json
"ml_model": {
  "source_label": "trained_local_correction_model",
  "model_inference_available": true,
  "model_version": "ai-local-24h-20260929T062009Z",
  "model_report_reference": "varsha_ai_local_24h_report.json",
  "ai_local_model_prediction_mm": 1.74,
  "feature_availability": "ok",
  "held_out_test_mae_mm": 2.3692,
  "reason": "ai_local_model_prediction_mm generated by trained model ai-local-24h-20260929T062009Z (selected: linear_regression; held-out test MAE 2.3692 mm; report varsha_ai_local_24h_report.json)."
}
```

and the AI source entry in `sources[]` gains
`model_inference_available`, `source_label`, `model_version`,
`model_report_reference`, `model_inference_reason`; with a model driving it,
`status` becomes `"model_inference"`, `quality_flag` becomes
`"model_prediction"` and `bias.method` becomes `"model_output_passthrough"`.

`GET /backtest` and `GET /backtest/report` gain a run-level
`ai_source_provenance` block plus two CSV columns per date
(`ai_source_label`, `ai_model_version`):

```json
"ai_source_provenance": {
  "source_label": "trained_local_correction_model",
  "model_inference_available": true,
  "labels_used": {"trained_local_correction_model": 4},
  "rows_using_trained_model": 4,
  "rows_using_fallback_source": 0,
  "mixed_inputs": false,
  "model_versions": ["ai-local-24h-20260929T062009Z"],
  "note": "Per-row ai_local input: 'trained_local_correction_model' when the trained artifact answered for that point, else the disclosed 'fallback_precomputed_ai_source'. The artifact is trained once from a controlled chronological dataset split via POST /model/train; full rolling-origin ML retraining per backtest date is future scope (not in this MVP)."
}
```

Report files written **before** Phase 4 are served as stored, with an added
`ai_source_provenance` block marking every row as
`fallback_precomputed_ai_source` — historical metrics are never silently
re-attributed to the model.

---

## Phase 5 — implemented and tested (Expert Review & Audit)

Two small backend endpoints power the dashboard's expert-review workflow. They
reuse the Phase 2 forecast engine (`_run`/`_resolve`/`_validate_lead`), so the
original system output is **computed by the backend at override time** — the
caller never supplies risk/rainfall/confidence, it only records the expert
decision and a mandatory reason.

> **Prototype local review log — not an official authorization record.** There
> is no authentication provider; the `role` field is a local demo label only.

### POST /overrides

Body — `district` (string), `date` (`YYYY-MM-DD`), `lead_hours` (`6|24|72`),
`selected_risk_level` (`Low|Moderate|High|Critical`), `reason` (string,
**mandatory**, 1–2000 chars), `reviewer_name` (optional), `role`
(`forecaster|administrator`, local demo label, default `forecaster`).

Response (`OverrideCreateResponse`): `data_mode`, `disclaimer`, `note`
(*Prototype local review log — not an official authorization record.*) and the
stored `record`:

```json
{
  "id": 1,
  "created_at": "2026-09-30T08:12:34Z",
  "actor": "A. Kumar",
  "role": "forecaster",
  "district_id": "Prayagraj",
  "district_name": "Prayagraj",
  "valid_date": "2025-09-15",
  "lead_hours": 24,
  "original_risk_level": "Moderate",
  "original_forecast_mm": 41.01,
  "overridden_risk_level": "High",
  "reason": "District control room reports ponding; escalate to High for preparedness drills.",
  "original_output": {
    "risk_level": "Moderate",
    "final_rainfall_mm": 41.01,
    "fallback_mode": "normal",
    "confidence_score": 71,
    "confidence_label": "High",
    "regime": "Active Monsoon",
    "algorithm_version": "varsha-blend-2.0.0",
    "config_version": "phase2-defaults-v1",
    "ai_source_label": "trained_local_correction_model"
  }
}
```

`original_risk_level`/`original_forecast_mm`/`original_output` always come from
the backend's own live forecast for that district/date/lead — never from the
request. Storing an `AuditLog("override.created")` row is transactional with
the override insert.

### GET /audit-logs

Query: `kind` (`override|system|all`, default `all`), `limit` (1–200,
default 50). Response: `data_mode`, `disclaimer`, `note`, `count`, and
`entries[]` — override + system events **merged newest-first** (by
`created_at`, then `id` descending). Each entry has `id`, `kind`,
`created_at` (ISO-8601 UTC), `actor`, `role`, `action` (system entries only),
and for overrides `district_id/name`, `valid_date`, `lead_hours`,
`original_risk_level`, `original_forecast_mm`, `overridden_risk_level`,
`reason` plus free-form `details`.

### Error shapes (Phase 5)

| HTTP | Code / shape | Meaning |
|------|--------------|---------|
| 404 | `{error, message, hint}` | Unknown district, out-of-range date, or reference forecast unavailable |
| 422 | pydantic list detail | Missing mandatory `reason`, invalid `lead_hours`, bad risk level, malformed date |
| 503 | `{error: "forecast_unavailable", ...}` | No usable source at that point; override refused (no system output to preserve) |
| 500 | `{error, message}` | Storage failure — never a stack trace |
