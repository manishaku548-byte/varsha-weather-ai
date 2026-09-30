# Deployment Guide — VARSHA Weather AI (GitHub · Vercel · Render/Railway)

> **Decision-Support Prototype — Synthetic Development Dataset — Not
> Operational Weather Data — Not an Official Weather Warning.**
>
> This guide deploys the SIH26081 **prototype** for evaluation/demo purposes.
> Nothing here claims IMD/NCMRWF integration, operational forecasting, or
> official-warning authority. All deployment is manual — the project never
> deploys automatically and no secret is stored in this repository.

## Overview

| Piece | Where it runs | Root directory | Key env var |
|-------|---------------|----------------|-------------|
| Source code | GitHub | repo root | none (no secrets in git) |
| Dashboard (Next.js) | **Vercel** | `frontend` | `NEXT_PUBLIC_API_BASE_URL` |
| API (FastAPI) | **Render** (or Railway) | `backend` | `PORT` (injected) + `VARSHA_CORS_ORIGINS` |

```
GitHub ──► Vercel (frontend) ── NEXT_PUBLIC_API_BASE_URL ──► Render/Railway (backend)
                                                              ▲
                                              /health probe (200 ok|degraded)
```

The backend serves the dashboard only for origins listed in
`VARSHA_CORS_ORIGINS` (comma-separated). The frontend never computes forecast
numbers; every value is fetched from the API.

---

## 0. Before you start (prerequisites, ~5 minutes)

