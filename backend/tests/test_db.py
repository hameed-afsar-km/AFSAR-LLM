import uuid
import pytest
import db


@pytest.fixture(autouse=True)
def setup_test_db():
    db.init_db()


def test_conversation_crud():
    conv_id = str(uuid.uuid4())
    conv = db.create_conversation(title="Test Stage 2 Conv", conv_id=conv_id)
    assert conv["id"] == conv_id
    assert conv["title"] == "Test Stage 2 Conv"

    fetched = db.get_conversation(conv_id)
    assert fetched is not None
    assert fetched["title"] == "Test Stage 2 Conv"

    # Update title
    updated = db.update_conversation_title(conv_id, "Updated Title")
    assert updated is True
    assert db.get_conversation(conv_id)["title"] == "Updated Title"

    # List conversations
    all_convs = db.list_conversations(limit=10)
    assert any(c["id"] == conv_id for c in all_convs)

    # Delete conversation
    deleted = db.delete_conversation(conv_id)
    assert deleted is True
    assert db.get_conversation(conv_id) is None


def test_messages_persistence_and_bounding():
    conv_id = str(uuid.uuid4())
    db.create_conversation(title="History Test", conv_id=conv_id)

    # Add 5 messages
    for i in range(5):
        role = "user" if i % 2 == 0 else "assistant"
        db.save_message(conv_id, role=role, content=f"Message {i}")

    messages = db.get_conversation_messages(conv_id)
    assert len(messages) == 5
    assert messages[0]["content"] == "Message 0"
    assert messages[4]["content"] == "Message 4"

    # Bounded history window (last 3 messages in chronological order)
    bounded = db.get_recent_history(conv_id, limit=3)
    assert len(bounded) == 3
    assert bounded[0]["content"] == "Message 2"
    assert bounded[1]["content"] == "Message 3"
    assert bounded[2]["content"] == "Message 4"


def test_cascade_delete():
    conv_id = str(uuid.uuid4())
    db.create_conversation(title="Cascade Test", conv_id=conv_id)
    db.save_message(conv_id, role="user", content="Will be deleted")
    assert len(db.get_conversation_messages(conv_id)) == 1

    db.delete_conversation(conv_id)
    assert len(db.get_conversation_messages(conv_id)) == 0
