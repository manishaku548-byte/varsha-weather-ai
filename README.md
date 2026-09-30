# VARSHA Weather AI

**Verified Adaptive Regime-aware Skill-weighted Hybrid Analytics**

SIH problem statement: **SIH26081 — Hybrid AI–NWP Multi-Model Forecast Blending System**

> ⚠️ **Decision-Support Prototype — Synthetic Development Dataset — Not
> Operational Weather Data — Not an Official Weather Warning.**
>
> 📊 Every payload also carries the data label
> `Synthetic Development Dataset — Not Operational Weather Data`, and every
> risk output carries
> `Decision-support output only; not an official warning.`

VARSHA is an explainable decision-support prototype that dynamically blends NWP,
ensemble and AI/ML rainfall forecasts with historical observations. It does **not**
replace meteorologists, does **not** issue official warnings, and does **not**
claim any IMD/NCMRWF integration.

---

## Project status (phased delivery)

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 1** | Repository structure, synthetic dataset, data contracts, data-quality validation, source health, `/health`, `/districts`, `/data/summary`, tests | ✅ Done |
| **Phase 2** | Forecast Intelligence Engine: bias correction, regime detection, Dynamic Trust Engine, blending, confidence/uncertainty, risk, `/forecast`, `/forecast/explain`, source-failure simulation, tests, docs | ✅ Done |
| **Phase 3** | Chronological walk-forward backtesting, regression/event metrics, honest baseline comparison, CSV/JSON report export, `/backtest`, `/backtest/report`, tests, docs | ✅ Done |
| **Phase 4** | Leakage-safe AI/ML local correction model (scikit-learn), chronological 60/20/20 split, validation-MAE model selection, held-out test metrics with honest reference comparison, disclosed fallback, `POST /model/train`, `GET /model/report`, `GET /model/status`, tests, docs | ✅ Done |
| Phase 5 | Next.js dashboard, map, source-failure UI, expert override audit UI | ✅ Done |
| Phase 6 | Demo readiness, final QA, docs finalisation, local hardening | ✅ Done |

---

## Prerequisites

- **Python 3.11+** (developed and tested on Python 3.14)
- **Node.js 20+** and npm (needed from Phase 5 only)
- Windows 10/11, macOS or Linux
- No internet-dependent services are required: everything runs locally

---

## Installation

### Windows (PowerShell)

```powershell
cd "C:\path\to\varsha-weather-ai"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### macOS / Linux

```bash
cd "/path/to/varsha-weather-ai"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements.txt
```

---

## Generate the dataset (Phase 1)

The repository ships with the generated CSVs. To regenerate them deterministically:

### Windows (PowerShell)

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.data.synthetic_generator
```

### macOS / Linux

```bash
cd backend
../../.venv/bin/python -m app.data.synthetic_generator
```

The generator is seeded (`--seed 42`), so it always reproduces byte-identical files.

---

## Run the backend

### Windows (PowerShell)

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### macOS / Linux

```bash
cd backend
../../.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Check it is alive

```bash
curl http://127.0.0.1:8000/health
```

### Open Swagger documentation

Open **<http://127.0.0.1:8000/docs>** in a browser (Swagger UI),
or the raw schema at <http://127.0.0.1:8000/openapi.json>.

---

## Run the tests

257 tests (Phase 1 data layer + Phase 2 Forecast Intelligence Engine +
Phase 3 backtesting and reporting + Phase 4 feature engineering, model
training, inference, endpoints and fallback behaviour + Phase 5 expert-review
and audit endpoints).

The Phase 4 tests train real models into a temporary directory, so the suite
takes a few minutes rather than seconds.

### Windows (PowerShell)

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
```

### macOS / Linux

```bash
cd backend
../../.venv/bin/python -m pytest
```

---

## Run the dashboard (Phase 5)

### Windows (PowerShell) — two terminals

Terminal 1 — backend on `127.0.0.1:8001` (the dashboard is configured for
this port):

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Terminal 2 — dashboard dev server:

```powershell
cd frontend
npm install          # first time only
npm run dev
```

Open **<http://localhost:3000>**. The dashboard is a single page with: header
+ data-mode banner, forecast controls (district / date / 6-24-72 h / scenario /
Run), forecast hero, source comparison, dynamic weights, backend-only
explanation, Leaflet district map, historical validation (metrics + CSV), a
source-failure simulator, the expert-override dialog with its audit timeline,
and a system-details panel. It never computes forecast/weight/confidence/risk/
metric values itself — every number is fetched from the backend.

If you change `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`, restart
`npm run dev`. See `frontend/README.md` for details.

#### Frontend checks (lint / type-check / build)

```powershell
cd frontend
npm run lint        # ESLint, flat config
npx tsc --noEmit    # TypeScript strict type-check
npm run build       # production build (prerenders the single page)
```

#### Demo scenario & demo readiness (Phase 6)

A stable, verified demo point ships with the dashboard: **Prayagraj ·
2025-09-03 · 24 h lead** — backend risk **Critical**, regime **Heavy-Rain
Risk**, all three sources healthy with the trained ML model active. The slim
*Suggested 3-minute demo flow* strip on the page (Forecast → Why this forecast
→ Backtest → Source failure → Expert override) includes a **Load Demo
Scenario** button that only sets existing inputs and triggers the normal
`GET /forecast` / `GET /forecast/explain` calls — it injects nothing.

