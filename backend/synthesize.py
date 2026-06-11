import json
import re
from llm import model
from profile import load_profile
from memory import load_memories


def _save_profile(profile: dict):
    with open("../data/profile.json", "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


def _save_memories(memories: list):
    with open("../data/memories.json", "w", encoding="utf-8") as f:
        json.dump(memories, f, indent=2)


def _extract_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def synthesize(user_input: str) -> dict:
    profile = load_profile()
    memories = load_memories()

    prompt = f"""You are an AI data extraction system for a personal AI assistant called AfsarLLM.

Given the user's input, extract and categorize information about the person (Afsar) into the correct fields.

Current profile:
{json.dumps(profile, indent=2)}

Current memories:
{json.dumps(memories, indent=2)}

User input: {user_input}

Analyze the input and return ONLY valid JSON with these fields:
- "name": string with full name, or null if not mentioned
- "communication_style": {{"language": string, "tone": string, "approach": string}} or null
- "goals": array of strings (new goals to add), or empty array
- "preferences": array of strings (new preferences to add), or empty array
- "projects": array of strings (new projects to add), or empty array
- "memories": array of {{"memory": string}} (new memories to add), or empty array

Rules:
- Only extract information explicitly stated or clearly implied.
- Do NOT duplicate anything already in the current profile or memories.
- If the same information already exists, return an empty array for that field.
- Return valid JSON only, no other text."""

    result = model.invoke(prompt)
    extracted = _extract_json(result) or {}

    changes = {}

    if extracted.get("name"):
        changes["name"] = extracted["name"]
        profile["name"] = extracted["name"]

    if extracted.get("communication_style"):
        changes["communication_style"] = extracted["communication_style"]
        profile["communication_style"] = extracted["communication_style"]

    new_goals = [g for g in extracted.get("goals", []) if g not in profile["goals"]]
    if new_goals:
        changes["goals_added"] = new_goals
        profile["goals"].extend(new_goals)

    new_prefs = [
        p for p in extracted.get("preferences", []) if p not in profile["preferences"]
    ]
    if new_prefs:
        changes["preferences_added"] = new_prefs
        profile["preferences"].extend(new_prefs)

    new_projects = [
        p for p in extracted.get("projects", []) if p not in profile["projects"]
    ]
    if new_projects:
        changes["projects_added"] = new_projects
        profile["projects"].extend(new_projects)

    existing_memories_texts = {m["memory"] for m in memories}
    new_memories = [
        m
        for m in extracted.get("memories", [])
        if m["memory"] not in existing_memories_texts
    ]
    if new_memories:
        changes["memories_added"] = new_memories
        memories.extend(new_memories)

    _save_profile(profile)
    _save_memories(memories)

    return {
        "profile": profile,
        "memories": memories,
        "changes": changes,
        "raw_extracted": extracted,
    }
