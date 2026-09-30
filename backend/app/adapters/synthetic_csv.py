"""Synthetic CSV adapter — reads the controlled development dataset from /data.

Synthetic Development Dataset — Not Operational Weather Data.
This adapter is the single entry point for Phase 1 data; a future
``AuthorizedFeedAdapter`` can replace it without touching services.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..config import settings
from .base import HistoricalReplayAdapter


class SyntheticCsvAdapter(HistoricalReplayAdapter):
    """Loads districts/forecasts/observations from CSV files on disk."""

    name = "synthetic_csv"
    data_mode = "synthetic"

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)

    # --- internals ---------------------------------------------------------------
    def _path(self, filename: str) -> Path:
        path = self.data_dir / filename
        if not path.is_file():
            raise FileNotFoundError(
                f"Required dataset file '{filename}' not found in '{self.data_dir}'. "
                "Generate it with: python -m app.data.synthetic_generator"
            )
        return path

    # --- HistoricalReplayAdapter --------------------------------------------------
    def load_districts(self) -> pd.DataFrame:
        return pd.read_csv(self._path(settings.districts_file))

    def load_forecasts(self) -> pd.DataFrame:
        return pd.read_csv(self._path(settings.forecasts_file))

    def load_observations(self) -> pd.DataFrame:
        return pd.read_csv(self._path(settings.observations_file))

    def describe(self) -> dict[str, str]:
        return {
            "adapter": self.name,
            "data_mode": self.data_mode,
            "label": settings.synthetic_data_label,
            "source": "controlled synthetic development dataset",
            "provenance_note": (
                "Generated locally by app.data.synthetic_generator with a fixed seed. "
                "It is NOT IMD, NCMRWF, Open-Meteo or any other real-world data source."
            ),
        }
