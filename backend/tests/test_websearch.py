import pytest
from websearch import should_search, GREETINGS


def test_should_search_greetings():
    for g in ["hi", "hello", "hey", "good morning", "how are you", "yo"]:
        assert should_search(g) is False, f"Expected {g} not to trigger search"


def test_should_search_questions():
    assert should_search("what is the current price of bitcoin?") is True
    assert should_search("latest news about artificial intelligence") is True
    assert should_search("who won the game today?") is True


def test_should_search_empty():
    assert should_search("") is False
    assert should_search("   ") is False
    assert should_search("ok") is False
