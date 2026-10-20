import pytest
from tts import split_sentences


def test_split_sentences_short():
    chunks = split_sentences("Hello boss. How are you today? All good.")
    assert len(chunks) == 3
    assert chunks[0] == "Hello boss."
    assert chunks[1] == "How are you today?"
    assert chunks[2] == "All good."


def test_split_sentences_empty():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


def test_split_sentences_long_clause():
    long_text = "This is a very long sentence that has multiple clauses, and it keeps going on and on without stopping, because we want to see if the sentence splitter appropriately breaks it into chunks based on commas, semicolons, and other natural pauses."
    chunks = split_sentences(long_text, max_len=80)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 100


def test_tts_endpoints():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    # Test /tts endpoint
    res = client.get("/tts?text=Hey")
    assert res.status_code == 200
    assert "audio/mpeg" in res.headers["content-type"]

    # Test /tts/stream endpoint
    res_stream = client.post("/tts/stream", json={"text": "Hey"})
    assert res_stream.status_code == 200
    assert "text/event-stream" in res_stream.headers["content-type"]

