from langchain_ollama import OllamaLLM

from profile import load_profile
from memory import memory_text

model = OllamaLLM(model="gemma2:2b")


def build_system_prompt():

    profile = load_profile()

    prompt = f"""
You are AfsarLLM.

You are a digital replica of Afsar.

User Profile:

Name:
{profile["name"]}

Communication Style:
{profile["communication_style"]}

Goals:
{profile["goals"]}

Preferences:
{profile["preferences"]}

Projects:
{profile["projects"]}

Known Memories:
{memory_text()}

Instructions:

- Speak in simple English.
- Be practical.
- Be direct.
- Consider Afsar's goals and preferences.
- Remember the provided memories.
"""

    return prompt


def generate_response(user_input: str):

    prompt = f"""
{build_system_prompt()}

User:
{user_input}

Assistant:
"""

    return model.invoke(prompt)