- Full walkthrough with measured values & fallback expectations:
  `docs/demo_scenario.md`
- Narrated 3-minute script: `docs/demo_script.md`
- Pre-demo smoke test + demo-day checklist: `docs/SIH_DEMO_CHECKLIST.md`

All screen values must be read from the live API at runtime; the numbers above
are guidance reproduced from the deterministic engine on the shipped dataset.

### macOS / Linux

```bash
cd backend
../../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

```bash
cd frontend && npm install && npm run dev
```

The dashboard can be exercised headlessly too — the backend API below is fully
CORS-enabled for `http://localhost:3000` and `http://127.0.0.1:3000`.

---

## Deployment (GitHub · Vercel · Render/Railway)

The repository is **deployment-ready, but nothing deploys automatically** and
no secret lives in the repo (`.env` files, SQLite databases, `.joblib`
artifacts, generated reports and tokens are all git-ignored — only
`.env.example` files are tracked). The full beginner runbook is
**`docs/DEPLOYMENT.md`**; a pre-push checklist is at the end of
`docs/SIH_DEMO_CHECKLIST.md`.

```
GitHub (source repository)
   │   └─ pushes update Vercel and Render/Railway
   ▼
Vercel (Next.js dashboard)        Render or Railway (FastAPI backend)
   │   NEXT_PUBLIC_API_BASE_URL        │   ── /health liveness probe
   └─────────────► https://…backend… ◄─┘   CORS: VARSHA_CORS_ORIGINS
```

| Piece | Host | Root directory | Key environment variable |
|-------|------|----------------|--------------------------|
| Source code | GitHub | repo root | — (no secrets in git) |
| Dashboard (Next.js) | Vercel | `frontend` | `NEXT_PUBLIC_API_BASE_URL` = backend public URL |
| API (FastAPI) | Render or Railway | `backend` | `PORT` (injected), `VARSHA_CORS_ORIGINS` = Vercel origin |

Backend cloud notes (all detailed in `docs/DEPLOYMENT.md`):

- The port is read from **`PORT`** (fallback **8001**) and the app runs with
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (see `backend/Procfile`,
  `backend/render.yaml`, `backend/railway.json`).
- CORS is read from **`VARSHA_CORS_ORIGINS`** (comma-separated origins).
- **`GET /health`** returns `200` (status `ok` or `degraded`) even when the
  dataset is missing — it is the health check used by Render/Railway.
- **Ephemeral storage.** Free-host filesystems are not persistent: SQLite
  audit rows, backtest reports and retrained `.joblib` artifacts are lost on
  redeploy unless a persistent disk is mounted at `VARSHA_DB_URL` /
  `VARSHA_REPORTS_DIR` / `VARSHA_MODELS_DIR`. The deployed model therefore
  starts in **disclosed fallback mode** (`fallback_precomputed_ai_source`)
  until you run `POST /model/train` on the instance — nothing claims persisted
  artifacts.
- All mandatory labels keep travelling: the production build bakes in
  “Decision-Support Prototype — Synthetic Development Dataset — Not Operational
  Weather Data — Not an Official Weather Warning” exactly as locally.

---

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Service health, dataset availability, disclaimers |
| GET | `/districts` | The five configured Uttar Pradesh districts |
| GET | `/data/summary` | Dataset summary, validation report, source health |
| GET | `/forecast` | Full blended forecast: bias, regime, trust weights, confidence, risk |
| GET | `/forecast/explain` | Plain-language explanation of the same numbers |
| POST | `/forecast/simulate-source-failure` | Normal vs degraded comparison when a source fails |
| GET | `/backtest` | Chronological walk-forward evaluation: regression + event metrics, honest baseline comparison |
| GET | `/backtest/report` | Report summary (`format=json`) or CSV file download (`format=csv`) |
| POST | `/model/train` | Train the local correction model for one horizon (never runs at startup) |
| GET | `/model/report` | Saved training report: splits, candidates, selection, held-out test metrics, honesty block |
| GET | `/model/status` | Artifact existence, trained horizons, inference readiness, fallback state |
| POST | `/overrides` | Record an expert override with a **mandatory reason**; the backend preserves the original system output (Phase 5) |
| GET | `/audit-logs` | Local review/audit timeline — override + system events, newest first (Phase 5, `kind`/`limit` filters) |

Full interactive documentation: `/docs` · Full schemas and error tables:
`docs/api_contract.md` (Phases 1–5) · Dashboard usage: `frontend/README.md`.

### Sample calls (PowerShell)

```powershell
# Full forecast package
curl.exe -s "http://127.0.0.1:8000/forecast?district=Prayagraj&date=2025-09-15&lead_hours=24"

# Plain-language explanation
curl.exe -s "http://127.0.0.1:8000/forecast/explain?district=Lucknow&date=2025-07-31&lead_hours=6"

# Short-history date (shows the honest "Insufficient prior history" path)
curl.exe -s "http://127.0.0.1:8000/forecast?district=Prayagraj&date=2025-06-03&lead_hours=24"

# Demo one source failing (nwp | ensemble | ai)
curl.exe -s "http://127.0.0.1:8000/forecast?district=Prayagraj&date=2025-09-15&lead_hours=24&simulate_failure_source=ai"

# Side-by-side normal vs degraded run
curl.exe -s -X POST http://127.0.0.1:8000/forecast/simulate-source-failure `
  -H "Content-Type: application/json" `
  -d '{"district":"Prayagraj","date":"2025-09-15","lead_hours":24,"failed_source":"ensemble"}'
```

