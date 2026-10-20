import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_liveness(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data


def test_health_readiness(client):
    response = client.get("/health/ready")
    # Response can be 200 (ready) or 503 (degraded) depending on live Ollama status
    assert response.status_code in [200, 503]
    data = response.json()
    assert data["status"] in ["ready", "degraded"]
    assert "ollama" in data
    assert "storage" in data
    assert data["storage"]["writable"] is True
