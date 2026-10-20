import pytest
from synthesize import _extract_json


def test_extract_json_direct():
    text = '{"name": "Afsar", "goals": ["Build afsGPT"]}'
    extracted = _extract_json(text)
    assert extracted is not None
    assert extracted["name"] == "Afsar"
    assert "Build afsGPT" in extracted["goals"]


def test_extract_json_markdown():
    text = 'Here is the output:\n```json\n{"name": "Afsar", "preferences": ["Fast responses"]}\n```\nHope this helps.'
    extracted = _extract_json(text)
    assert extracted is not None
    assert extracted["name"] == "Afsar"
    assert "Fast responses" in extracted["preferences"]


def test_extract_json_embedded():
    text = 'Result: {"memories": ["Afsar enjoys coding in Python"]} done.'
    extracted = _extract_json(text)
    assert extracted is not None
    assert "Afsar enjoys coding in Python" in extracted["memories"]


def test_extract_json_invalid():
    assert _extract_json("No json here at all") is None
    assert _extract_json("") is None
