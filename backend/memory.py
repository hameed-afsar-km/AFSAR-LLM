import json
import logging
from config import settings

logger = logging.getLogger("afsar.memory")


def load_memories() -> list:
    memories_path = settings.DATA_DIR / "memories.json"
    try:
        if memories_path.is_file():
            with open(memories_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                if isinstance(data, list):
                    return data
    except Exception as e:
        logger.warning(f"Failed to read memories at {memories_path}: {e}")
    return []


def memory_text() -> str:
    memories = load_memories()

    text = ""

    for memory in memories:
        if isinstance(memory, dict) and "memory" in memory:
            text += f"- {memory['memory']}\n"

    return text