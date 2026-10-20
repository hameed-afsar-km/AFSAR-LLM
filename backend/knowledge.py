from pathlib import Path

KNOWLEDGE_DIR = Path("../data/knowledge_base")


def list_knowledge_files() -> list[str]:
    if not KNOWLEDGE_DIR.exists():
        return []
    return sorted(
        f.name
        for f in KNOWLEDGE_DIR.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )


def knowledge_text() -> str:
    files = list_knowledge_files()
    if not files:
        return "No documents in knowledge base yet."

    parts = []
    for fname in files:
        fpath = KNOWLEDGE_DIR / fname
        parts.append(f"--- {fname} ---")
        try:
            text = fpath.read_text(encoding="utf-8")
            parts.append(text.strip())
        except Exception as e:
            parts.append(f"[Could not read: {e}]")

    return "\n\n".join(parts)
