# Contributing to VARSHA Weather AI

> **Decision-Support Prototype — Synthetic Development Dataset — Not
> Operational Weather Data — Not an Official Weather Warning.**

Thanks for contributing to SIH26081. This is a small, honest prototype: every
number is computed by the backend from the shipped synthetic dataset, and
nothing here claims IMD/NCMRWF/government integration or operational accuracy.
Please keep it that way.

## Local setup (one command per terminal)

```powershell
# Terminal 1 — backend
cd backend
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m pytest        # full suite
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# Terminal 2 — dashboard
cd frontend
npm install
npm run lint
npx tsc --noEmit
npm run build
npm run dev
```

macOS/Linux equivalents use `.venv/bin/python` and `cd frontend && npm install && npm run dev`.

## Rules for contributions

1. **Backend is the source of truth.** The frontend must never compute or
   hardcode forecast, weight, confidence, risk or metric values. Changes that
   move computation client-side will be rejected.
2. **Keep the honesty rules.** No fabricated numbers, no "VARSHA wins"
   defaults, no skipping tests to go green, no silent fallbacks — every
   fallback is disclosed.
3. **Never commit secrets or local state.** No `.env` files (only
   `.env.example`), no SQLite `.db` files, no `.joblib` artifacts, no local
   machine paths, no tokens/API keys. See `.gitignore` and
   `docs/DEPLOYMENT.md`.
4. **Keep the mandatory labels.** "Decision-Support Prototype", "Synthetic
   Development Dataset", "Not Operational Weather Data", "Not an Official
   Weather Warning" must survive every UI/API/doc change.
5. **Changes stay in scope.** No deployment automation, paid services, live
   provider integration, Docker, auth providers, or LLM integration without
   explicit approval.
6. **Quality gates.** Backend: new/updated logic needs pytest coverage; run
   `python -m pytest` from `backend/` until the whole suite passes. Frontend:
   `npm run lint`, `npx tsc --noEmit` and `npm run build` must be clean.
7. **Docs travel with code.** Update README / `docs/` for any behaviour,
   threshold, endpoint or limitation change.
8. **Small, reviewable PRs.** One concern per PR; reference the SRS section
   where relevant (e.g. "BR-13 chronological honesty").

## Pull request checklist

- [ ] Ran the full backend test suite (all pass)
- [ ] Ran `npm run lint` + `npx tsc --noEmit` + `npm run build` (clean)
- [ ] No `.env`, `.db`, `.joblib`, token or local path would be committed
      (`git status` shows only intended files)
- [ ] Mandatory disclaimer labels still present in UI + API responses
- [ ] In scope and consistent with the architecture (docs/architecture.md)