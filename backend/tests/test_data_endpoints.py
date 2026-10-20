import pytest
from fastapi.testclient import TestClient
from main import app
from profile import load_profile
from memory import load_memories, memory_text


@pytest.fixture
def client():
    return TestClient(app)


def test_get_data_endpoint(client):
    response = client.get("/data")
    assert response.status_code == 200
    data = response.json()
    assert "profile" in data
    assert "memories" in data
    assert isinstance(data["profile"], dict)
    assert isinstance(data["memories"], list)
    assert "name" in data["profile"]


def test_profile_and_memory_loading():
    p = load_profile()
    assert isinstance(p, dict)
    assert "name" in p

    m = load_memories()
    assert isinstance(m, list)

    txt = memory_text()
    assert isinstance(txt, str)
