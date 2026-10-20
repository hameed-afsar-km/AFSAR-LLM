import uuid
from unittest.mock import patch
import pytest
from assistant import AssistantService
import db


@pytest.fixture
def service():
    return AssistantService(history_window_size=4)


def test_assistant_chat_without_conversation_id(service):
    with patch("assistant.generate_response", return_value="Mocked JARVIS response"):
        res = service.chat(user_input="Hello", client_history=[{"role": "user", "content": "Hi"}])
        assert res["output"] == "Mocked JARVIS response"
        assert res["conversation_id"] is None


def test_assistant_chat_with_conversation_id_persistence(service):
    conv_id = str(uuid.uuid4())
    service.create_conversation(title="Assistant Persistence Test", conv_id=conv_id)

    with patch("assistant.generate_response", return_value="I got your message, boss."):
        res = service.chat(user_input="Remember this please", conversation_id=conv_id)
        assert res["output"] == "I got your message, boss."
        assert res["conversation_id"] == conv_id

        # Check that both user and assistant messages were saved in SQLite
        msgs = service.get_messages(conv_id)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Remember this please"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "I got your message, boss."


def test_assistant_chat_stream_persistence(service):
    conv_id = str(uuid.uuid4())
    service.create_conversation(title="Stream Persistence Test", conv_id=conv_id)

    def mock_stream(user_input, history):
        yield "Right"
        yield ", "
        yield "boss"

    with patch("assistant.generate_response_stream", side_effect=mock_stream):
        tokens = list(service.chat_stream("Status check", conversation_id=conv_id))
        assert tokens == ["Right", ", ", "boss"]

        # Check that accumulated stream was saved as assistant message
        msgs = service.get_messages(conv_id)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "Status check"
        assert msgs[1]["content"] == "Right, boss"
