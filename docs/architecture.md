# Architecture — VARSHA Weather AI

> **Decision-Support Prototype — Synthetic Development Dataset — Not
> Operational Weather Data — Not an Official Weather Warning.**

## Pipeline at a glance

**Data → Quality → Bias → Regime → Trust → Blend → Confidence/Risk →
Explainability → Override/Audit → Verification**

That is: synthetic CSV adapters → SQLite storage/validation & source health →
per-source bias correction → regime detection → Dynamic Trust Engine →
weighted blend → confidence & risk → explainability ("Why this forecast?") →
expert override + immutable audit log (Phase 5) → backtest verification and
per-lead model reports (Phases 3–4). Every stage is an isolated, unit-tested
module; the next eight sections detail each.

## 1. Design principles

1. **Explainable decision support.** VARSHA sits *above* existing forecast
   providers. It never replaces meteorologists, agencies or official warning
   workflows, and never claims IMD/NCMRWF integration.
2. **Everything numeric is computed.** No forecast value, weight, confidence,
   alert level or verification metric is hard-coded anywhere in the frontend or
   API layer. If a value cannot be computed, the system says
   *"Insufficient data"*.
3. **Modular services (SRS NFR-MAIN-01).** Ingestion → validation →
   harmonisation → bias correction → regime detection → trust weighting →
   blending → confidence/risk → explanation → audit. Each stage is an isolated
   Python module with unit tests.
4. **Swappable data providers.** All data enters the system through a single
   adapter interface, so synthetic CSVs can be replaced by authorised replay or
   live feeds without rewriting services.
5. **Chronological honesty.** All splits, bias history and backtests are
   chronological; future records are never used to compute anything for an
   earlier valid time (SRS BR-13).

## 2. Component map (Phases 1–4 solid, later phases dashed)

```
                 +----------------------------------------------+
   districts.csv |  Adapters (app/adapters)                     |
   forecasts.csv |  HistoricalReplayAdapter (ABC)               |
   obs.csv  -----+-> SyntheticCsvAdapter                        |
                 +---------------+------------------------------+
                                 | DataFrames
                 +---------------v------------------------------+
                 |  Services (app/services)                     |
                 |  * validation   - contract + quality flags   |
                 |  * source_health - Healthy/Delayed/... (as-of)|
                 |  * rainfall     - configurable buckets       |
                 |  * dataset      - load, cache, resolve       |
                 |  * summary      - descriptive aggregation    |
                 +---------------+------------------------------+
                                 |
                 +---------------v------------------------------+
                 |  Forecast Intelligence Engine (Phase 2)      |
                 |  services/forecast_engine.run_forecast():    |
                 |   health(as-of) -> bias correction ->        |
                 |   AI-source model / disclosed fallback (P4) ->|
                 |   regime detection -> Dynamic Trust Engine ->|
                 |   blending -> confidence -> risk             |
                 |  services/: bias - regime - trust - blend -  |
                 |             confidence - risk                |
                 +---------------+------------------------------+
                                 | Pydantic models (schemas.py,
                                 |                 schemas_forecast.py)
                 +---------------v------------------------------+
                 |  Routers                                     |
                 |  meta.py:  /health /districts /data/summary  |
                 |  forecast.py: GET  /forecast                 |
                 |               GET  /forecast/explain         |
                 |               POST /forecast/simulate-source-|
                 |                       failure                |
                 +---------------+------------------------------+
                                 | Pydantic models (schemas_backtest.py)
                 +---------------v------------------------------+
                 |  Verification & Feedback Loop (Phase 3)      |
                 |  services/backtest.py: chronological         |
                 |    walk-forward - for each date D run        |
                 |    run_forecast(D) with history strictly < D |
                 |    or skip with an explicit reason; each row |
                 |    records ai_source_label + model version   |
                 |  services/metrics.py: regression + event     |
                 |    metrics -> honest baseline comparison     |
                 |  services/reporting.py: CSV/JSON reports     |
                 |    -> data/reports/ (safe deterministic      |
                 |       names, no traversal)                   |
                 +---------------+------------------------------+
                 |  Routers (cont.)                             |
                 |  backtest.py: GET  /backtest                 |
                 |               GET  /backtest/report          |
                 +---------------+------------------------------+
                                 |  on demand only, never at startup
                 +---------------v------------------------------+
                 |  Local Correction Model (Phase 4)            |
                 |  services/features.py  strictly-prior rows   |
                 |    (16 documented features, target excluded) |
                 |  services/ml_training.py chronological       |
                 |    60/20/20 split -> 2 candidates -> select  |
                 |    by VALIDATION MAE only -> refit on       |
                 |    train+val -> ONE test evaluation          |
                 |  services/model_store.py joblib + report    |
                 |    artifacts, integrity checks, mtime cache |
                 |  services/model_inference.py model-first,    |
                 |    disclosed-fallback AI source             |
                 |  routers/model.py POST /model/train         |
                 |    GET /model/report  GET /model/status      |
                 |  -> data/models/varsha_ai_local_<lead>h.*   |
                 +---------------+------------------------------+
                                 |
    - - - - - - - - - - - - - - -+ - - Phase 5+ - - - - - - -
                 +---------------v------------------------------+
                 |  Storage (app/database.py + models.py)       |
                 |  SQLite: audit_logs, override_decisions      |
                 +---------------+------------------------------+
                                 |
                 +---------------v------------------------------+
                 |  Frontend (Next.js, Phase 5)                 |
                 |  dashboard - map - explanations - override   |
                 +----------------------------------------------+
```

