import os
from pathlib import Path
import pytest
from pydantic import ValidationError
from config import Settings


def test_default_settings():
    s = Settings()
    assert s.HOST == "127.0.0.1"
    assert s.PORT == 8000
    assert "http" in s.OLLAMA_URL
    assert s.MODEL_NAME == "llama3.2:3b"
    assert s.LOG_LEVEL in ["INFO", "DEBUG", "WARNING", "ERROR"]
    assert s.DATA_DIR.exists()
    assert isinstance(s.CORS_ORIGINS, list)
    assert len(s.CORS_ORIGINS) > 0


def test_invalid_port():
    with pytest.raises(ValidationError):
        Settings(PORT=70000)

    with pytest.raises(ValidationError):
        Settings(PORT=0)


def test_invalid_log_level():
    with pytest.raises(ValidationError):
        Settings(LOG_LEVEL="INVALID_LEVEL")


def test_cors_origins_parsing():
    s = Settings(CORS_ORIGINS=["http://custom:1234"])
    assert s.CORS_ORIGINS == ["http://custom:1234"]