`GET /forecast` parameters: `district` (required), `date` (required,
`YYYY-MM-DD` inside the dataset range), `lead_hours` (required: 6, 24 or 72),
`simulate_failure_source` (optional).

### Backtest sample calls (PowerShell)

```powershell
# Walk-forward evaluation for one district/horizon/range (writes CSV + JSON reports)
curl.exe -s "http://127.0.0.1:8000/backtest?district=Prayagraj&lead_hours=24&start_date=2025-07-01&end_date=2025-07-20"

# Same, with per-date rows inside the response
curl.exe -s "http://127.0.0.1:8000/backtest?district=Prayagraj&lead_hours=24&start_date=2025-07-01&end_date=2025-07-05&include_daily_rows=true"

# Report summary (JSON) — stored file if present, generated otherwise
curl.exe -s "http://127.0.0.1:8000/backtest/report?district=Prayagraj&lead_hours=24&start_date=2025-07-01&end_date=2025-07-20&format=json"

# Report as a CSV file download
curl.exe -s -o backtest_report.csv "http://127.0.0.1:8000/backtest/report?district=Prayagraj&lead_hours=24&start_date=2025-07-01&end_date=2025-07-20&format=csv"

# Custom event threshold (24h-equivalent; scaled by lead_hours/24)
curl.exe -s "http://127.0.0.1:8000/backtest?district=Lucknow&lead_hours=6&start_date=2025-07-01&end_date=2025-07-10&heavy_rain_threshold_mm=100"
```

`GET /backtest` parameters: `district`, `lead_hours` (6/24/72), `start_date`
and `end_date` (required, inclusive range); `minimum_history_days` (default
14), `heavy_rain_threshold_mm` (default 64.5), `include_daily_rows` (default
false) are optional. `GET /backtest/report` takes the same range parameters
plus `format=json|csv`.

### Train the local correction model (Phase 4)

Training **never happens at startup or on the first request** — you trigger it
explicitly, either through the API or the CLI.

### Windows (PowerShell)

```powershell
cd backend

# Train one horizon via the CLI (24 h here; 6 and 72 also supported)
..\.venv\Scripts\python.exe -m app.train_model --lead-hours 24

# Retrain even though a valid artifact already exists
..\.venv\Scripts\python.exe -m app.train_model --lead-hours 24 --force

# Raise the minimum-sample requirement to see the honest skip path
..\.venv\Scripts\python.exe -m app.train_model --lead-hours 72 --minimum-samples 5000
```

### macOS / Linux

```bash
cd backend

# Train one horizon via the CLI (24 h here; 6 and 72 also supported)
../../.venv/bin/python -m app.train_model --lead-hours 24

# Retrain even though a valid artifact already exists
../../.venv/bin/python -m app.train_model --lead-hours 24 --force
```

Artifacts are written to `data/models/`:

* `varsha_ai_local_<lead>h.joblib` — the fitted scikit-learn pipeline
  (imputer → scaler → one-hot → regressor). Git-ignored.
* `varsha_ai_local_<lead>h_report.json` — the full-precision training report
  (feature schema, split boundaries and counts, per-candidate validation
  metrics, selection rationale, held-out test metrics, reference comparison,
  honesty block, provenance, limitations). Kept in git.

Exit codes: `0` for `completed` or `already_trained`, `1` for a skip
(`skipped_insufficient_data`).

### Model sample calls (PowerShell)

```powershell
# Train through the API (Swagger UI: http://127.0.0.1:8000/docs -> POST /model/train)
curl.exe -s -X POST http://127.0.0.1:8000/model/train `
  -H "Content-Type: application/json" `
  -d '{"lead_hours": 24}'

# What is loaded right now? (works before anything has been trained)
curl.exe -s http://127.0.0.1:8000/model/status

# Full honest training report for the saved artifact
curl.exe -s "http://127.0.0.1:8000/model/report?lead_hours=24"

# Forecast now shows the model provenance in the ml_model block
curl.exe -s "http://127.0.0.1:8000/forecast?district=Prayagraj&date=2025-09-15&lead_hours=24"

# Serve the precomputed source instead, without deleting the artifact
$env:VARSHA_ML_INFERENCE = "false"
```

`POST /model/train` body: `lead_hours` (required: 6, 24 or 72),
`minimum_samples` (optional, overrides the configured minimum) and
`force_retrain` (optional, default `false`). `GET /model/report` takes
`lead_hours` (optional — defaults to the most recently trained horizon);
`GET /model/status` takes nothing.

---

## Forecast calculations (Phase 2)

Everything below is computed per request from the stored dataset — no value
is hardcoded, no LLM is involved anywhere in the pipeline.

### 1. Bias correction (per source × district × lead)

```
bias            = mean(observed_rain_mm - source_forecast_mm)   # records with valid_date < selected date
corrected       = max(0, raw_forecast + bias)                   # floor: rainfall cannot be negative
```

* Only records strictly **earlier** than the selected date are used (never
  the selected date, never the future); only `status == "ok"`, plausible
  records enter the history.
