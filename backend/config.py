import os
import logging
from pathlib import Path
from typing import List, Union
from pydantic import BaseModel, Field, field_validator


def _find_default_data_dir() -> Path:
    # 1. Environment variable override
    env_dir = os.getenv("AFSAR_DATA_DIR") or os.getenv("DATA_DIR")
    if env_dir:
        return Path(env_dir).resolve()

    # 2. Check repo root / data relative to this file
    backend_dir = Path(__file__).resolve().parent
    repo_root = backend_dir.parent
    candidate_repo_data = repo_root / "data"
    if candidate_repo_data.exists():
        return candidate_repo_data.resolve()

    # 3. Fallback to backend / data
    candidate_backend_data = backend_dir / "data"
    if candidate_backend_data.exists():
        return candidate_backend_data.resolve()

    # Default to repo root / data even if not yet created
    return candidate_repo_data.resolve()


def _load_env_file() -> None:
    """Load key-value pairs from .env file into os.environ if not already set."""
    backend_dir = Path(__file__).resolve().parent
    repo_root = backend_dir.parent
    for env_path in [backend_dir / ".env", repo_root / ".env"]:
        if env_path.is_file():
            try:
                content = env_path.read_text(encoding="utf-8")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key and key not in os.environ:
                        os.environ[key] = val
            except Exception:
                pass


_load_env_file()


def _get_env(key: str, default: str) -> str:
    return os.getenv(f"AFSAR_{key}") or os.getenv(key) or default


def _parse_origins(val: Union[str, List[str]]) -> List[str]:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            import json
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed]
            except Exception:
                pass
        return [o.strip() for o in val.split(",") if o.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


class Settings(BaseModel):
    HOST: str = Field(default_factory=lambda: _get_env("HOST", "127.0.0.1"))
    PORT: int = Field(default_factory=lambda: int(_get_env("PORT", "8000")))
    OLLAMA_URL: str = Field(default_factory=lambda: _get_env("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"))
    MODEL_NAME: str = Field(default_factory=lambda: _get_env("MODEL_NAME", "llama3.2:3b"))
    MODEL_KEEP_ALIVE: str = Field(default_factory=lambda: _get_env("MODEL_KEEP_ALIVE", "30m"))
    TTS_VOICE: str = Field(default_factory=lambda: _get_env("TTS_VOICE", "en-US-AriaNeural"))
    TTS_RATE: str = Field(default_factory=lambda: _get_env("TTS_RATE", "-8%"))
    TTS_PITCH: str = Field(default_factory=lambda: _get_env("TTS_PITCH", "-4Hz"))
    LOG_LEVEL: str = Field(default_factory=lambda: _get_env("LOG_LEVEL", "INFO").upper())
    DATA_DIR: Path = Field(default_factory=_find_default_data_dir)
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: _parse_origins(
            _get_env(
                "CORS_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000,http://localhost:1420,tauri://localhost,https://tauri.localhost",
            )
        )
    )
    REQUEST_TIMEOUT: float = Field(default_factory=lambda: float(_get_env("REQUEST_TIMEOUT", "60.0")))
    ENV: str = Field(default_factory=lambda: _get_env("ENV", "development"))

    @field_validator("PORT")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"PORT must be between 1 and 65535, got {v}")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "WARN", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}, got {v}")
        return "WARNING" if upper == "WARN" else upper

    @field_validator("DATA_DIR")
    @classmethod
    def validate_data_dir(cls, v: Path) -> Path:
        resolved = Path(v).resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved


settings = Settings()


def setup_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
