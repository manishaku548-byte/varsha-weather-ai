# Demo Script — VARSHA Weather AI (backend Phases 1–4 + Phase 5 dashboard)

> **Decision-Support Prototype — Synthetic Development Dataset — Not
> Operational Weather Data — Not an Official Weather Warning.**
>
> Read `limitations.md` before demoing. Every number you point at is computed
> live by the backend from the synthetic replay dataset — nothing is hardcoded.

## 0. Setup (30 seconds, before the clock starts)

```powershell
cd "C:\path\to\varsha-weather-ai\backend"
..\.venv\Scripts\python.exe -m pytest -q        # expect: 257 passed (~6 min)
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

For the dashboard section, also start the frontend in a second terminal:

```powershell
cd "C:\path\to\varsha-weather-ai\frontend"
npm install        # first time only
npm run dev        # → http://localhost:3000
```

Open Swagger: **<http://127.0.0.1:8001/docs>** · Dashboard:
**<http://localhost:3000>**
(If port 8000 is free you may use it; this machine's local LLM client polls
8000, so 8001 is recommended.)

---

## 1. The 2-minute run

### 0:00 — "It's alive, and it's labelled"

```powershell
curl.exe -s http://127.0.0.1:8001/health
```

**Say:** *Phase 1 foundation still up — dataset loaded, 5,400 forecast and
1,800 observation records. Note the disclaimer and the "Synthetic Development
Dataset" label — they appear on every single response.*

### 0:20 — "One request, the whole pipeline"

```powershell
curl.exe -s "http://127.0.0.1:8001/forecast?district=Prayagraj&date=2025-09-15&lead_hours=24"
```

**Point at, in order (≈40 s):**

1. `sources[]` → `raw_forecast_mm` vs `corrected_forecast_mm`, and `bias`
   (`bias_mm = +11.37 mm from 98 records strictly earlier than 2025-09-15`).
   *Bias correction only looks backwards — never at the selected date.*
2. `weather_regime` → label, confidence, the exact rules and thresholds that
   fired. *Heavy-Rain Risk always beats Heatwave beats Active Monsoon beats
   Normal; it is a rule set, not a certified forecast.*
3. `sources[].trust` → every score component stored separately:
   historical skill, recent skill, health, agreement, context factor →
   `trust_score` → `weight`. *Weights are dynamic and sum to 1.*
4. `blend.final_rainfall_mm` = Σ(weight × corrected) with `fallback_mode`.
5. `confidence` → score/label/bands + uncertainty range (marked *not
   calibrated*).
6. `risk` → level, reasons, non-binding actions +
   `Decision-support output only; not an official warning.`

### 1:00 — "Why should anyone trust this number?"

```powershell
curl.exe -s "http://127.0.0.1:8001/forecast/explain?district=Prayagraj&date=2025-09-15&lead_hours=24"
```

**Say:** *Same computation, plain language: a headline, the top-weighted
source with its reason, the source-health/fallback note, and a "Why this
forecast?" list — every bullet built from the same numbers, no invented
values.*

### 1:25 — "Pull the plug on a source"

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/forecast/simulate-source-failure `
  -H "Content-Type: application/json" `
  -d '{"district":"Prayagraj","date":"2025-09-15","lead_hours":24,"failed_source":"ensemble"}'
```

**Point at:** `normal` vs `degraded`
(weights `0.26/0.39/0.35` → `0.47/0.00/0.53`, confidence `87.5 → 61.5`,
fallback `normal → degraded`) and the `explanation[]` diff.
**Say:** *The failed source gets exactly zero weight, the rest renormalise to
1, confidence drops — and the system tells you what changed and why.*

### 1:50 — "It fails loudly, not silently"