* If fewer than `min_bias_history_records` (default 10, env
  `VARSHA_MIN_BIAS_HISTORY`) prior records exist: `bias_available = false`,
  `reason = "Insufficient prior history"`, raw value kept unchanged.
* The response reports for **every** source: raw forecast, bias amount,
  corrected forecast, prior record count and availability.

### 2. Regime detection (transparent rules, configurable thresholds)

Priority order — the first rule that fires wins:

1. **Heavy-Rain Risk** — ensemble mean *or* any bias-corrected blend input
   crosses the heavy-rain threshold (64.5 mm at 24h, scaled by lead).
2. **Heatwave** — latest temperature available *before* the selected date
   reaches `heatwave_temp_c` (40 °C default).
3. **Active Monsoon** — any wet signal: ensemble ≥ moderate threshold, or
   trailing 3-day observed rainfall ≥ 40 mm, or humidity ≥ 80 %.
4. **Normal** — otherwise.

Returns label, 0–1 confidence, the triggered rules, the thresholds used and a
human-readable reason. It is a prototype rule set — **no meteorological
operational certification is claimed**.

### 3. Dynamic Trust Engine (per source)

```
trust   = (0.40 x historical_skill + 0.25 x recent_skill
         + 0.20 x health + 0.15 x agreement) x context_factor
weight  = trust / sum(trust of eligible sources)
```

* `historical_skill` = inverse MAE over **all** prior usable records;
  `recent_skill` = inverse MAE over the most recent 14 prior records
  (both mapped to 0–1 via `1 / (1 + MAE / 25 mm)`).
* `health` from the configurable map: Healthy 1.0 · Delayed 0.6 ·
  Anomalous 0.3 · Unavailable 0.0 — evaluated over the 14-day window
  **ending at the selected date**.
* `agreement` = proximity to the peer median of the corrected forecasts.
* `context_factor` = configurable regime × lead-time adjustment
  (`context_regime_factors`, `context_lead_factors`).
* Weights are stored per component in the response, each with a
  plain-language reason.

### 4. Blending and fallback

```
final_rainfall_mm = sum(weight_i x corrected_forecast_i)
```

| Eligible sources | `fallback_mode` | Behaviour |
|------------------|-----------------|-----------|
| 3 | `normal` | All weights normalized to 1 |
| 2 | `degraded` | Failed source weight **exactly 0**, rest renormalized, confidence capped at 69 |
| 1 | `single_source` | Weight **exactly 1.0**, output says *“single-source fallback”*, confidence capped at 39 |
| 0 | — | HTTP **503** `forecast_unavailable` with per-source reasons |

### 5. Confidence and uncertainty (0–100)

Weighted factors: available sources 25 % · weighted historical skill 25 % ·
source health 15 % · agreement 20 % · ensemble spread 15 % (spread factor
dropped and the rest renormalized if the ensemble is unavailable).
Bands: **Low 0–39 · Medium 40–69 · High 70–100**. The response also returns
an uncertainty range (mm) — a prototype heuristic, explicitly marked
*not a calibrated prediction interval*.

### 6. Rainfall risk (configurable levels)

Amount → base level using thresholds scaled by `lead_hours / 24`
(defaults 15.6 / 64.5 / 115.6 / 204.5 mm at 24h):
`< moderate → Low`, `≥ moderate → Moderate`, `≥ heavy → High`,
`≥ very heavy → Critical` (≥ extreme adds an explicit reason). A
**Heavy-Rain Risk** regime escalates Low/Moderate by one level; low
confidence adds a caveat instead of silently lowering a level. Every risk
output contains event type, level, predicted rainfall, validity period,
confidence, reasons, non-binding preparedness actions and
`Decision-support output only; not an official warning.`

---

## Historical backtest (Phase 3)

`GET /backtest` replays the Phase 2 engine day by day over an inclusive date
range (**strictly chronological**): for each date `D` the engine may use only
records **earlier than `D`** for bias, skill, regime context and dynamic
weights — the observation of `D` itself enters only as verification truth.
A normal run never mutates the stored forecast data.

**Five methods are evaluated** for every included date:

| Method | Definition |
|--------|-----------|
| `nwp` | NWP source, bias-corrected from prior records |
| `ensemble` | Ensemble mean source |
| `ai_local` | AI local-correction source |
| `equal_weight` | Equal-weight average of the valid available corrected sources |
| `varsha_dynamic_blend` | VARSHA's dynamic Trust-Engine blend (Phase 2) |

Dates are **skipped with an explicit reason** instead of being silently
dropped: `missing_observation`, `missing_forecast`, `invalid_data`,
`insufficient_history` (fewer than `minimum_history_days`, default 14) or
`no_valid_source`. The response reports evaluated/skipped counts, a
skip-reason breakdown and, when the evaluated sample is smaller than
`min_comparison_sample` (20), the exact warning
*"Insufficient evaluation sample for reliable comparison."*

### Regression metrics — how to read them

| Metric | Meaning |
|--------|---------|
| **MAE** (mm) | Average absolute error — the primary "typical error" number; lower is better |
| **RMSE** (mm) | Square-root of mean squared error — punishes big misses; much larger than MAE means occasional large errors |
| **Mean bias error** (mm) | `mean(prediction − actual)` — positive = over-prediction, negative = under-prediction; best near 0 regardless of sign |
| **Median absolute error** (mm) | Typical error without outlier influence |
| **Maximum absolute error** (mm) | Worst single miss in the period |

