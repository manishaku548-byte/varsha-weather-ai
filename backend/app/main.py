"""VARSHA Weather AI FastAPI application entry point.

Decision-Support Prototype — Not an Official Weather Warning.
All values returned by this API are computed by backend code from the loaded
replay dataset. Nothing here claims official IMD/NCMRWF integration.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import init_db
from .routers import audit, backtest, forecast, meta, model
from .services.dataset import DatasetUnavailableError


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # create audit/override tables (SRS NFR-REL-05)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        f"**{settings.app_name}** — {settings.app_full_form}\n\n"
        f"SIH problem statement: `{settings.problem_statement_id}` — "
        "Hybrid AI–NWP Multi-Model Forecast Blending System.\n\n"
        f"> ⚠️ **{settings.decision_support_disclaimer}**\n\n"
        f"> 📊 **{settings.synthetic_data_label}** "
        f"(data mode: `{settings.data_mode}`).\n\n"
        "This API is an explainable decision-support prototype. It does not replace "
        "meteorologists, does not issue official warnings, and does not claim any "
        "authorized IMD/NCMRWF integration. Every numeric value is computed by the "
        "backend from the loaded historical-replay dataset — no hardcoded forecast "
        "or metric values exist in the frontend or in this API layer."
    ),
    lifespan=lifespan,
    openapi_tags=[
        {"name": "meta", "description": "Service health, district configuration and dataset summary."},
        {
            "name": "forecast",
            "description": (
                "Forecast Intelligence Engine: bias correction, regime detection, "
                "Dynamic Trust Engine weights, blending, confidence and risk guidance."
            ),
        },
        {
            "name": "backtest",
            "description": (
                "Phase 3 verification loop: chronological walk-forward backtesting, "
                "regression/event metrics, honest baseline comparison and CSV/JSON "
                "report export."
            ),
        },
        {
            "name": "model",
            "description": (
                "Phase 4 AI/ML local rainfall-correction model: controlled on-demand "
                "training (chronological splits, validation-MAE selection, single "
                "held-out test evaluation), model report, artifact status and "
                "disclosed fallback behaviour."
            ),
        },
        {
            "name": "audit",
            "description": (
                "Phase 5 expert review: local override records with preserved "
                "system output and the local review/audit timeline. Prototype "
                "review log only — not an official authorization record."
            ),
        },
    ],
)

# Local-only CORS for the Phase 5 Next.js dashboard (never a wildcard).
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(DatasetUnavailableError)
def dataset_unavailable_handler(request: Request, exc: DatasetUnavailableError) -> JSONResponse:
    """Return a helpful 503 instead of a stack trace when data files are missing."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": str(exc),
            "hint": "Run: python -m app.data.synthetic_generator  (from the backend/ directory)",
        },
    )


app.include_router(meta.router)
app.include_router(forecast.router)
app.include_router(backtest.router)
app.include_router(model.router)
app.include_router(audit.router)


def main() -> None:
    """Run the API with uvicorn on 0.0.0.0:$PORT (Render/Railway style).

    Also enables ``python -m app.main`` locally. ``PORT`` defaults to 8001
    (the Phase 5 dashboard demo port) when the environment does not set it.
    """
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
