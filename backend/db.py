import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from config import settings

logger = logging.getLogger("afsar.db")


def get_db_path() -> Path:
    db_file = settings.DATA_DIR / "afsar.db"
    return db_file


def get_connection() -> sqlite3.Connection:
    path = get_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


MIGRATIONS = [
    # Version 1: initial conversations and messages tables
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        metadata TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        metadata TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
    CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
    """
]


def init_db() -> None:
    """Initialize database and apply all pending migrations."""
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            """
        )
        cur = conn.execute("SELECT version FROM schema_migrations;")
        applied_versions = {row[0] for row in cur.fetchall()}

        for version, migration_sql in enumerate(MIGRATIONS, start=1):
            if version not in applied_versions:
                logger.info(f"Applying database migration version {version}")
                conn.executescript(migration_sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?);",
                    (version, datetime.now(timezone.utc).isoformat()),
                )
        conn.commit()


def create_conversation(
    title: str = "New Conversation",
    conv_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    conv_id = conv_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata or {})

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, title, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?);
            """,
            (conv_id, title, now, now, meta_json),
        )
        conn.commit()

    return {
        "id": conv_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "metadata": metadata or {},
    }


def list_conversations(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, title, created_at, updated_at, metadata
            FROM conversations
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?;
            """,
            (limit, offset),
        )
        rows = cur.fetchall()

    result = []
    for row in rows:
        meta = {}
        try:
            meta = json.loads(row["metadata"])
        except Exception:
            pass
        result.append(
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "metadata": meta,
            }
        )
    return result


def get_conversation(conv_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, title, created_at, updated_at, metadata
            FROM conversations
            WHERE id = ?;
            """,
            (conv_id,),
        )
        row = cur.fetchone()

    if not row:
        return None

    meta = {}
    try:
        meta = json.loads(row["metadata"])
    except Exception:
        pass

    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "metadata": meta,
    }


def delete_conversation(conv_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM conversations WHERE id = ?;", (conv_id,))
        conn.commit()
        return cur.rowcount > 0


def update_conversation_title(conv_id: str, title: str) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?;",
            (title, now, conv_id),
        )
        conn.commit()
        return cur.rowcount > 0


def save_message(
    conv_id: str,
    role: str,
    content: str,
    msg_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # Ensure conversation exists
    if not get_conversation(conv_id):
        first_title = content[:40].strip() or "New Conversation"
        create_conversation(title=first_title, conv_id=conv_id)

    msg_id = msg_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata or {})

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (msg_id, conv_id, role, content, now, meta_json),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?;",
            (now, conv_id),
        )
        conn.commit()

    return {
        "id": msg_id,
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "timestamp": now,
        "metadata": metadata or {},
    }


def get_conversation_messages(conv_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, conversation_id, role, content, timestamp, metadata
            FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
            LIMIT ?;
            """,
            (conv_id, limit),
        )
        rows = cur.fetchall()

    result = []
    for row in rows:
        meta = {}
        try:
            meta = json.loads(row["metadata"])
        except Exception:
            pass
        result.append(
            {
                "id": row["id"],
                "conversation_id": row["conversation_id"],
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["timestamp"],
                "metadata": meta,
            }
        )
    return result


def get_recent_history(conv_id: str, limit: int = 10) -> List[Dict[str, str]]:
    """Retrieve bounded recent history window formatted as [{'role': ..., 'content': ...}] in chronological order."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT role, content
            FROM (
                SELECT role, content, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            )
            ORDER BY timestamp ASC;
            """,
            (conv_id, limit),
        )
        rows = cur.fetchall()

    return [{"role": row["role"], "content": row["content"]} for row in rows]
