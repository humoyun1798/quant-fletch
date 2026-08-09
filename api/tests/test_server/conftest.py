"""Integration test fixtures — FastAPI TestClient with DI overrides."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope='module')
def client():
    """Module-scoped TestClient for the FastAPI app."""
    from server.main import app
    with TestClient(app) as tc:
        yield tc
