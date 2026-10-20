import logging
from typing import Any, Dict, Generator, List, Optional

import db
from llm import generate_response, generate_response_stream

logger = logging.getLogger("afsar.assistant")


class AssistantService:
    def __init__(self, history_window_size: int = 10):
        self.history_window_size = history_window_size
        db.init_db()

    def resolve_history(
        self,
        conversation_id: Optional[str] = None,
        client_history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        if conversation_id:
            # Load bounded window of recent messages from SQLite
            return db.get_recent_history(conversation_id, limit=self.history_window_size)
        return (client_history or [])[-self.history_window_size :]

    def chat(
        self,
        user_input: str,
        conversation_id: Optional[str] = None,
        client_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Process chat non-streaming."""
        # 1. If conversation_id is provided, save user message first
        if conversation_id:
            db.save_message(conversation_id, role="user", content=user_input)

        # 2. Retrieve history context
        history = self.resolve_history(conversation_id, client_history)

        # 3. Generate response
        response_text = generate_response(user_input, history)

        # 4. If conversation_id is provided, save assistant message
        if conversation_id:
            db.save_message(conversation_id, role="assistant", content=response_text)

        return {
            "output": response_text,
            "conversation_id": conversation_id,
        }

    def chat_stream(
        self,
        user_input: str,
        conversation_id: Optional[str] = None,
        client_history: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[str, None, None]:
        """Stream response tokens and persist full messages if conversation_id provided."""
        # 1. If conversation_id is provided, save user message first
        if conversation_id:
            db.save_message(conversation_id, role="user", content=user_input)

        # 2. Retrieve history context
        history = self.resolve_history(conversation_id, client_history)

        # 3. Stream tokens and accumulate for DB persistence
        accumulated: List[str] = []
        try:
            for token in generate_response_stream(user_input, history):
                if token:
                    accumulated.append(token)
                    yield token
        finally:
            if conversation_id and accumulated:
                full_response = "".join(accumulated)
                try:
                    db.save_message(
                        conversation_id, role="assistant", content=full_response
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to persist assistant response to DB: {e}"
                    )

    # Conversation management methods
    def create_conversation(
        self, title: str = "New Conversation", conv_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return db.create_conversation(title=title, conv_id=conv_id)

    def list_conversations(
        self, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        return db.list_conversations(limit=limit, offset=offset)

    def get_conversation(self, conv_id: str) -> Optional[Dict[str, Any]]:
        return db.get_conversation(conv_id)

    def delete_conversation(self, conv_id: str) -> bool:
        return db.delete_conversation(conv_id)

    def get_messages(
        self, conv_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        return db.get_conversation_messages(conv_id, limit=limit)


# Global singleton instance for shared usage
assistant_service = AssistantService()
