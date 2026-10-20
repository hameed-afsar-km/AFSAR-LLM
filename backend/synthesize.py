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

    existing_memories = "\n".join(f"- {m['memory']}" for m in memories)

    prompt = f"""You are an extraction engine for Afsar's personal assistant. Update Afsar's profile and memory with NEWly mentioned facts.

User input: {user_input}

Current known facts:
- Name: {profile.get('name') or 'unknown'}
- Goals: {', '.join(profile.get('goals', [])) or 'none'}
- Preferences: {', '.join(profile.get('preferences', [])) or 'none'}
- Projects: {', '.join(profile.get('projects', [])) or 'none'}
Known memories:
{existing_memories or '- none'}

Extract ONLY facts NOT already known. Output valid JSON with ONLY these keys, and only include keys that have new values:
- "name": full name string
- "communication_style": {{"language", "tone", "approach"}}
- "goals": array of new goal strings
- "preferences": array of new preference strings
- "projects": array of new project strings
- "memories": array of new memory strings (short, factual)

Return "{{}}" if nothing new. No other text."""

    result = model.invoke(
        prompt,
        format="json",
        keep_alive=300,
        options={
            "num_predict": 64,
            "temperature": 0,
        },
    )
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
    new_memory_texts = extracted.get("memories", [])
    if isinstance(new_memory_texts, list):
        new_memories = [
            {"memory": text}
            for text in new_memory_texts
            if isinstance(text, str)
            and text.strip()
            and text.strip() not in existing_memories_texts
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
