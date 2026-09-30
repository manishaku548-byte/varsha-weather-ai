# SIH Demo & Full-Stack Smoke-Test Checklist — VARSHA Weather AI

> **Decision-Support Prototype — Synthetic Development Dataset — Not
> Operational Weather Data — Not an Official Weather Warning.**
>
> Use this checklist before and during the demo. Two parts: (A) a manual
> full-stack smoke test (run once before the event), and (B) the demo-day
> checklist including the screenshots to capture.

---

## A. Manual full-stack smoke test (before the event)

### A1. Environment

- [ ] Laptop / desktop ready, external display OK at **1366×768** or wider
- [ ] Ports free: **8001** (backend), **3000** (frontend)
- [ ] Python venv present: `varsha-weather-ai\.venv`
- [ ] `frontend\node_modules` present (or run `npm install`)
- [ ] `frontend\.env.local` has `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001`

### A2. Backend

- [ ] Start: `cd backend; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001`
- [ ] `GET /health` → 200, `data_mode: synthetic`, disclaimer present
- [ ] `GET /districts` → 200, 5 districts
- [ ] `GET /data/summary` → 200, range 2025-06-01 → 2025-09-28
- [ ] `GET /model/status` → `inference_ready: true` (artifacts shipped) — if
      `false`, note the fallback label is expected and still demo-safe
- [ ] `GET /model/report?lead_hours=24` → report JSON with split & metrics

### A3. Frontend

- [ ] Start: `cd frontend; npm run dev` (or `npm run start` after `npm run build`)
- [ ] Open **http://localhost:3000** — header shows *Connected*, green dot
- [ ] Mandatory labels visible: *Decision-Support Prototype*, *Synthetic
      Development Dataset*, *Not Operational Weather Data*, *Not an Official
      Weather Warning*
- [ ] Controls enabled: district, date (min/max from backend), lead 6/24/72,
      scenario, Run Forecast

### A4. Core scenarios (verify each)

- [ ] **Normal forecast:** Prayagraj · 2025-09-03 · 24 h → hero shows Critical
      risk, ~150 mm, Heavy-Rain Risk regime, confidence ≈ 81/100 High
- [ ] **Explanation:** "Why this forecast?" bullets match the hero numbers
      (same backend run)
- [ ] **Backtest:** Run Backtest → "Evaluated N of N dates", metrics table
      (MAE/RMSE/Bias/Precision/Recall/F1/FAR), honest baseline comparison;
      Download CSV Report → file saved
- [ ] **ML model:** per-lead table shows trained artifact + held-out test MAE
      for 6/24/72 h; AI source chip says *Trained Local-Correction Model*
- [ ] **Source-failure:** simulate NWP failure → confirm → NWP weight 0.0000,
      confidence drop, *Degraded* mode, before/after cards, Reset works
- [ ] **Expert override (Forecaster):** empty reason blocked; valid reason
      saved; audit timeline shows original vs overridden risk, preserved
      original rainfall, actor/role/timestamp
- [ ] **Role gating:** Viewer hides Expert Review + audit; Administrator restores
- [ ] **Load Demo Scenario:** button sets Prayagraj/2025-09-03/24h and triggers
      the normal API run (network tab shows `GET /forecast`)
- [ ] **Copy Summary:** button copies backend values + disclaimer to clipboard

### A5. Error handling (each must fail loudly, never blank/zero)

- [ ] **Backend offline:** stop uvicorn → banner *Backend unavailable* with
      `http://127.0.0.1:8001` + Retry; restart → Retry / auto-poll → Connected
- [ ] **Invalid district / date:** 404 with a structured message (dashboard
      date input enforces the backend range)
- [ ] **Missing forecast:** a date with no usable sources → 503-style message,
      no fabricated number
- [ ] **Missing model artifact:** temporarily rename `data/models/*.joblib` →
      model status reports inference unavailable, AI source falls back with an
      explicit label (restore afterward)
- [ ] **No-data state:** Source Failure panel before any run shows its
      explanatory EmptyState; validation before run shows its EmptyState
- [ ] **Refresh:** reload the page → no crash, no stale scenario/simulation
      artefacts, controls reset to current backend defaults

---

## B. Demo-day checklist

### B1. Pre-demo (10 minutes)

- [ ] Start backend & frontend (commands in section A2/A3)
- [ ] Open http://localhost:3000 and http://127.0.0.1:8001/docs (Swagger)
- [ ] Browser zoom 100%; window at demo resolution; no other tabs stealing focus
- [ ] Set role selector to **Forecaster**
- [ ] Click **Load Demo Scenario** to pre-warm the forecast for 2025-09-03

### B2. Suggested 3-minute narration

1. **Forecast (0:00–0:40)** — hero: 150.6 mm, Critical risk, Heavy-Rain Risk
   regime, confidence 81/100, *Trained Local-Correction Model* chip, disclaimers.
2. **Why this forecast? (0:40–1:00)** — source comparison + weights + explain
   bullets, all from the backend.
