# Limitations — VARSHA Weather AI

> **Decision-Support Prototype — Synthetic Development Dataset — Not
> Operational Weather Data — Not an Official Weather Warning.**

This page must be read (and shown on screen) alongside any demo of the
system. It states what the prototype **is not**.

## 1. Synthetic data only

1. The entire dataset is generated locally by a seeded script
   (`backend/app/data/synthetic_generator.py`, seed 42). It is *not* IMD,
   NCMRWF, Open-Meteo, NASA, ESA or any real observation or model output.
2. Every API response labels it
   `Synthetic Development Dataset — Not Operational Weather Data`, and every
   forecast payload repeats the full disclaimer.
3. The synthetic generator deliberately plants behaviour (NWP
   under-prediction of heavy rain, ensemble spread, AI strength on moderate
   rain, delayed/anomalous/unavailable bursts) so that bias correction,
   health detection and trust weighting are demonstrable. Those patterns are
   *storytelling for the algorithm*, not measurements of any real model.
4. No number produced from this data may be quoted as an accuracy, skill or
   reliability figure for any real forecasting system.

## 2. No official-warning authority

1. VARSHA is a **decision-support prototype**. It does not issue official
   warnings, does not replace the IMD or any state/district warning centre,
   and must not be used as the sole basis for evacuation, closure or
   deployment decisions.
2. Risk levels (`Low/Moderate/High/Critical`) and preparedness actions are
   prototype constructs driven by configurable thresholds. They carry
   `Decision-support output only; not an official warning.` on every risk
   output.
3. No claim of IMD/NCMRWF/Open-Meteo integration or endorsement exists
   anywhere in code, API or UI.
4. The regime classifier is a transparent **rule set**, not a certified
   meteorological product; its response says
   `Prototype rule set — no meteorological operational certification claimed.`

## 3. Backtesting is development-only — no operational skill claims

1. **Phase 3 chronological backtesting exists now** (`GET /backtest`,
   `GET /backtest/report`): strict walk-forward evaluation (each date uses
   only records earlier than itself), regression metrics (MAE/RMSE/mean bias/
   median/max absolute error), heavy-rain event metrics (TP/FP/TN/FN,
   precision/recall/F1/false-alarm/missed-event), an honest baseline
   comparison and CSV/JSON report export.
2. **But every metric is still computed from the same synthetic development
   dataset.** They are development/testing numbers for engineering confidence
   in the pipeline — **not operational skill scores**, not verification
   against reality, and not evidence of performance for any real forecast
   system. No number from these reports may be quoted as accuracy for a real
   region, season or model.
3. **No official-warning verification.** Event metrics compare VARSHA against
   synthetic observations at a *configurable prototype threshold*
   (64.5 mm/24h default). They do **not** verify any official warning,
   bulletin or threshold of the IMD or any agency, and must never be
   presented as such. Every backtest response and report file carries
   `Synthetic Development Dataset — Development/Testing Only — Not Operational
   Weather Data — Not an Official Weather Warning.`
4. **Small event samples are weak evidence.** The 120-day dataset contains
   only a handful of heavy-rain days per district/lead, so precision, recall
   and F1 rest on few events. The API flags this explicitly
   (`low_event_sample_warning` when fewer than 5 observed events, and
   `Insufficient evaluation sample for reliable comparison.` below 20
   evaluated dates); zero-division scores are returned as `null` with an
   explanation instead of a flattering 0. Treat all event scores as
   indicative only.
5. **Honest comparison, including losses.** `best_method_by_metric` is chosen
   from the returned numbers only; VARSHA is never assumed to win. On the
   sample Prayagraj 24h window 2025-07-01→07-20, for example, the synthetic
   ensemble beats the VARSHA blend on MAE, and the response says exactly
   that. On other windows/results VARSHA may win — neither outcome is
   guaranteed or adjusted.
6. **Single deterministic period.** One seeded dataset, one monsoon season,
   no cross-validation, no multi-year sampling: results may change on any
   other data. Ranges are capped at 366 dates per run.
7. **The AI source is a trained local-correction model, but it is not a
   skill win.** Phase 4 replaced the synthetic `ai_rain_mm` column as the
   AI source with a real scikit-learn model trained on the stored dataset
   (see §4). Do not present it as an improvement over the raw NWP value or
   the precomputed source — on this dataset it is not.
8. **No live feeds yet.** The adapter interface exists
   (`HistoricalReplayAdapter`), but only the synthetic CSV adapter is wired
   in. Swap-in of an authorised feed is a future phase and must be labelled
   separately.
9. The confidence score (0–100) and the uncertainty range are **heuristics**,
   not calibrated probabilities or prediction intervals. The uncertainty
   range is explicitly marked
   `… not a calibrated prediction interval` in every response.
10. Dynamic weights reflect *historical skill against this synthetic
    dataset*. They would need re-estimation against any real dataset.

## 4. The AI/ML local correction model is a pipeline demonstration

Phase 4 trains a real model (`backend/app/services/ml_training.py`) and serves
its prediction as the `ai_local_v1` source. The *methodology* is real and
honest; the *result* is not an improvement, and must not be presented as one.

