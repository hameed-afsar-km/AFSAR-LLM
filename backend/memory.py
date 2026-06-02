import json


def load_memories():
    with open("../data/memories.json", "r", encoding="utf-8") as file:
        return json.load(file)


def memory_text():
    memories = load_memories()

    text = ""

    for memory in memories:
        text += f"- {memory['memory']}\n"

    return text