```powershell
curl.exe -s -o nul -w "%{http_code}`n" "http://127.0.0.1:8001/forecast?district=Atlantis&date=2025-09-15&lead_hours=24"
curl.exe -s -o nul -w "%{http_code}`n" "http://127.0.0.1:8001/forecast?district=Prayagraj&date=2024-01-01&lead_hours=24"
curl.exe -s -o nul -w "%{http_code}`n" "http://127.0.0.1:8001/forecast?district=Prayagraj&date=2025-09-15&lead_hours=12"
```

**Expected:** `404` (unknown district, lists valid ones), `404` (date outside
the dataset range), `422` (lead must be 6/24/72). All errors are structured
JSON with an `error` key — no stack traces.

**Closing line:** *Everything you saw is computed from the stored dataset by
deterministic rules — no LLM, no hardcoded numbers, no official-warning
authority.*

---

## 2. The 2-minute numeric-validation demo (Phase 3)

**Story:** *Anyone can produce a forecast. VARSHA also measures itself —
chronologically, honestly, and exportably.*

### 0:00 — Choose the district and the evaluation range

```powershell
curl.exe -s "http://127.0.0.1:8001/backtest?district=Prayagraj&lead_hours=24&start_date=2025-07-01&end_date=2025-07-20&include_daily_rows=true"
```

**Point at (≈30 s):**

1. `disclaimer` → *Synthetic Development Dataset — Development/Testing Only —
   Not Operational Weather Data — Not an Official Weather Warning.*
2. `evaluation_summary` → 20 dates requested, 20 evaluated, 0 skipped, the
   full skip-reason breakdown. *Skipped dates are never silently dropped.*
3. `event_threshold` → 64.5 mm at 24h, scaled to 16.125 mm at 6h / 193.5 mm
   at 72h — same threshold for observed **and** predicted events.
4. `daily_rows` → one row per date: actual rain, all five predictions, VARSHA
   weights, confidence, risk, source health.

### 0:40 — Compare the five methods (honestly)

**Point at `methods` → `regression_metrics` for this window:**

| Method | MAE (mm) |
|--------|----------|
| NWP bias-corrected | ≈19.9 |
| **Ensemble** | **≈2.8 (best)** |
| AI local correction | ≈10.7 |
| Equal-weight average | ≈6.6 |
| VARSHA dynamic blend | ≈5.9 |

**Then `comparison_summary`:**

* `best_method_by_metric.mae_mm = "ensemble"` — *selected from the returned
  metrics, not assumed to be VARSHA.*
* `outcome_summary` says verbatim: *VARSHA performed **better** than the
  equal-weight average … and **worse** than the best single source (Ensemble
  forecast) … for this selected synthetic evaluation period.*
* `varsha_vs_best_single_source_mae_delta_mm = +3.075` — *positive means
  VARSHA has more error than the ensemble here. We report that; we don't hide
  it.*

**Say:** *On this synthetic window the ensemble beats the dynamic blend —
the evaluation tells the truth even when the truth isn't flattering. All
metrics come from actual engine outputs vs observations, strictly
walk-forward: each date only sees records earlier than itself.*

### 1:20 — Check the event scores

**Point at `methods.varsha_dynamic_blend.event_metrics`:** TP/FP/TN/FN,
precision, recall, F1, false-alarm rate, missed-event rate at the 64.5 mm
threshold, plus `event_count` and the `low_event_sample_warning` — *few
events means we explicitly label the scores statistically weak, and
zero-division cases return `null` with a note instead of a fake 0.*

### 1:40 — Export the CSV

```powershell
curl.exe -s -o backtest_report.csv "http://127.0.0.1:8001/backtest/report?district=Prayagraj&lead_hours=24&start_date=2025-07-01&end_date=2025-07-20&format=csv"
notepad backtest_report.csv
```

**Point at:** the deterministic filename in `Content-Disposition`
(`backtest_prayagraj_24h_2025-07-01_2025-07-20.csv`), one row per date,
`included_in_evaluation`, `skip_reason`, and the `disclaimer` column on every
row. The JSON twin (metrics table, comparisons, versions, limitations) sits
next to it in `data/reports/`.

**Closing line:** *Forecast, explanation, self-evaluation, export — all from
the same deterministic engine, all labelled synthetic, all honest about where
VARSHA wins and where it loses.*

---

## 3. The AI/ML model demo (Phase 4)

**Story:** *The "AI" source is now a real trained model, not a CSV column — and
we tell you exactly how good it is, even when the answer is unflattering.*

### 0:00 — "Nothing trains by itself"

```powershell
curl.exe -s http://127.0.0.1:8001/model/status
```

**Point at:** `artifact_exists`, `trained_lead_hours`, `inference_enabled`,
and `fallback_status` → `{"active": true, "label":
"fallback_precomputed_ai_source", "reason": "No trained model artifact exists
yet; POST /model/train first; …"}`.

**Say:** *The server never trains at startup. The AI source is honestly
labelled as the precomputed fallback, and it says why.*

### 0:25 — Train one horizon (≈15 s)

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/model/train `
  -H "Content-Type: application/json" `
  -d '{"lead_hours": 24}'
```

**Point at, in order (≈40 s):**

1. `disclaimer` → *Synthetic Development Dataset — Development/Testing Only —
   Not Operational Weather Data — Not an Official Weather Warning.*
2. `feature_schema` → 16 features, `features-v1`, and the per-feature
   `timing`/`leakage_safeguard` documentation. *No observation from the target
   date or later is ever an input.*
3. `split` → **chronological, by unique global date**: train
   2025-06-01→2025-08-11 (72 dates / 302 rows), validation
   2025-08-12→2025-09-04 (24 / 113), test 2025-09-05→2025-09-28 (24 / 110).
   *No random shuffling, no future→past.*
4. `candidates` → `linear_regression` 2.5628 mm vs
   `hist_gradient_boosting` 5.3089 mm validation MAE, plus
   `selection_rationale`: *selected by validation MAE only — the test split
   was not used for selection.*
5. `held_out_test_metrics` → MAE 2.3692, RMSE 3.3161, bias +1.9128, median
   1.8246, max 10.8589 over 110 rows. *Evaluated exactly once, after the
   choice was frozen.*
6. `test_references` + `honesty` → **the key moment.**

### 1:05 — "Is the model better? No. Here's the proof."

| Predictor (same 110 held-out rows) | MAE (mm) |
|------------------------------------|----------|
| `naive_train_mean` | 35.95 |
| **Selected model** | **2.37** |
| `raw_nwp` | 2.32 |
| `precomputed_ai_source` | 1.39 |

**Point at:** `honesty.ml_worse_than_baseline = true`,
`worse_than_references: ["raw_nwp", "precomputed_ai_source"]` and the
`summary_sentences`.

**Say:** *On this synthetic dataset, at 24 h, the trained model is **worse**
than the raw NWP value and worse than the old precomputed column. We say that
in the API, in the saved report and in the limitations — we are not going to
claim an improvement the held-out numbers do not support. 120 days and ~600
rows is enough to prove the training pipeline is honest and leakage-free; it
is not enough to beat a good input.*

**If asked "does it ever win?":** *Yes, and we report that too — run the same
training for 6 h and 72 h. In this run the 6 h model (MAE 1.17 vs 3.01 for raw
NWP) and the 72 h model (3.29 vs 7.45) do beat the references, and
`honesty.ml_worse_than_baseline` is `false` for them. The verdict is computed
per horizon on every run; nobody picks the flattering horizon for you.*

### 1:30 — "The forecast now says which one it used"

```powershell
curl.exe -s "http://127.0.0.1:8001/forecast?district=Prayagraj&date=2025-09-15&lead_hours=24"
```

**Point at:** the `ai_local_v1` entry in `sources[]` →
`"source_label": "trained_local_correction_model"`,
`"model_inference_available": true`, `model_version`,
`"status": "model_inference"`, `"quality_flag": "model_prediction"`,
`bias.method: "model_output_passthrough"`, and the top-level `ml_model` block
with the model's held-out test MAE.

**Then show the fallback is disclosed, not hidden** — request a date with no
model training, or restart with `$env:VARSHA_ML_INFERENCE = "false"`:
`source_label` flips to `fallback_precomputed_ai_source` with the exact reason,
and every other field keeps its shape.

### 1:50 — "And the backtest knows which one it measured"

```powershell
curl.exe -s "http://127.0.0.1:8001/backtest?district=Prayagraj&lead_hours=24&start_date=2025-08-15&end_date=2025-08-18"
```

**Point at:** `ai_source_provenance` → `rows_using_trained_model`,
`rows_using_fallback_source`, `mixed_inputs`, `model_versions`, and the `note`
stating that the artifact is trained once, not per date. Report files written
before Phase 4 are served as stored and marked as the fallback source — we
never re-attribute an old metric to the model.

**Closing line:** *Trained on a strict chronological split, selected on
validation MAE alone, evaluated once on held-out future data, compared against
honest references, and reported as the loser where it is the loser.*

### The honest-skip variant (if asked "what if there isn't enough data?")

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/model/train `
  -H "Content-Type: application/json" `
  -d '{"lead_hours": 72, "minimum_samples": 5000}'
```

→ `"status": "skipped_insufficient_data"`, `model_version: null`,
`held_out_test_metrics: null`, a `warnings` explanation, `fallback.active:
true`. *No artifact is written and forecasts keep using the disclosed
precomputed source. A misleading model is worse than no model.*

---

## 4. The dashboard demo (Phase 5 + Phase 6, ~3 minutes in the browser)

**Story:** *Everything you just saw in curl, on one labelled screen — with the
override/audit workflow that the SRS requires.*

Open **http://localhost:3000**. Recommended order (the slim *Suggested 3-minute
demo flow* strip on the page mirrors these exact steps):

