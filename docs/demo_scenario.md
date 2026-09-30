# Demo Scenario — VARSHA Weather AI (Phase 6)

> **Decision-Support Prototype — Synthetic Development Dataset — Not
> Operational Weather Data — Not an Official Weather Warning.**
>
> All values below were measured live from the running API on the shipped
> synthetic dataset and the shipped trained artifacts. **They are guidance,
> not promises** — always read the actual values from the API in the demo.

## The stable scenario

| Field | Value |
|---|---|
| District | **Prayagraj** (`prayagraj`) |
| Valid date | **2025-09-03** |
| Lead horizon | **24 h** |
| Expected data availability | 3/3 sources healthy (`nwp_model_a`, `ensemble_mean`, `ai_local_v1`); observation record present for the date |
| ML inference expected ready | **Yes** — trained artifacts for 6/24/72 h ship on disk; `/model/status` reports `inference_ready: true` and the AI source label is `trained_local_correction_model`. If the artifacts are missing, the disclosed `fallback_precomputed_ai_source` is used instead and the dashboard says so. |
| Regime | **Heavy-Rain Risk** (high regime confidence) |
| Risk level | **Critical** |

Measured on 2026-09-30 against the shipped dataset:

- **Normal run:** final rainfall **150.56 mm**, confidence **81 / 100 (High band)**,
  fallback mode **Normal**.
- Weights: NWP Model A **0.2744**, Ensemble Mean **0.4103**, AI Local
  Correction **0.3153**.
- Uncertainty range ≈ **111.4 – 189.8 mm** (prototype heuristic, not a
  calibrated prediction interval).

## Source-failure sequence (each simulated via POST /forecast/simulate-source-failure)

Run these in order — after each, point at the failed source's **exactly zero
weight**, the renormalised weights (sum 1), the confidence drop and the
`Degraded` fallback label.

| Failed source | Final rainfall | Confidence | Weight change (failed source) | Note |
|---|---|---|---|---|
| `nwp` (NWP Model A) | 174.13 mm | 69 / 100 (Medium) | 0.2744 → **0.0000** | Ensemble 0.5679, AI 0.4321 |
| `ensemble` (Ensemble Mean) | 129.38 mm | 69 / 100 (Medium) | 0.4103 → **0.0000** | NWP 0.4892, AI 0.5108 |
| `ai` (AI Local Correction) | 140.49 mm | 69 / 100 (Medium) | 0.3153 → **0.0000** | NWP 0.4197, Ensemble 0.5803 |

In every case the fallback mode reads `Normal → Degraded`, the confidence drops
exactly 12.2 points (81.2 → 69.0), rainfall swings in the direction the removed
source was biasing the blend, and the backend returns a plain-language
`explanation[]` of exactly what changed. **No dataset or model is mutated by
these simulations.**

## Demo strip & "Load Demo Scenario" button

The dashboard's slim *Suggested 3-minute demo flow* strip includes a **Load
Demo Scenario** button that sets the controls above (Prayagraj · 2025-09-03 ·
24 h · normal replay) and triggers the **normal** `GET /forecast` +
`GET /forecast/explain` calls — it injects nothing and bypasses no calculation.

## Caveats (read these aloud if asked)

1. **Values must be read from the actual API at runtime.** They are reproduced
   from the deterministic engine on the shipped dataset; any regeneration of the
   dataset, retraining, or configuration change can shift them. Never quote the
   numbers above as "expected output" — quote what the screen shows.
2. This is a **synthetic development dataset** and a **decision-support
   prototype**: nothing here is operational weather data or an official
   warning, and no IMD/NCMRWF/government integration exists.
3. `2025-09-03` lies 95 days into the dataset window, so bias correction and
   historical skill use ample strictly-prior history (there is no
   `insufficient_history` risk on this date).
4. If the backend is unreachable, the dashboard shows the *Backend unavailable*
   banner with the exact URL and a **Retry connection** button; the demo strip
   button stays disabled until meta data loads.