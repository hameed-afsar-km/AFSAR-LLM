import json
import logging
from config import settings

logger = logging.getLogger("afsar.profile")

DEFAULT_PROFILE = {
    "name": "Afsar",
    "communication_style": {
        "language": "",
        "tone": "",
        "approach": "",
    },
    "goals": [],
    "preferences": [],
    "projects": [],
}


def load_profile() -> dict:
    profile_path = settings.DATA_DIR / "profile.json"
    try:
        if profile_path.is_file():
            with open(profile_path, "r", encoding="utf-8") as file:
                return json.load(file)
    except Exception as e:
        logger.warning(f"Failed to read profile at {profile_path}: {e}")

    return dict(DEFAULT_PROFILE)