1. **Header & banner (0:00–0:20).** "Decision-Support Prototype" badge, green
   health dot (*Connected*), the *Synthetic Development Dataset —
   Development/Testing Only* banner, and "Not an Official Weather Warning"
   labels. Use the role selector → **Viewer**: the Expert Review section
   disappears (read-only demo); switch back to **Forecaster**.
2. **Load Demo Scenario + hero (0:20–0:50).** Click **Load Demo Scenario** in
   the demo strip — it only sets existing inputs (Prayagraj · 2025-09-03 ·
   24 h) and lets the normal debounced run fetch from the API. The hero shows
   the backend's **Critical** risk, **Heavy-Rain Risk** regime, **≈150.6 mm**
   final rainfall, confidence **81/100 (High)** and the AI-provenance chip
   `trained_local_correction_model`; then hit **Copy Summary** once and paste it
   somewhere to prove the values came from the response (the text includes the
   disclaimer).
3. **Source comparison & weights (0:50–1:10).** raw vs corrected per source
   with bias and status, the dynamic weights bars (which sum to 1, from the
   API), and "Why this forecast?" — every bullet rendered from
   `GET /forecast/explain`, nothing client-computed.
4. **Map (1:10–1:30).** District pins from `GET /districts`; click a marker to
   select that district and re-run. Non-selected districts are neutral, never
   invented-risk coloured. The card is labelled *not an official warning map*.