### Heavy-rain event metrics — how to read them

An event is `rainfall ≥ 64.5 mm` at 24h by default (configurable via
`heavy_rain_threshold_mm`; scaled by `lead_hours/24`, so 16.125 mm at 6h and
193.5 mm at 72h). The **same** effective threshold defines observed and
predicted events.

| Metric | Meaning |
|--------|---------|
| **Precision** | Of the days VARSHA flagged, how many really happened (false alarms hurt it) |
| **Recall** | Of the real heavy-rain days, how many VARSHA caught (misses hurt it) |
| **F1** | Harmonic mean of precision and recall — single balance score |
| **False-alarm rate** | `FP/(FP+TN)` — share of non-event days wrongly flagged |
| **Missed-event rate** | `FN/(TP+FN)` — share of real events missed (= 1 − recall) |

Event counts below 5 trigger an explicit *"statistically weak"* warning, and
zero-division cases (e.g. nothing ever predicted) return `null` with an
explanatory note instead of a misleading 0.

### Honest comparison

`comparison_summary` reports `best_method_by_metric` computed **from the
returned metrics only** (never assuming VARSHA wins), plus the deltas
`varsha_vs_equal_weight_mae_delta_mm`, `varsha_vs_best_single_source_mae_delta_mm`,
`varsha_vs_equal_weight_recall_delta` and
`varsha_vs_best_single_source_recall_delta` (delta = VARSHA − baseline;
negative MAE delta favours VARSHA). The plain-language outcome uses only
computed MAE (±0.5 mm similarity tolerance), e.g. *"VARSHA performed worse
than the best single source (Ensemble forecast) for this selected synthetic
evaluation period (MAE …)"*. If VARSHA loses to a baseline, the response says
so.

### Report files

Every `/backtest` request writes two deterministic files into `data/reports/`:

* `backtest_<district>_<lead>h_<start>_<end>.csv` — one row per requested
  date (included **and** skipped) with all five predictions, weights,
  confidence, risk, source health, skip reason, data mode and disclaimer.
* `backtest_<district>_<lead>h_<start>_<end>.json` — request echo, data mode,
  disclaimer, generation timestamp, algorithm/config versions, evaluated/
  skipped counts, full-precision metrics table, baseline comparisons and
  limitations.

`GET /backtest/report?format=json` returns the stored summary (or generates
it); `format=csv` streams the CSV as a file download. Report files keep full
precision — API responses round to 4 decimals for display only.

## Local correction model (Phase 4)

The `ai_local_v1` source is no longer a hardcoded synthetic column. Phase 4
trains a **local correction model** on the stored dataset with scikit-learn and
serves its prediction as the AI source. The precomputed `ai_rain_mm` column
remains as an **explicitly labelled fallback** — the switch is never silent.

### The 16 features (all leakage-safe)

Every feature for forecast valid date `D` uses only information available
**strictly before** `D`. Raw source values are used as-is; the model's target is
the observed rainfall for `D`, which the model never sees as input.

| Group | Features |
|-------|----------|
| Raw source signals | `nwp_rain_mm`, `ensemble_mean_mm`, `ensemble_spread_mm` |
| Prior observation context | `prior_temp_c`, `prior_wind_kmph`, `prior_rain_1d_mm`, `prior_rain_3d_total_mm`, `prior_rain_3d_mean_mm`, `prior_rain_7d_total_mm`, `prior_rain_7d_mean_mm` |
| Availability ratios | `nwp_prior_ok_ratio`, `ensemble_prior_ok_ratio` |
| Calendar | `month`, `lead_hours` |
| Categorical | `district`, `season` |

Rolling windows end at `D − 1`; prior temperature/wind come from the latest
observation strictly before `D`; the availability ratios use forecast statuses
over `[D − 14, D − 1)`. Full per-feature documentation lives in
`docs/data_dictionary.md`.

**Deliberately excluded:** the observed rainfall for `D` (the target), any
bias-corrected or blended value (leaks the Phase 2 signal path), any
observation dated `D` or later, the Phase 2/3 regime label, confidence, risk,
dynamic weights and backtest metrics (all derived from target-adjacent data).

Each row carries `feature_availability` — `ok`, `missing_forecast` or
`insufficient_history` — plus a plain-language `feature_skip_reason`. It is
computed from feature-side inputs **only**, never from the observed value, so a
row's features are identical whether or not the observation exists.

### Chronological split, honest selection, single held-out test

The split is chronological by **unique global date** (not by row), so all
districts of a date always land in the same split and no date can leak across
boundaries. Default ratio 60 / 20 / 20 (configurable, with a 70 / 15 / 15
fallback when the sample is too thin).

For the default dataset and the 24 h horizon:

| Split | Dates | Rows |
|-------|-------|------|
| Train | 2025-06-01 → 2025-08-11 (72 dates) | 302 |
| Validation | 2025-08-12 → 2025-09-04 (24 dates) | 113 |
| Test (held out) | 2025-09-05 → 2025-09-28 (24 dates) | 110 |

Of 600 possible rows per horizon, 525 are usable (44 `missing_forecast`, 31
`insufficient_history` — the 7-day minimum history rule).

