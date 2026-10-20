import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from main import app
from llm import build_system_prompt, current_time_note


@pytest.fixture
def client():
    return TestClient(app)


def test_time_note_format():
    note = current_time_note()
    assert isinstance(note, str)
    assert "local time" in note


def test_build_system_prompt():
    prompt = build_system_prompt()
    assert "Afsar's Assistant" in prompt
    assert "JARVIS" in prompt
    assert "Profile" in prompt
    assert "Long-Term Memory" in prompt


def test_generate_endpoint_mocked(client):
    with patch("main.assistant_service.chat", return_value={"output": "Right, boss. Systems online."}):
        response = client.post("/generate", json={"input": "Hello", "history": []})
        assert response.status_code == 200
        data = response.json()
        assert "output" in data
        assert data["output"] == "Right, boss. Systems online."


def test_generate_stream_sse_protocol(client):
    tokens = ["Hello", " ", "boss", "!"]

    def mock_stream(user_input, conversation_id=None, client_history=None):
        for t in tokens:
            yield t

    with patch("main.assistant_service.chat_stream", side_effect=mock_stream):
        response = client.post("/generate/stream", json={"input": "Hello", "history": []})
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        lines = [line.strip() for line in response.text.split("\n") if line.strip()]
        assert len(lines) >= len(tokens) + 1  # tokens + done

        received_tokens = []
        saw_done = False

        for line in lines:
            assert line.startswith("data: ")
            payload = json.loads(line[6:])
            if payload.get("done") is True:
                saw_done = True
            elif "token" in payload:
                received_tokens.append(payload["token"])

        assert received_tokens == tokens
        assert saw_done is True