1. A **GitHub** account and `git` installed locally
   (`git --version`). Windows: Git for Windows / Git Bash; macOS: `xcode-select
   --install`; Linux: `sudo apt install git` (or your distro's package).
2. A **Render** account (<https://render.com>) — free tier is enough.
3. A **Vercel** account (<https://vercel.com>) — free (Hobby) tier is enough.
4. Local working repo checked out and healthy:

```powershell
cd /path/to/varsha-weather-ai
code .   # optional: open in your editor
```

> **Do not** copy `.env` / `.env.local` files, `*.db`, `*.joblib`, or anything
> listed in `.gitignore` into the repository. They stay local.

---

## 1. Create a new empty GitHub repository named `varsha-weather-ai`

1. Go to <https://github.com/new> (logged in).
2. **Repository name:** `varsha-weather-ai`.
3. Leave it **Public or Private** as you prefer (Private is safer for a
   prototype; Render/Vercel import works the same either way).
4. **Do NOT** tick "Add a README", ".gitignore", or "license" — the repository
   already contains all of those.
5. Click **Create repository**.
6. Leave the "…or push an existing repository from the command line" box open —
   you need those commands in step 2 (I reproduce them below).

---

## 2. Push the local code

Run these from the repository root. **This is the first commit** — review
`git status` output before committing and make sure the only listed files are
the intended source, data CSVs and docs (no `.env`, `.db`, `.joblib`,
`node_modules`, `.next`).

```powershell
cd /path/to/varsha-weather-ai

# 1. See exactly what would be committed (should NOT list .env/.db/.joblib/…)
git status --short

# 2. Start tracking everything that is not ignored
git add -A

# 3. Commit
git commit -m "VARSHA Weather AI (SIH26081) — decision-support prototype"

# 4. Point at GitHub and push (replace YOUR-USERNAME)
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/varsha-weather-ai.git
git push -u origin main
```

Sanity check after pushing: on GitHub, confirm the repo tree shows
`README.md`, `LICENSE`, `CONTRIBUTING.md`, `backend/`, `frontend/`, `data/`,
`docs/` — and **no** `.env`, `*.db` or `*.joblib` files.

> First-push-only credentials: GitHub no longer accepts account passwords for
> HTTPS. Use a **Personal Access Token (classic, `repo` scope)** as the
> password, or set up SSH. Never put the token in a file in this repo.

---

## 3. Deploy the backend to Render

> Prefer the one-click **Blueprint** path if it works for you: New →
> Blueprint → pick the repo — Render reads `backend/render.yaml`. It sets the
> root directory, build/start commands and the placeholder CORS origin for you.
> The manual steps below do the same thing and are the canonical reference.

**Manual web service:**

1. Render dashboard → **New** → **Web Service** → **Connect** the
   `varsha-weather-ai` repository.
2. If asked, choose the branch `main`.
3. Configure exactly:

   | Setting | Value |
   |---|---|
   | **Name** | `varsha-weather-ai-backend` |
   | **Region** | closest to you (e.g. `Singapore (Southeast Asia)`) |
   | **Root Directory** | `backend` |
   | **Runtime** | `Python 3` (auto-detected) |
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
   | **Instance Type** | Free |

4. **Environment variables** (below the service form, "Environment"):

   | Key | Value |
   |---|---|
   | `VARSHA_DATA_MODE` | `synthetic` |
   | `VARSHA_CORS_ORIGINS` | `https://your-vercel-domain.vercel.app` *(placeholder — replaced in step 5)* |
   | (optional) `VARSHA_ML_INFERENCE` | `true` |

   `PORT` is injected automatically by Render — do **not** set it. All other
   variables are optional (see `backend/.env.example` and the README
   "Configuration" table).
5. Click **Create Web Service** and wait for the deploy to finish (a few
   minutes on free tier; first deploy is the slowest).
6. Open its public URL. Render gives you
   `https://varsha-weather-ai-backend.onrender.com`.

---

## 4. Copy the backend public URL and check `/health`

```powershell
# Replace with your real URL
$BACK = "https://varsha-weather-ai-backend.onrender.com"

curl.exe -s "$BACK/health"
```

Expected: HTTP 200 with `status: "ok"`, `data_mode: "synthetic"`, the
`disclaimer` string, and record counts. `GET /health` returns `200` even
without the dataset (`status: "degraded"`) — that is deliberate, so the
platform's health check never kills the service during dataset problems.
(Note: on Render a service is "live" only while `/health` responds, which it
does.)

Also check one real endpoint:

```powershell
curl.exe -s "$BACK/forecast?district=Prayagraj&date=2025-09-03&lead_hours=24"
curl.exe -s "$BACK/model/status"
```

`/model/status` may report `inference_ready: false` — that is expected and
handled (see **Model fallback on deployment**, step 9).

---

## 5. Deploy the frontend to Vercel

1. Go to <https://vercel.com> → **Add New…** → **Project** → **Import** the
   `varsha-weather-ai` repository.
2. Vercel auto-detects **Next.js** with a **Root Directory** of
   `frontend` (choose it if it is not picked automatically). Build command
   `npm run build` and output `frontend/.next` are defaults — leave them.
3. Under **Environment Variables**, add one:

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | `https://varsha-weather-ai-backend.onrender.com` (your step-4 URL, no trailing slash) |

   Apply it to all environments (Production + Preview + Development).
   `NEXT_PUBLIC_*` variables are baked into the build at build time — a value
   change requires a redeploy (Vercel does this automatically on save).
4. Click **Deploy**. Wait for the build (1–3 minutes).
5. Vercel gives your site a URL like `https://varsha-weather-ai.vercel.app`
   (or `https://<project-name>.vercel.app`).

> `frontend/vercel.json` is **not** required — Next.js on Vercel needs no
> extra config, and deliberately none was added. The map tiles load from the
> public Leaflet CDN over HTTPS, which Vercel serves fine.

---

## 6. Point the backend CORS at the real Vercel URL, then redeploy

1. Open your Render service → **Environment** tab.
2. Set **`VARSHA_CORS_ORIGINS`** to your real frontend origin, e.g.:
   `https://varsha-weather-ai.vercel.app`
3. **Save Changes** → Render redeploys. After it is live, re-check
   `/health`.

If you later deploy a preview/integration branch with a different Vercel URL,
add it comma-separated (e.g.
`https://varsha-weather-ai.vercel.app,https://varsha-weather-ai-git-main-yourname.vercel.app`).

---

## 7. Test the deployed frontend

Open `https://varsha-weather-ai.vercel.app`. Checklist (more detail in
`docs/SIH_DEMO_CHECKLIST.md`):

- [ ] Header shows **Connected**; mandatory banner visible (Decision-Support
      Prototype · Synthetic Development Dataset · Not Operational Weather
      Data · Not an Official Weather Warning)
- [ ] Forecast: Prayagraj · 2025-09-03 · 24 h → hero renders (~150 mm,
      Critical, Heavy-Rain Risk, High confidence) — numbers read live from
      the API
- [ ] **Why this forecast?** loads the explanation
- [ ] Backtest runs and shows metrics + honest comparison
- [ ] **Source failure** (simulate NWP/Ensemble/AI) shows the Degraded mode,
      weight 0.0000 and confidence drop; Reset works
- [ ] **Expert override** saves with a mandatory reason; audit timeline shows
      the preserved original output
- [ ] **Broken backend behaviour:** stop the Render service (or set
      `NEXT_PUBLIC_API_BASE_URL` to a wrong URL and redeploy) → the dashboard
      shows the *Backend unavailable* banner with the exact URL it polls and a
      **Retry connection** button — never a crash or blank screen

---

## 8. Free-tier caveats (read before demoing from the cloud)

| Caveat | What it means for VARSHA |
|---|---|
| **Cold starts** | After ~15 min of no traffic (Render free; Vercel serverless), the first request is slow (5–30 s). Click **Retry connection** if the banner appears, then wait. |
| **Ephemeral filesystem** | Render free/Railway starter have **no persistent disk**. Anything written at runtime — SQLite audit rows (`varsha_weather_ai.db`), `/backtest` CSV/JSON reports, retrained `*.joblib` — is **lost on every redeploy/restart**. The app recreates missing dirs and starts with a fresh DB. |
| **No persistent model artifacts** | Because `.joblib` files are git-ignored, a fresh deploy has **no trained model** and the AI source honestly serves the `fallback_precomputed_ai_source` label until you retrain on the instance (step 9). |
| **Resource limits** | Free instances are small (512 MB RAM typical). A backtest over a very long range or a `/model/train` run may be slow; keep ranges modest (≤ ~60 dates for a live demo). |
| **No production guarantees** | This is a prototype with synthetic data. The cloud URLs are demo/evaluation instances, not operational weather services. |

---

## 9. Model fallback on deployment — what to expect, how to fix

**Why:** `data/models/*.joblib` is git-ignored on purpose (it is generated
locally from synthetic data). A fresh cloud deploy therefore has no artifact,
so `GET /model/status` reports `inference_ready: false` and forecasts label the
AI source `fallback_precomputed_ai_source` with the exact reason. This is the
designed **disclosed fallback**, not a bug.

**Options:**

- **A. Leave it (recommended for demos).** The dashboard already shows the
  labelled fallback; the demo remains honest and complete.
- **B. Train on the instance (works until the next redeploy).** Call the API
  once per horizon:
  ```powershell
  curl.exe -s -X POST "$BACK/model/train" -H "Content-Type: application/json" -d '{"lead_hours": 6}'
  curl.exe -s -X POST "$BACK/model/train" -H "Content-Type: application/json" -d '{"lead_hours": 24}'
  curl.exe -s -X POST "$BACK/model/train" -H "Content-Type: application/json" -d '{"lead_hours": 72}'
  ```
  Training uses only the shipped synthetic data, ~1–3 min per horizon, and
  writes into `data/models/` on the instance. The training report JSON is
  served via `GET /model/report?lead_hours=…`. **Reminder:** these artifacts
  vanish on redeploy (ephemeral disk).
- **C. Persistent disk (Render paid; Railway volumes).** Mount a persistent
  disk and point the writable paths at it, then train once:
  - `VARSHA_MODELS_DIR=/data/models`
  - `VARSHA_REPORTS_DIR=/data/reports`
  - `VARSHA_DB_URL=sqlite:////data/varsha_weather_ai.db`
  With a disk, retrained artifacts and audit rows survive redeploys. Be aware
  mounting a disk changes the *instance's* filesystem only — it never turns
  the synthetic model into an operational one.

---

## 10. Railway alternative (if you prefer Railway over Render)

Same app, same commands. In Railway:

1. **New Project** → **Deploy from GitHub repo** → select
   `varsha-weather-ai`.
2. **Add a service** pointing at the `backend` directory (Railway calls this
   the service's *Root Directory* / project settings).
3. Railway reads `backend/railway.json` and the `Procfile` (start command
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/health`).
4. Add the same env vars as step 3.4 (`VARSHA_DATA_MODE`,
   `VARSHA_CORS_ORIGINS`); Railway injects `PORT` too.
5. Public URL looks like `https://varsha-weather-ai-backend.up.railway.app` —
   use it as `NEXT_PUBLIC_API_BASE_URL` on Vercel and as the CORS origin.

---

## 11. Troubleshooting

| Symptom | Cause & fix |
|---|---|
| **CORS error in the browser console** (`blocked by CORS policy`) | The frontend origin is not in backend `VARSHA_CORS_ORIGINS`. Set it to the **exact** Vercel origin (scheme + host, **no trailing slash**), save → Render redeploys. If you have Preview URLs, add them comma-separated. |
| **`502` / `503` on the backend URL** | Usually a cold start or a build/deploy in progress — wait 10–60 s and retry `/health`. `503` with an error payload = an app-level error (e.g. missing dataset): check Render logs and `GET /health` (should still be 200 `degraded`). |
| **Frontend shows "Backend unavailable" + wrong URL** | `NEXT_PUBLIC_API_BASE_URL` is baked at build time. Fix the env var in Vercel → save → redeploy. Re-check the URL in the banner after it reloads. |
| **Model chip says fallback / `inference_ready: false`** | Expected on a fresh deploy (see step 9). Train via `POST /model/train`, or demo the disclosed fallback state. |
| **Leaflet map not rendering / tiles missing** | Tiles come from the public Leaflet CDN over HTTPS; block a corporate proxy or offline network and the tiles fail while the rest of the page works. The map is a client-only component (no SSR) — verify you are on the public Vercel URL, not a firewalled localhost. |
| **Audit log / overrides reset after redeploy** | SQLite is ephemeral on free hosting. Use step 9C (persistent disk + `VARSHA_DB_URL`) if you need durability; otherwise this is a documented free-tier limitation, not data corruption. |
| **Backtest report 404 or old-looking numbers** | Reports are generated per request into `data/reports/` and are ephemeral. Regenerate with the same query params. |
| **Service stuck "Live" but `/forecast` slow** | Cold start + synthetic-data loading. First forecast after idle is the slowest; keep the instance warm before a demo. |

---

## 12. Post-deployment verification checklist

Run once after Go-Live before any demo/pitch:

- [ ] `curl $BACK/health` → 200, `status: ok`, disclaimer present
- [ ] `curl $BACK/forecast?...` → 200 with `ml_model.source_label` present
- [ ] `curl $BACK/model/status` → known value (`inference_ready` true/false and expected)
- [ ] `curl $BACK/backtest?...` → 200, metrics + honest comparison
- [ ] Dashboard loads over HTTPS, header **Connected**, mandatory banner visible
- [ ] Forecast hero matches backend values (150.6 mm / Critical / Heavy-Rain / High for the demo scenario)
- [ ] Source-failure simulator works (Degraded, weight 0.0000, confidence drop)
- [ ] Expert override saves + audit timeline updates
- [ ] Wrong-URL test → clean *Backend unavailable* banner (then restore the correct URL)
- [ ] Browser console: zero CORS errors, zero failed API requests
- [ ] `git status` clean in the repo; no secrets pushed (see next section)

---

## 13. Keeping secrets out of the repository

- Only `.env.example` files are tracked (root/`backend`/`frontend` have them).
- `.gitignore` never tracks: `.env`, `.env.*` (except `.env.example`),
  `*.db`, `*.sqlite*`, `*.joblib`, `node_modules/`, `.next/`, `logs/`,
  generated `data/reports/*` files, IDE settings.
- Render/Vercel **dashboard env variables are the only secret store** the
  project uses. If you ever add a real key, add it there, never in git.
- Quick local scan before any push:

```powershell
# list everything git would add (should show only intended files)
git add -A --dry-run

# look for obvious secrets in tracked files
git grep -n -i -E "(api[_-]?key|secret|password|token|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY)" -- ":!*.md" ":!LICENSE"
```

---

## Related documents

- `docs/SIH_DEMO_CHECKLIST.md` — pre-demo smoke test + **pre-push checklist**
- `docs/demo_scenario.md` / `docs/demo_script.md` — the 3-minute demo
- `docs/limitations.md` — read before quoting any number
- `docs/architecture.md` / `docs/api_contract.md` — design and contracts
- `frontend/README.md` — dashboard setup and the backend-connection matrix