Two candidates are trained: a `LinearRegression` baseline and
`HistGradientBoostingRegressor` (nonlinear). Both live inside a
`Pipeline` + `ColumnTransformer`, so the imputer, the scaler and the one-hot
encoder are **fitted on the training rows only** — never on validation or test.
The final model is selected by **validation MAE alone** (deterministic
tie-break: linear first), then refit on train + validation and saved. The
held-out test split is evaluated **exactly once**, after the choice is frozen.

### The honest result (default dataset, all three horizons, 1 real run)

| Horizon | Test rows | Selected model MAE (mm) | `raw_nwp` | `precomputed_ai_source` | `naive_train_mean` | Verdict from the report |
|---------|-----------|--------------------------|-----------|---------------------------|---------------------|------------------------|
| 6 h | 116 | **1.1705** | 3.0069 | 1.3119 | 9.7552 | better than all references |
| 24 h | 110 | 2.3692 | 2.3191 | 1.3878 | 35.9520 | **worse** than `raw_nwp` and `precomputed_ai_source` |
| 72 h | 114 | **3.2916** | 7.4518 | 3.7600 | 98.2335 | better than all references |

The verdict is **per horizon and per run** — it is whatever
`honesty.ml_worse_than_baseline` in the report says, not a fixed claim. In this
run the 24 h model loses to both references and says so
(`ml_worse_than_baseline = true`, `worse_than_references` naming both, plus an
attached warning); the 6 h and 72 h models beat them
(`ml_worse_than_baseline = false`). **No blanket accuracy or improvement claim
is made anywhere in this project**, and neither result should be generalised.
These are development/testing numbers on synthetic data — `GET /model/report`
always reports what actually happened on the data you trained on.

### Trained model vs fallback — never silent

| `source_label` | When | `GET /forecast` shows |
|----------------|------|-----------------------|
| `trained_local_correction_model` | a validated artifact exists for that horizon and the features are available | AI source `status: "model_inference"`, `quality_flag: "model_prediction"`, `bias.method: "model_output_passthrough"`, plus the model version and its held-out test MAE |
| `fallback_precomputed_ai_source` | nothing trained, inference disabled, artifact invalid, or features unavailable for that row | the precomputed `ai_rain_mm` value, with the exact reason |

Both `GET /forecast` and `GET /forecast/explain` return an additive `ml_model`
block with `source_label`, `model_inference_available`, `model_version`,
`model_report_reference`, `ai_local_model_prediction_mm`,
`feature_availability`, `held_out_test_mae_mm` and a `reason` string. All
Phase 1–3 fields keep their exact shape.

`GET /backtest` and `GET /backtest/report` add a run-level
`ai_source_provenance` block and two per-date CSV columns
(`ai_source_label`, `ai_model_version`). Historical report files written before
Phase 4 are served as stored, marked
`fallback_precomputed_ai_source` — a stored metric is never silently
re-attributed to the model. Retraining is **not** repeated per backtest date.

### When the system refuses to train

If the data is too small or too thin in dates, training is **skipped**, no
artifact is written, `warnings` explains the shortfall, and forecasts keep using
the labelled fallback. A misleading model is worse than no model.

---

## Disclaimers

* All responses: `Decision-Support Prototype — Synthetic Development Dataset
  — Not Operational Weather Data — Not an Official Weather Warning.`
* Data label: `Synthetic Development Dataset — Not Operational Weather Data`
* Risk outputs: `Decision-support output only; not an official warning.`
* Backtest responses and report files: `Synthetic Development Dataset —
  Development/Testing Only — Not Operational Weather Data — Not an Official
  Weather Warning.`
* Phase 4 model responses and training reports: `Synthetic Development Dataset
  — Development/Testing Only — Not Operational Weather Data — Not an Official
  Weather Warning.`
* See `docs/limitations.md` before quoting any number from this system.

---

## Project structure

