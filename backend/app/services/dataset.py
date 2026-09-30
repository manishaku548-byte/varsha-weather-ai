"""Dataset loading and caching.

Loads the replay dataset through the adapter interface, validates it once, and
caches the result for the process lifetime.

Decision-Support Prototype — Not an Official Weather Warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..adapters.synthetic_csv import SyntheticCsvAdapter
from ..config import settings
from ..schemas import ValidationSummary
from .validation import validate_dataset


class DatasetUnavailableError(RuntimeError):
    """Raised when required dataset files are missing or unreadable."""


@dataclass
class Dataset:
    """Validated in-memory copy of the replay dataset."""

    data_dir: Path
    adapter_name: str
    data_mode: str
    provider_description: dict[str, str]
    districts: pd.DataFrame
    forecasts: pd.DataFrame
    observations: pd.DataFrame
    validation: ValidationSummary


def load_dataset(data_dir: Path | str | None = None) -> Dataset:
    """Load and validate the dataset (raises DatasetUnavailableError)."""
    directory = Path(data_dir) if data_dir is not None else Path(settings.data_dir)
    adapter = SyntheticCsvAdapter(directory)
    try:
        districts = adapter.load_districts()
        forecasts = adapter.load_forecasts()
        observations = adapter.load_observations()
    except FileNotFoundError as exc:
        raise DatasetUnavailableError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unreadable/corrupt file
        raise DatasetUnavailableError(
            f"Failed to read dataset from '{directory}': {exc}"
        ) from exc

    validation = validate_dataset(districts, forecasts, observations)

    return Dataset(
        data_dir=directory,
        adapter_name=adapter.name,
        data_mode=adapter.data_mode,
        provider_description=adapter.describe(),
        districts=districts,
        forecasts=forecasts,
        observations=observations,
        validation=validation,
    )


_cache: dict[str, Dataset] = {}


def get_dataset(data_dir: Path | str | None = None) -> Dataset:
    """Return the cached dataset, loading it on first use."""
    directory = Path(data_dir) if data_dir is not None else Path(settings.data_dir)
    key = str(directory)
    if key not in _cache:
        _cache[key] = load_dataset(directory)
    return _cache[key]


def clear_cache() -> None:
    """Drop cached datasets (used by tests and future reload endpoints)."""
    _cache.clear()


def resolve_district(ds: Dataset, query: str | None) -> str | None:
    """Resolve a district id/name (case-insensitive) to its canonical id."""
    if query is None or not str(query).strip():
        return None
    needle = str(query).strip().lower()
    for row in ds.districts.to_dict("records"):
        if str(row["district_id"]).lower() == needle or str(row["district_name"]).lower() == needle:
            return str(row["district_id"])
    raise KeyError(needle)


def available_district_names(ds: Dataset) -> list[str]:
    """Human-readable district list for error messages."""
    return [str(name) for name in ds.districts["district_name"].tolist()]