## 3. Request lifecycle (Phase 1 meta endpoints)

1. FastAPI receives a request and validates query parameters (Pydantic).
2. `services.dataset.get_dataset()` returns the cached, validated dataset
   (loaded once via the adapter). Missing files raise
   `DatasetUnavailableError` → **HTTP 503** with a repair hint.
3. The route builds response models (`app/schemas.py`) from computed values
   only.
4. Every payload embeds the two mandatory labels:
   `disclaimer` and `data_label`.

## 4. Forecast Intelligence Engine flow (Phase 2)

`GET /forecast`, `GET /forecast/explain` and
`POST /forecast/simulate-source-failure` all call
`services/forecast_engine.run_forecast(ds, district_id, valid_date,
lead_hours, simulate_failure_source)`.

```
inputs: district + valid_date + lead_hours (+ optional failed source)
  |
  | (1) range check       date inside [first, last] of the dataset
  |                       -> else HTTP 404 date_out_of_range
  | (2) point rows        forecast rows for (district, date, lead)
  |                       -> raw value, status, quality_flag, spread
  | (3) source health     window of last 14 days ENDING at valid_date
  |                       (as_of_date -> never reads later records)
  | (4) bias correction   per source: bias = mean(obs - fc) over records
  |                       with valid_date < selected date
  |                       corrected = max(0, raw + bias)
  |                       < min history -> keep raw, bias_available=false
  | (5) regime detection  priority: Heavy-Rain Risk > Heatwave >
  |                       Active Monsoon > Normal, using ensemble raw,
  |                       corrected inputs and PRIOR observations only
  | (6) trust engine      40% historical skill + 25% recent skill +
  |                       20% health + 15% agreement, x context factor
  |                       -> normalized weights (sum = 1)
  |                       eligible == 0 -> HTTP 503 forecast_unavailable
  | (7) blending          final = sum(weight x corrected)
  |                       3 src -> normal, 2 -> degraded, 1 -> single_source
  | (8) confidence        0-100 from available sources, weighted skill,
  |                       health, agreement, ensemble spread; capped at
  |                       39 (single_source) / 69 (degraded)
  | (9) risk              Low/Moderate/High/Critical from amount +
  |                       regime + confidence, with non-binding actions
  v
response models (schemas_forecast.py) with display rounding only:
  mm -> 2 decimals, weights -> 4 decimals (residual fixed to sum 1.0)
```

Key invariants:

* **No future data.** Bias, historical MAE, recent-14 MAE, health window and
  regime context (temperature, humidity, trailing 3-day rainfall) are all cut
  off strictly before `valid_date`. Tests perturb observations at/after the
  selected date and assert that outputs do not move.
* **Zero-weight rule.** An unavailable/ineligible source has trust score and
  weight *exactly* 0.0; remaining weights renormalize to 1.0.
* **Deterministic.** Same dataset + same parameters → identical output; the
  algorithm/config versions are echoed for audit.
* **Graceful degradation.** Missing point → 404 with the valid range; all
  sources unusable → 503 `forecast_unavailable` listing per-source reasons;
  partial loss → `degraded` fallback with a capped confidence;
  single source → `single_source` fallback, weight 1.0, labelled
  "single-source fallback".

## 5. Verification & feedback loop (Phase 3)