```
varsha-weather-ai/
├── README.md
├── LICENSE                    MIT license
├── CONTRIBUTING.md            contribution rules + quality gates
├── .gitignore                 never tracks .env/.db/.joblib/secrets
├── docs/
│   ├── data_dictionary.md
│   ├── architecture.md            incl. verification & feedback loop
│   ├── api_contract.md            Phases 1-5 endpoint schemas (incl. /model/*, overrides/audit)
│   ├── demo_script.md             backend + dashboard demo narration
│   ├── demo_scenario.md           stable demo point + source-failure expectations (Phase 6)
│   ├── SIH_DEMO_CHECKLIST.md      pre-demo smoke test + demo-day checklist (Phase 6),
│   │                              + pre-push / deployment checklist (Phase 7)
│   ├── DEPLOYMENT.md              GitHub · Vercel · Render/Railway runbook (Phase 7)
│   └── limitations.md             synthetic data, authority & validation limits
├── data/
│   ├── districts.csv
│   ├── historical_forecasts_synthetic.csv
│   ├── observations_synthetic.csv
│   ├── reports/                   backtest CSV + JSON reports (generated)
│   └── models/                    Phase 4 .joblib artifacts + training reports
├── backend/
│   ├── requirements.txt
│   ├── .env.example             non-secret example env vars (tracked)
│   ├── Procfile                 web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
│   ├── render.yaml              Render blueprint (no secrets)
│   ├── railway.json             Railway build/start + /health check
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py                FastAPI app + error handlers
│   │   ├── train_model.py         Phase 4 CLI trainer (no server needed)
│   │   ├── config.py              all thresholds, weights & labels (configurable)
│   │   ├── database.py            SQLAlchemy + SQLite
│   │   ├── schemas.py             Pydantic v2 contracts (Phase 1)
│   │   ├── schemas_forecast.py    Pydantic v2 contracts (Phase 2)
│   │   ├── schemas_backtest.py    Pydantic v2 contracts (Phase 3)
│   │   ├── schemas_model.py       Pydantic v2 contracts (Phase 4)
│   │   ├── schemas_audit.py      Pydantic v2 contracts (Phase 5: overrides/audit)
│   │   ├── models.py              audit + override tables
│   │   ├── routers/
│   │   │   ├── meta.py            /health /districts /data/summary
│   │   │   ├── forecast.py        /forecast /forecast/explain /forecast/simulate-source-failure
│   │   │   ├── backtest.py        /backtest /backtest/report
│   │   │   ├── model.py          /model/train /model/report /model/status
│   │   │   └── audit.py          /overrides /audit-logs (Phase 5)
│   │   ├── services/
│   │   │   ├── validation.py      contract + quality flags
│   │   │   ├── source_health.py   Healthy/Delayed/Anomalous/Unavailable (as-of aware)
│   │   │   ├── rainfall.py        configurable buckets
│   │   │   ├── dataset.py         load, cache, resolve
│   │   │   ├── summary.py         descriptive aggregation
│   │   │   ├── bias.py            mean-bias correction (prior records only)
│   │   │   ├── regime.py          rule-based regime classifier
│   │   │   ├── trust.py           Dynamic Trust Engine
│   │   │   ├── blend.py           weighted blending + fallback modes
│   │   │   ├── confidence.py      confidence score + uncertainty range
│   │   │   ├── risk.py            rainfall risk guidance
│   │   │   ├── forecast_engine.py Phase 2 orchestration (run_forecast)
│   │   │   ├── metrics.py         regression + event metrics, honest comparison
│   │   │   ├── backtest.py        chronological walk-forward engine
│   │   │   ├── reporting.py       CSV/JSON report export (safe deterministic paths)
│   │   ├── features.py         leakage-safe feature rows (features-v1)
│   │   ├── ml_training.py      chronological split, candidates, selection, artifacts
│   │   ├── model_store.py      joblib/JSON persistence + integrity checks
│   │   └── model_inference.py  AI-source inference with disclosed fallback
│   │   ├── adapters/              provider interface + synthetic CSV adapter
│   │   └── data/                  synthetic dataset generator
│   └── tests/                     pytest suite (257 tests)
└── frontend/                      Phase 5/6 dashboard (Next.js + TypeScript)
    ├── app/
    │   ├── layout.tsx             root layout (system font stack)
    │   ├── page.tsx               dashboard orchestrator (single page)
    │   └── globals.css            Tailwind + light-theme tokens + print CSS
    ├── components/                header, controls, demo strip, hero, source
    │                              comparison, weights, explanation, Leaflet map,
    │                              validation, model status, source-failure,
    │                              override, audit timeline, system details …
    ├── components/                header, controls, hero, source comparison,
    │                              weights, explanation, Leaflet map, validation,
    │                              model status, source-failure, override, audit
    │                              timeline, system details …
    ├── lib/                       typed API client, formatters, constants, useAsync
    ├── types/api.ts               full backend schema mappings
    └── README.md                  dashboard setup/usage
```

---

## Screenshots

> Placeholders — add real captures before publishing the README on GitHub.
> Recommended: 1366×768 or 1920×1080, saved under `docs/screenshots/` and
> referenced as `docs/screenshots/<name>.png`.

| File | What it shows |
|------|---------------|
| `docs/screenshots/dashboard-overview.png` | Full dashboard: header + mandatory banner, controls, forecast hero for the demo scenario (Prayagraj · 2025-09-03 · 24 h) |
| `docs/screenshots/hero-explanation.png` | Hero with source comparison, dynamic weights and *Why this forecast?* |
| `docs/screenshots/backtest-metrics.png` | Backtest metrics table + honest baseline comparison for one range |
| `docs/screenshots/source-failure.png` | Source-failure simulator: Degraded mode, weight 0.0000, confidence drop |
| `docs/screenshots/expert-override.png` | Expert override modal + audit timeline with preserved original output |
| `docs/screenshots/model-status.png` | Per-horizon trained-model status table (6/24/72 h) |
| `docs/screenshots/offline-banner.png` | *(optional)* Backend-unavailable banner with URL + Retry |

The `docs/SIH_DEMO_CHECKLIST.md` § B3 lists the same captures with exact
demo-day steps.

---

## Data limitations (read this before demoing)

Full statement: **`docs/limitations.md`**. Headlines:

1. **All data is synthetic.** It is generated locally by a seeded script and is
   *not* IMD, NCMRWF, Open-Meteo or any real observation. It is labelled on
   every API response and will be labelled on every screen.
2. **No live feeds.** The MVP runs in historical-replay mode. A provider
   adapter interface exists so an authorised feed can replace the synthetic
   CSVs later without rewriting the system.
3. **No official-warning authority.** VARSHA is decision-support only; risk
   outputs are non-binding and say so verbatim.