3. **Backtest (1:00–1:30)** — Run Backtest → metrics table + honest comparison;
   Download CSV.
4. **Source failure (1:30–2:10)** — Simulate Ensemble Failure → weight 0.0000,
   confidence 81→69, Degraded; Reset.
5. **Expert override (2:10–2:45)** — Record Expert Override → reason (mandatory)
   → audit timeline shows Low→High-style change with original rainfall
   preserved.
6. **(Optional) System health + offline (2:45–3:00)** — System Details; stop
   backend → offline banner with URL → restart → Retry connection.

See `docs/demo_script.md` for the full narration text and talking points.

### B3. Screenshots to capture (for the report/pitch)

1. **Dashboard overview** — header + banner + controls + hero (default view)
2. **Forecast / weights / explanation** — source comparison + dynamic weights +
   "Why this forecast?"
3. **Backtest metrics** — metrics table + honest baseline verdict
4. **Failure simulation** — before/after cards + weight-change table
5. **Override / audit timeline** — modal with reason + updated timeline entry
6. **Model status** — per-lead trained artifacts table
7. *(Optional)* **Offline banner** — backend down state with URL + retry

### B4. Fallback plan if something fails

| Failure | Fallback |
|---|---|
| Backend won't start (port conflict) | `--port 8001` is in use → pick a free port and set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`, restart frontend |
| Frontend build broken | Run `npm run dev` (no build step); if node_modules broken → `npm install` again |
| Model artifacts missing (model chip says fallback) | Demo the *disclosed fallback* explicitly — it is a designed, labelled state |
| Backend dies mid-demo | Restart uvicorn, click **Retry connection**; no data is lost (read-only demo) |
| Network/panel not loading | Use Swagger at `http://127.0.0.1:8001/docs` to show the same endpoints |
| Date/risk differs from this checklist | Read the values displayed — they are computed live; never claim a specific number is guaranteed |

### B5. Reminders

- [ ] Start every section with the **disclaimer statement** (see
      `docs/demo_script.md` § Disclaimer).
- [ ] Say "synthetic development data" at least once early and once at the end.
- [ ] Never claim IMD / NCMRWF / government integration or operational accuracy.
- [ ] Never say the map is a warning map (it is labelled *not an official
      warning map*).
- [ ] Close with: *every number on screen is computed by the backend; the
      frontend computes nothing.*

---

## C. Pre-push / GitHub deployment checklist (Phase 7)

Run before `git add` / `git commit` / `git push` or any cloud deployment.
Full runbook: `docs/DEPLOYMENT.md`. **No automatic commit, push, repository
creation or deployment happens without explicit approval.**

### C1. Quality gates

- [ ] Backend: full suite passes from `backend/` —
      `..\.venv\Scripts\python.exe -m pytest` (257 tests)
- [ ] Frontend: `npm run lint` → 0 errors; `npx tsc --noEmit` → clean;
      `npm run build` → success
- [ ] `git status` shows **only intended files** (no `.env`, `.db`,
      `.joblib`, `node_modules`, `.next`, generated `data/reports/*`)

### C2. Secrets & local state scan

- [ ] `git add -A --dry-run` reviewed — no `.env`, `.env.local`,
      `*.db`, `*.sqlite*`, `*.joblib`, `logs/`, IDE settings, local absolute
      paths (`C:\Users\...`) in any file that would be committed
- [ ] `git grep -n -i -E "(api[_-]?key|secret|password|token|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY)"` over tracked files shows only docs/example text (or nothing)
- [ ] Only `.env.example` files are tracked (root + `backend/` + `frontend/`)
- [ ] No GitHub PAT / Render / Vercel / API tokens stored anywhere in the repo

### C3. Repository hygiene

- [ ] `LICENSE` (MIT) present; `CONTRIBUTING.md` present
- [ ] Root `README.md` has the GitHub-ready sections (overview, SIH26081,
      architecture, local setup, deployment, env vars, disclaimers,
      screenshots placeholders, limitations)
- [ ] `docs/DEPLOYMENT.md` present with exact Render/Vercel values
- [ ] Mandatory disclaimer labels present in UI, API responses and docs
      (Decision-Support Prototype · Synthetic Development Dataset · Not
      Operational Weather Data · Not an Official Weather Warning)
- [ ] `data/` synthetic CSVs and docs are tracked; `data/reports/` and
      `data/models/.gitkeep` keep the folders, generated contents stay ignored

### C4. Cloud-config sanity

- [ ] `backend/Procfile` start command uses `$PORT`
- [ ] `backend/render.yaml` / `backend/railway.json` contain **no secrets**
      (CORS origin is a placeholder or dashboard-set)
- [ ] `backend/.env.example` and `frontend/.env.example` are committed and
      contain **no real secrets**
- [ ] Deployment docs state that free hosting is ephemeral and the model
      starts in disclosed fallback mode until trained on the instance