1. **The model is worse than the references it is compared against.** On the
   default synthetic dataset, 24 h horizon, held-out future test split
   (2025-09-05 → 2025-09-28, 110 rows): the selected model's MAE is
   **2.3692 mm**, against **2.3191 mm** for the unmodified NWP value and
   **1.3878 mm** for the precomputed `ai_rain_mm` source on the same rows
   (naive train+validation mean: 35.95 mm). The training report states this
   explicitly: `honesty.ml_worse_than_baseline = true`, with
   `worse_than_references: ["raw_nwp", "precomputed_ai_source"]` and an
   attached warning. **No blanket accuracy, improvement or superiority claim
   is made anywhere in this project**, and none may be made in a demo.
   The verdict is computed per horizon and per run: in the same run the 6 h
   model (MAE 1.1705 vs `raw_nwp` 3.0069 and `precomputed_ai_source` 1.3119)
   and the 72 h model (MAE 3.2916 vs 7.4518 and 3.7600) *did* beat both
   references, and `honesty.ml_worse_than_baseline` is `false` for them.
   Quoting only the winning horizons would be as dishonest as quoting only the
   losing one.
2. **The dataset is far too small for a weather model.** 120 valid days
   (2025-06-01 → 2025-09-28) × 5 districts = 600 candidate rows per horizon;
   525 usable after the 7-day minimum-history and missing-forecast rules;
   302 / 113 / 110 rows across the train / validation / test splits. A
   113-row validation set cannot support hyperparameter search, and a
   110-row test set cannot support a reliable skill estimate. Both splits are
   in the "indicative only" category.
3. **The features are deliberately simple**, and two of them (`nwp_rain_mm`,
   `ensemble_mean_mm`) already carry most of the signal; the model cannot
   invent information that is not in the inputs. The nonlinear candidate
   (HistGradientBoosting) validated *worse* (5.31 mm) than the linear baseline
   (2.56 mm) on this sample, which is itself evidence of overfitting risk at
   this data size.
4. **Predictions are clipped** to `[0, max_plausible_rain_mm]` in the service
   layer only, and the pipeline output is not clipped during evaluation, so
   reported MAE is the raw model MAE.
5. **No per-date retraining.** The artifact is trained once from a controlled
   chronological split and then reused for every forecast and every backtest
   row. Backtest numbers are therefore *not* a rolling-origin operational
   evaluation, and the backtest provenance block says so.
6. **Historical report files are never re-attributed.** Report JSON/CSV files
   written before Phase 4 keep their original metrics and are served with
   `source_label: "fallback_precomputed_ai_source"`, so a stored Phase 3 metric
   can never be read as a Phase 4 model result.
7. **The fallback is a first-class outcome.** If nothing is trained, inference
   is disabled (`VARSHA_ML_INFERENCE=false`), the artifact fails validation, or
   a row lacks features, the precomputed source is used and the response says
   so (`fallback_precomputed_ai_source` + the exact reason). The switch is
   never silent. If the data is too small to train on, training is **skipped**
   and no artifact is written — a misleading model is worse than no model.
8. **Training is never automatic.** It runs only on an explicit
   `POST /model/train` or `python -m app.train_model`; a single run takes
   roughly 15 seconds and is not part of request handling.
9. **Model metrics are development/testing numbers on synthetic data**, like
   every other number here. They say nothing about performance on real
   rainfall, and they carry the mandatory label
   `Synthetic Development Dataset — Development/Testing Only — Not Operational
   Weather Data — Not an Official Weather Warning.`

## 5. Prototype context priors are hand-set

The Dynamic Trust Engine's context factor (regime/lead-time adjustment) uses
configurable, **hand-set** priors in `config.py`
(`context_regime_factors`, `context_lead_factors`). They are transparent and
tunable, but they are assumptions — not learned from data.

## 6. Scope boundaries

| Dimension | MVP scope |
|-----------|-----------|
| Districts | 5 in Uttar Pradesh (Prayagraj, Lucknow, Varanasi, Kanpur Nagar, Gorakhpur) |
| Variable | Rainfall, mm only |
| Lead times | 6h, 24h, 72h |
| Dates | 2025-06-01 → 2025-09-28 (120 valid days) |
| Users/roles | Viewer/Forecaster/Admin roles are documented in the SRS; the Phase 5 dashboard has a **local role selector** (Viewer/Forecaster/Administrator) for the demo — authentication is not built yet |
| ML model | One local-correction regressor per lead horizon (6 h / 24 h / 72 h), trained on demand from a chronological split; served with a disclosed fallback |
| Frontend | Phase 5 dashboard built (Next.js, single page, light theme); every displayed value is fetched from the backend — none are computed client-side |

## 7. Known technical caveats

1. **Bias correction floor** — `corrected = max(0, raw + bias)`, so a strongly
   negative bias on a near-zero forecast yields 0.0 mm (rainfall cannot be
   negative). The reason string says when the floor was applied.
2. **Threshold scaling** — India-style 24-hour rainfall categories are scaled
   linearly by `lead_hours / 24` (configurable). This is a prototype
   convention, not an official 6-hour or 72-hour classification standard.
3. **Health window** — source health uses the 14 days ending at the selected
   date across *all* districts/leads (configurable), so a burst of bad
   records elsewhere in that window can lower a source's health score.
4. **Single source** — with only one usable source the system still returns a
   number, but capped at Low confidence (≤39) and explicitly labelled
   `single-source fallback`.
5. **SQLite** — the audit/override tables are populated by the Phase 5
   `POST /overrides` / `GET /audit-logs` endpoints. It is a **prototype local
   review log, not an official authorization record** — there is no
   authentication, and a motivated user could edit the file.
6. **Model artifact integrity** — the `.joblib` bundle and its report JSON are
   re-validated on every load (lead horizon, feature-schema version, model
   version). A mismatch surfaces as `model_artifact_invalid` and the artifact
   is never served; retrain with `--force`. Nothing is auto-healed.
7. **Artifact staleness** — the loaded pipeline is cached in memory keyed by file
   modification time and size, so a retrained artifact is picked up without a
   restart, but a hand-edited artifact with an unchanged mtime/size would not
   be. The integrity check, not the cache, is the safety net.