4. **Validation is development-only.** Phase 3 adds strict chronological
   backtesting (walk-forward, no future leakage) with MAE/RMSE/recall/F1 and
   an honest baseline comparison — but all of it runs on the same synthetic
   development dataset, so the metrics are *development/testing numbers*, not
   operational skill scores, and event verification against so few synthetic
   heavy-rain days is statistically weak. This is **not** official-warning
   verification. Confidence and the uncertainty range remain heuristics,
   explicitly marked as not calibrated.
5. **The ML model is not better than the references.** On the default
   synthetic dataset the 24 h model reaches 2.37 mm MAE on the held-out future
   test split, against 2.32 mm for the raw NWP value and 1.39 mm for the
   precomputed `ai_rain_mm` source on the same rows. The training report states
   this openly (`honesty.ml_worse_than_baseline`). The dataset is 120 days and
   ~600 rows per horizon, which is far too small for a generalisable weather
   model — it demonstrates a leakage-safe, honest training and serving
   *pipeline*, not operational skill. When the sample is too small, training
   is skipped rather than producing a misleading model.
6. **No per-date retraining.** The artifact is trained once from a controlled
   chronological split; backtests do not re-fit per date, so backtest numbers
   are not a rolling-origin operational evaluation. Historical report files
   keep their original metrics and are marked as pre-model.
7. **Five districts only**, one variable (rainfall, mm), three lead times
   (6h/24h/72h) in the MVP.
8. **Prototype thresholds** follow India (IMD-style) 24-hour rainfall
   categories as *configurable defaults*, scaled by lead time — not as
   official definitions.

---

## Configuration

Environment variables (all optional):

| Variable | Default | Meaning |
|----------|---------|---------|
| `VARSHA_DATA_DIR` | `<project>/data` | Dataset directory |
| `VARSHA_DB_URL` | `sqlite:///backend/varsha_weather_ai.db` | SQLAlchemy URL |
| `VARSHA_DATA_MODE` | `synthetic` | Data-mode label returned by the API |
| `VARSHA_HEALTH_WINDOW_DAYS` | `14` | Source-health evaluation window |
| `VARSHA_MIN_BIAS_HISTORY` | `10` | Minimum prior records before bias correction activates |
| `VARSHA_MIN_HISTORY_DAYS` | `14` | Default `minimum_history_days` for `/backtest` |
| `VARSHA_MAX_BACKTEST_DATES` | `366` | Maximum dates per backtest request |
| `VARSHA_REPORTS_DIR` | `<project>/data/reports` | Backtest CSV/JSON report directory |
| `VARSHA_MODELS_DIR` | `<project>/data/models` | Phase 4 `.joblib` artifact + training-report directory |
| `VARSHA_ML_INFERENCE` | `true` | Set to `false` to serve the precomputed AI source even when an artifact exists (the response then says so) |
| `VARSHA_ML_MIN_TRAIN_ROWS` | `200` | Minimum training rows; below this training is skipped |
| `VARSHA_ML_MIN_VAL_ROWS` | `50` | Minimum validation rows |
| `VARSHA_ML_MIN_TEST_ROWS` | `50` | Minimum held-out test rows |
| `VARSHA_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowed origins for the Phase 5 dashboard (GET/POST/OPTIONS only) |
| `PORT` | `8001` | HTTP port the web server binds (uvicorn). Render/Railway inject `PORT` in production; locally it falls back to 8001 |

Rainfall category thresholds, regime thresholds, trust weights, context
factors, confidence weights/caps, preparedness actions and source-health
ratios live in `backend/app/config.py` (`Settings`), so demos can tune them
without touching engine code.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `503 ... districts.csv not found` | Generate the dataset (see *Generate the dataset*). |
| `ModuleNotFoundError: No module named 'app'` | Run commands from inside `backend/`, or use `python -m uvicorn app.main:app` from there. |
| `pip is not recognized` | Use `python -m pip` (and the venv interpreter). |
| PowerShell blocks `.venv\Scripts\Activate.ps1` | Skip activation and call `.\.venv\Scripts\python.exe` directly (all commands above already do this). |
| Port 8000 already in use | Add `--port 8001` and open `http://127.0.0.1:8001/docs`. |
| Dashboard shows "Backend unavailable" | Start the backend on `127.0.0.1:8001` (see *Run the dashboard*), then use **Retry connection**. The banner shows the exact URL the dashboard polls. |
| Browser console shows blocked requests | Re-check `frontend/.env.local` → `NEXT_PUBLIC_API_BASE_URL` (default `http://127.0.0.1:8001`), and that `VARSHA_CORS_ORIGINS` contains the dashboard origin (`http://localhost:3000`). |
| Tests use a separate database | Tests automatically use `varsha_phase1_test.db` (ignored by git). |
| `GET /forecast` shows `fallback_precomputed_ai_source` | Nothing is trained yet. Run `POST /model/train` (or the CLI) for that `lead_hours`, or check `GET /model/status` for the exact reason. |
| `404 model_not_trained` from `/model/report` | That horizon has no artifact. Train it, or omit `lead_hours` to get the most recently trained one. |
| `404 model_artifact_invalid` | The `.joblib` and the report JSON disagree (lead, feature schema version or model version). Retrain with `--force`; the stale artifact is never served. |
| The suite takes minutes | Phase 4 tests train real models into a temp directory. That is the leakage checks doing real work, not a hang. |
