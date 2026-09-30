"""CLI training command for the Phase 4 local correction model.

Runs the exact same service as ``POST /model/train`` — controlled, on-demand,
never automatic:

    .. code-block:: powershell

        ..\\.venv\\Scripts\\python.exe -m app.train_model --lead-hours 24
        ..\\.venv\\Scripts\\python.exe -m app.train_model --lead-hours 24 --force
        ..\\.venv\\Scripts\\python.exe -m app.train_model --lead-hours 6 --minimum-samples 150

Prints the full model report as JSON. Exit code 0 when a trained artifact is
available afterwards (``completed`` / ``already_trained``), 1 when training was
skipped (``skipped_insufficient_data``).

Decision-Support Prototype — Synthetic Development Dataset —
Development/Testing Only — Not Operational Weather Data —
Not an Official Weather Warning.
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import settings
from .services.dataset import get_dataset
from .services.ml_training import train_local_correction_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.train_model",
        description=(
            "Train the VARSHA local rainfall-correction model for one lead "
            "horizon (chronological split; selection by validation MAE; "
            "single held-out test evaluation)."
        ),
    )
    parser.add_argument(
        "--lead-hours",
        type=int,
        required=True,
        choices=(6, 24, 72),
        help="Lead horizon to train for.",
    )
    parser.add_argument(
        "--minimum-samples",
        type=int,
        default=None,
        help="Minimum required training rows (overrides ml_min_train_rows).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Retrain even when a validated artifact already exists.",
    )
    args = parser.parse_args(argv)

    if args.minimum_samples is not None and args.minimum_samples < 1:
        parser.error("--minimum-samples must be >= 1")

    ds = get_dataset()
    report = train_local_correction_model(
        ds,
        lead_hours=args.lead_hours,
        minimum_samples=args.minimum_samples,
        force_retrain=bool(args.force),
        cfg=settings,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if report.get("status") in ("completed", "already_trained") else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