5. **Validation (1:30–2:00).** Backtest metrics table (MAE/RMSE/bias/precision/
   recall/F1/FAR) with the honest baseline highlight + **Download CSV** (the
   browser gets the file from `GET /backtest/report?format=csv`). Switch lead
   to 6 h / 72 h and watch the numbers change — they come from the engine every
   time.
6. **Source failure (2:00–2:20).** Scenario selector → **NWP fails** — on
   2025-09-03 expect NWP weight to fall to 0.0000, confidence to drop
   81 → 69 (-12.2) and the mode to flip to **Degraded** — or the dedicated
   simulator with its confirm dialog → before/after rainfall, confidence and
   weight deltas (all from `POST /forecast/simulate-source-failure`), then
   **Reset**. The simulation state never survives a refresh or a district/date
   change.
7. **Expert override & audit (2:20–3:00).** As **Forecaster**, open *Record
   Expert Override*, pick a different risk level, enter a **mandatory reason**
   (empty reason must be blocked — Escape also closes the dialog), submit →
   the audit timeline shows original vs overridden risk, the preserved original
   rainfall, actor/role and ISO timestamp. API: `POST /overrides`,
   `GET /audit-logs`.
8. **System details & health.** Expand *System Details* → versions, dataset
   window, source health, fallback status, current request. The header's health
   chip is live `GET /health`; **Ctrl+P** prints a clean forecast/validation
   summary (controls, map and simulators are hidden by print CSS).