`GET /backtest` and `GET /backtest/report` turn the Phase 2 engine into a
measurable loop:

```
dataset (district, date, lead, source)
   |
   v
for D in [start_date .. end_date]              # strictly chronological
   |-- observation for D?        no -> skip missing_observation
   |-- forecast rows for D?      no -> skip missing_forecast
   |-- plausible observed mm?    no -> skip invalid_data
   |-- prior history >= N days?  no -> skip insufficient_history
   |-- run_forecast(D)   (Phase 2 engine, history strictly < D)
   |        raises ->             skip no_valid_source
   |-- record 5 predictions: nwp / ensemble / ai_local /
   |      equal_weight / varsha_blend + regime, weights,
   |      confidence, risk, fallback mode, source health
   v
metrics per method (only rows where that method predicted):
   regression: MAE, RMSE, mean bias, median AE, max AE (mm)
   event (>= effective threshold): TP/FP/TN/FN, precision, recall,
        F1, false-alarm rate, missed-event rate
   v
honest comparison: best method per metric = argmin/argmax of the
   returned values (never assumes VARSHA), VARSHA - baseline deltas,
   plain-language verdict better/similar/worse, or the fixed sentence
   "Insufficient evaluation sample for reliable comparison."
   v
report export: data/reports/backtest_<district>_<lead>h_<start>_<end>
   .csv (per-date rows, included AND skipped) + .json (raw-precision
   metadata) -> served by GET /backtest/report (json | csv download)
```

Loop properties:

* **Leakage-free by construction** — the engine's cutoffs (bias, skill,
  health, regime context) stop strictly before `D`; the observation of `D`
  is read only *after* that date's prediction exists, purely to score it.
  A test perturbs observations at/after `D` and asserts every prediction,
  weight, confidence, regime and risk value for `D` is unchanged.
* **Read-only** — a normal run never mutates forecast/observation frames;
  only report files are written (asserted by a test).
* **Honest by construction** — winners are computed from returned metrics;
  insufficient samples yield a warning sentence instead of a verdict; event
  metrics with few/no events return `null` + notes (never fabricated zeros);
  nothing is tuned or filtered to flatter VARSHA.
* **Feedback path** — per-method skill numbers produced here feed Phase 4
  (model training/selection report) and expert review in Phase 5;
  thresholds stay configurable (`heavy_rain_threshold_mm`,
  `minimum_history_days`, `VARSHA_MAX_BACKTEST_DATES`, `VARSHA_REPORTS_DIR`).

## 6. Local correction model (Phase 4)

`POST /model/train` (or `python -m app.train_model`) is the **only** way a model
is ever fitted. Importing the app, starting uvicorn or calling any read
endpoint never trains — `/model/status` says so in its `note`.

Training flow:

1. **Feature frame** — `services/features.build_feature_frame()` builds 16
   documented features per (district, date) from strictly prior inputs, with a
   `feature_availability` flag and a skip reason on every excluded row.
2. **Chronological split** — unique valid dates are cut 60/20/20; all
   districts of a date always land in the same split.
3. **Sample guards** — fewer than 200 train / 50 validation / 50 test rows
   returns `skipped_insufficient_data` and the deterministic fallback source
   stays active. No model is fitted on inadequate data.
4. **Two candidates** — `LinearRegression` (baseline) and
   `HistGradientBoostingRegressor`, each fitted on **train rows only** inside
   one sklearn `Pipeline` (imputer, scaler and one-hot encoder are part of the
   pipeline, so they are fitted on train only as well).
5. **Selection** — `select_candidate()` receives **validation MAE only**; its
   signature makes test-driven selection structurally impossible.
6. **Refit** — the selected candidate is refit on train + validation.
7. **One test evaluation** — metrics on the untouched future test split.
8. **Honest references** — the same rows are scored against the naive
   train+validation mean, the raw NWP value and the precomputed AI source;
   `honesty.ml_worse_than_baseline` and a warning are emitted when the model
   loses to them.
9. **Persistence** — `data/models/varsha_ai_local_<lead>h.joblib` (pipeline
   bundle) + `..._report.json` (the full training report).

Inference flow (`services/model_inference.predict_ai_local()`), called by
`GET /forecast` for every request:

- ML inference disabled by configuration → fallback, with reason
- no valid artifact for this lead horizon → fallback, with reason
- features unavailable for this point → fallback, with reason
- any inference error or NaN → fallback, with reason
- otherwise → `trained_local_correction_model`, clipped to
  `max_plausible_rain_mm`

