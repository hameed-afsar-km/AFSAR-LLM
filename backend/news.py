import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
import xml.etree.ElementTree as ET

from profile import load_profile

DATA_DIR = Path("../data")
NEWS_CACHE_FILE = DATA_DIR / "news_cache.json"
STATE_FILE = DATA_DIR / "state.json"

CACHE_MAX_AGE_SEC = 60 * 60
MAX_HEADLINES = 6
NEWS_TIMEOUT = 12

FALLBACK_TOPICS = ["startup", "business", "technology", "AI"]

_PREFERENCE_KEYWORDS = {
    "startup": "startup",
    "business": "business",
    "financ": "economy",
    "invest": "investing",
    "automation": "automation",
    "learn": "technology",
    "build": "technology",
}


def _topics_from_profile(profile: dict) -> list[str]:
    blobs = [
        " ".join(profile.get("preferences", [])),
        " ".join(profile.get("goals", [])),
        " ".join(profile.get("projects", [])),
    ]
    haystack = " ".join(blobs).lower()

    topics: list[str] = []
    if re.search(r"\bai\b|artificial intelligence", haystack):
        topics.append("AI")
    for token, topic in _PREFERENCE_KEYWORDS.items():
        if token in haystack and topic not in topics:
            topics.append(topic)

    if not topics:
        topics = list(FALLBACK_TOPICS)
    return topics[:5]


def _clean_title(title: str) -> str:
    title = title.strip()
    cleaned = re.sub(r"\s+-\s+[^-]+$", "", title)
    return cleaned or title


def _fetch_rss(query: str, limit: int) -> list[dict]:
    url = (
        "https://news.google.com/rss/search"
        + "?q="
        + quote(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    headers = {"User-Agent": "Mozilla/5.0 (AFSAR Assistant)"}
    resp = requests.get(url, headers=headers, timeout=NEWS_TIMEOUT)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    items: list[dict] = []
    for item in root.iter("item"):
        title = _clean_title(item.findtext("title") or "")
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""
        items.append(
            {
                "title": title,
                "source": source,
                "published": (item.findtext("pubDate") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
            }
        )
        if len(items) >= limit:
            break
    return items


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def fetch_headlines(topics: list[str] | None = None, force: bool = False) -> list[dict]:
    topics = topics or _topics_from_profile(load_profile())
    cache = _read_json(NEWS_CACHE_FILE)
    now = time.time()

    if (
        not force
        and cache.get("fetched_at")
        and (now - cache.get("fetched_at", 0)) < CACHE_MAX_AGE_SEC
        and cache.get("topics") == topics
    ):
        return cache.get("headlines", [])

    query = " OR ".join(topics)
    try:
        headlines = _fetch_rss(query, MAX_HEADLINES)
    except Exception:
        stale = cache.get("headlines", [])
        return stale if stale else []

    _write_json(
        NEWS_CACHE_FILE,
        {"fetched_at": now, "topics": topics, "headlines": headlines},
    )
    return headlines


def morning_news_due() -> bool:
    return _read_json(STATE_FILE).get("last_morning_news") != date.today().isoformat()


def mark_morning_news_sent() -> None:
    state = _read_json(STATE_FILE)
    state["last_morning_news"] = date.today().isoformat()
    _write_json(STATE_FILE, state)


_MORNING_PATTERN = re.compile(r"\b(good\s*morning|morning|gm)\b", re.IGNORECASE)
_NEWS_PATTERN = re.compile(
    r"\b(news|headlines|headlines?|briefing|top stories|"
    r"what'?s (going on|happening)|what has been happening)\b",
    re.IGNORECASE,
)
_TOPIC_PATTERN = re.compile(
    r"\bnews\s+(?:about|on|regarding|relevant to)\s+(.+)", re.IGNORECASE
)


def get_news_brief(user_input: str) -> str | None:
    text = user_input.strip()
    is_morning = bool(_MORNING_PATTERN.search(text))
    is_news_request = bool(_NEWS_PATTERN.search(text))

    topic_match = _TOPIC_PATTERN.search(text)
    topics = [topic_match.group(1).strip()] if topic_match else None

    if not (is_morning or is_news_request):
        return None

    if is_morning and morning_news_due():
        headline_list = fetch_headlines(topics or _topics_from_profile(load_profile()))
        mark_morning_news_sent()
    elif is_news_request:
        if topics:
            headline_list = fetch_headlines(topics, force=True)
            if not headline_list:
                headline_list = fetch_headlines()
        else:
            headline_list = fetch_headlines()
    else:
        return None

    if not headline_list:
        return None

    lines = [
        f"{i + 1}. {h['title']} ({h['source']})"
        for i, h in enumerate(headline_list)
        if h.get("title")
    ]
    return "\n".join(lines)