**If asked "what if the backend is down?":** stop the backend → the banner
changes to *Backend unavailable* with the exact URL; press **Retry connection**
after restarting it. No stack traces ever appear in the UI.

**Closing line:** *A decision-support prototype: every number on this screen
is fetched from the backend's deterministic engine — the frontend computes no
forecast, weight, confidence, risk or metric — and the override/audit path is
a labelled local review log, not a production authorization record. For the
full walkthrough including expected fallback behaviour, see
`docs/demo_scenario.md`.*

---

## 5. Optional extras (if you have 30 more seconds)

* **Insufficient history:** same `/forecast` call with `date=2025-06-03` →
  `"bias_available": false, "reason": "Insufficient prior history"` and the
  raw value kept.
* **Another regime:** `date=2025-07-31` → `Heavy-Rain Risk` + `Critical`
  risk; `date=2025-06-21` → `Heatwave`.
* **Failure via query param:**
  `.../forecast?district=Prayagraj&date=2025-09-15&lead_hours=24&simulate_failure_source=ai`
* **Full test suite:**
  `..\.venv\Scripts\python.exe -m pytest -q` → `257 passed`.

## 6. Q&A crib sheet

| Question | Answer |
|----------|--------|
| Is this IMD data? | No. Synthetic, seeded, locally generated — labelled everywhere. |
| Where do the weights come from? | 40% historical skill + 25% recent skill + 20% health + 15% agreement × context factor, normalised to 1 (see `docs/architecture.md` §4). |
| Does it use future data? | No. Bias, skill, health and regime context stop strictly before the selected date — tests perturb future observations and assert nothing moves. |
| Is VARSHA the best model? | Not necessarily — the backtest says so when it loses (e.g. the ensemble wins MAE on the 2025-07-01→07-20 Prayagraj window). Best methods are selected from computed metrics only. |
| Are these verification numbers? | Development/testing only: strict chronological backtest on synthetic data, not operational skill, not official-warning verification — every report says so. |
| Can it warn officially? | No. Decision-support only; risk outputs say so verbatim. |
| Is the AI/ML source a real model? | Yes — a scikit-learn local-correction regressor trained on the stored dataset, one per lead horizon, on a strict chronological 60/20/20 split by unique date. Trained only on `POST /model/train`; never at startup. |
| Is the model better than the baseline? | **No, and we say so.** On the held-out future test split (24 h, 110 rows) the model's MAE is 2.37 mm vs 2.32 mm for the raw NWP value and 1.39 mm for the precomputed source. `honesty.ml_worse_than_baseline = true` in the report. |
| How do you know the test set wasn't used for tuning? | Scalers/encoders/imputers and both candidate models are fitted on the training rows only, selection uses validation MAE alone, and the test split is evaluated exactly once after the choice is frozen. Tests perturb future observations and assert nothing moves. |
| What if there isn't enough data to train? | Training is **skipped** with `skipped_insufficient_data`, no artifact is written, and forecasts keep using the precomputed source labelled `fallback_precomputed_ai_source`. |
| Why is confidence capped? | `single_source → ≤39`, `degraded → ≤69`: fewer/failed sources must never look more certain. |
| Do the dashboard numbers match the API? | Yes — the dashboard renders `GET /forecast` / `GET /forecast/explain` / `GET /backtest` / `GET /model/*` responses as-is; it computes no values client-side. |
| Are the override/audit entries real? | Real rows in the local SQLite DB, labelled as a prototype local review log. Roles are a local demo selector, not authentication. |
| Is the map a warning map? | No — coordinates come from `GET /districts`; the map is labelled "not an official warning map" and only colours the selected district from the backend's risk output. |
| Does "Load Demo Scenario" fake a result? | No — it only sets existing controls (Prayagraj · 2025-09-03 · 24 h) and triggers the normal `GET /forecast` / `GET /forecast/explain` calls. It injects nothing and bypasses no calculation. |
