"""Shared pytest fixtures.

The SQLite database used by tests is isolated from the dev database.
"""

from __future__ import annotations

import os

os.environ.setdefault("VARSHA_DB_URL", "sqlite:///./varsha_phase1_test.db")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Session-wide API client (starts the app, creates DB tables)."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def dataset():
    """The validated, cached replay dataset."""
    from app.services.dataset import get_dataset

    return get_dataset()


@pytest.fixture(autouse=True)
def _deterministic_ml_state(monkeypatch):
    """Phase 1-3 tests must stay deterministic regardless of model artifacts
    on disk: ML inference is OFF by default. Phase 4 tests opt in through the
    ``model_env`` fixture."""
    from app.config import settings
    from app.services.model_store import clear_model_cache

    monkeypatch.setattr(settings, "ml_inference_enabled", False)
    clear_model_cache()
    yield
    clear_model_cache()


@pytest.fixture()
def model_env(tmp_path, monkeypatch):
    """Isolated model artifacts directory + ML inference enabled.

    Phase 4 tests that need trained-model behaviour use this fixture; artifacts
    are written into ``tmp_path`` so the repo's ``data/models`` stays untouched
    and other tests never see them."""
    from app.config import settings
    from app.services.model_store import clear_model_cache

    monkeypatch.setattr(settings, "models_dir", tmp_path)
    monkeypatch.setattr(settings, "ml_inference_enabled", True)
    clear_model_cache()
    yield tmp_path
    clear_model_cache()
