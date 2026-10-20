import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_conversations_api_lifecycle(client):
    # 1. Create conversation
    res = client.post("/conversations", json={"title": "Route Lifecycle Conv"})
    assert res.status_code == 200
    conv = res.json()["conversation"]
    conv_id = conv["id"]
    assert conv["title"] == "Route Lifecycle Conv"

    # 2. Get conversation
    res = client.get(f"/conversations/{conv_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["conversation"]["id"] == conv_id
    assert isinstance(data["messages"], list)

    # 3. Update title
    res = client.patch(f"/conversations/{conv_id}", json={"title": "Renamed Conv"})
    assert res.status_code == 200

    # 4. Generate with conversation_id
    with patch("assistant.generate_response", return_value="Affirmative."):
        res = client.post(
            "/generate",
            json={"input": "Are you there?", "conversation_id": conv_id},
        )
        assert res.status_code == 200
        assert res.json()["output"] == "Affirmative."
        assert res.json()["conversation_id"] == conv_id

    # 5. Verify message persisted in conversation
    res = client.get(f"/conversations/{conv_id}")
    msgs = res.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["content"] == "Are you there?"
    assert msgs[1]["content"] == "Affirmative."

    # 6. Delete conversation
    res = client.delete(f"/conversations/{conv_id}")
    assert res.status_code == 200

    # 7. 404 after delete
    res = client.get(f"/conversations/{conv_id}")
    assert res.status_code == 404
