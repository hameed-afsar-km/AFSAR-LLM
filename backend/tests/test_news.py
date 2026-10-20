import pytest
from news import _clean_title, _topics_from_profile, fetch_headlines


def test_clean_title():
    assert _clean_title("Tesla reports record deliveries - Reuters") == "Tesla reports record deliveries"
    assert _clean_title("Simple Title") == "Simple Title"


def test_topics_from_profile():
    profile = {
        "preferences": ["startup", "AI"],
        "goals": ["build afsGPT"],
        "projects": ["automation"],
    }
    topics = _topics_from_profile(profile)
    assert isinstance(topics, list)
    assert len(topics) > 0
    assert "AI" in topics or "technology" in topics or "startup" in topics


def test_fetch_headlines_cached_or_live():
    # fetch_headlines should safely return a list (from cache or live, never crash)
    headlines = fetch_headlines(topics=["AI", "technology"], force=False)
    assert isinstance(headlines, list)
