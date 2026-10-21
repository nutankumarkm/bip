"""Tests for API and Edge app health endpoints."""

import pytest
from fastapi.testclient import TestClient

from bip.api.app import app as api_app
from bip.edge.app import app as edge_app


@pytest.mark.unit
def test_api_health():
    client = TestClient(api_app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "api"


@pytest.mark.unit
def test_edge_health():
    client = TestClient(edge_app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "edge"