Every answer carries `source_label`, `model_inference_available`,
`model_version`, `held_out_test_mae_mm` and a machine-readable `reason`.

Invariants:

- **Model first, disclosed fallback second — never silent.** The AI source
  always states which of the two produced its value. The fallback returns the
  untouched precomputed `ai_rain_mm` CSV value (bias-corrected exactly as in
  Phase 2); the model output is itself a correction, so bias handling passes it
  through with method `model_output_passthrough`.
- **A forecast can never crash because of the ML path** — every inference step
  is contained and any failure downgrades to the disclosed fallback.
- **Kill switch** — `VARSHA_ML_INFERENCE=false` forces the fallback path even
  when an artifact exists; the test suite uses it so Phase 1–3 expectations
  stay deterministic regardless of what is on disk.
- **Artifact integrity** — a bundle is used only when lead horizon, feature
  schema version and `model_version` all agree with the saved report; any
  mismatch is reported as unavailable with an explicit reason. An
  mtime/size-keyed cache keeps repeated inference cheap while still picking up
  retrains and deletions.
- **No per-date retraining** — the backtest replays dates through the same
  artifact and records `ai_source_label` + `ai_model_version` on every row, so
  stored Phase 3 metrics are never silently altered and pre-Phase-4 report
  files are served with an explicit `fallback_precomputed_ai_source` marker.
- **Honest reporting** — when the model is worse than the references on the
  held-out test split, the report says so in `honesty`, in the warnings and in
  the comparison sentences. No improvement claim is made anywhere.

## 7. Technology choices

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | FastAPI + Pydantic v2 | OpenAPI/Swagger for free, typed contracts (SRS NFR-MAIN-03) |
| Data | pandas + NumPy | Fast, testable tabular processing |
| ML | scikit-learn (Pipeline, ColumnTransformer) + joblib | Reproducible and inspectable; preprocessing fitted inside a single train-only pipeline |
| Storage | SQLite + SQLAlchemy | Zero-setup, persistent audit/override records (SRS NFR-REL-05) |
| Tests | pytest + httpx TestClient | Unit + API integration in one runner |
| Frontend | Next.js, TypeScript, Tailwind, Recharts, React Leaflet | Phase 5 dashboard (light, government-tech style) |

Explicitly **not** used: microservices, Kubernetes, Kafka, paid SaaS, hosted
auth, LLM calls for numbers.

## 8. Configuration & thresholds

All thresholds live in `backend/app/config.py` and can be overridden by
environment variables (`VARSHA_DATA_DIR`, `VARSHA_DB_URL`,
`VARSHA_DATA_MODE`, `VARSHA_HEALTH_WINDOW_DAYS`, `VARSHA_MIN_BIAS_HISTORY`,
`VARSHA_MIN_HISTORY_DAYS`, `VARSHA_MAX_BACKTEST_DATES`, `VARSHA_REPORTS_DIR`).
Phase 2 added configurable: rainfall category thresholds and their lead-time
scaling (`base_thresholds_24h_mm`, `scale_thresholds_by_lead`), regime
thresholds, trust weights and health scores, context (regime/lead) factors,
confidence weights and fallback caps, and per-level preparedness actions — so
demos can tune them live without touching engine code (SRS BR-12). Phase 3
added the configurable event threshold (`heavy_rain_threshold_mm` request
override on top of `base_thresholds_24h_mm["heavy"]`), the history rule
(`default_minimum_history_days`), the honest-comparison tolerances
(`min_comparison_sample`, `low_event_sample_threshold`,
`comparison_similar_tolerance_mm`) and the report directory.

## 9. Data flow guarantees

* **Traceability** — raw CSV rows are never mutated; corrections are returned
  as separate fields (`raw_forecast_mm`, `bias.bias_mm`,
  `corrected_forecast_mm`) alongside the untouched raw value
  (SRS FR-DQ-05, BR-08).
* **Quality-aware** — implausible/missing/unexpected values are counted as
  quality flags *and* quarantined from blending: such a record makes its
  source ineligible (weight 0.0), never silently averaged (SRS FR-DQ-06,
  BR-05).
* **Honest degradation** — a missing dataset yields HTTP 503, an unusable
  forecast point yields HTTP 404/503 with reasons, a degraded point yields an
  explicit `fallback_mode` + capped confidence; nothing is silently ignored
  (SRS NFR-REL-02/06).
