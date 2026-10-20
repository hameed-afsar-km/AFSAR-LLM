import html
import re
import time
import urllib.parse

import httpx

SEARCH_TTL = 300
_search_cache: dict[str, tuple[float, list[dict]]] = {}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

_SUMMARY_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    text = _SUMMARY_TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _uddg_url(href: str) -> str:
    if "uddg=" in href:
        qs = urllib.parse.urlsplit(href).query
        params = urllib.parse.parse_qs(qs)
        if params.get("uddg"):
            return params["uddg"][0]
    if href.startswith("//"):
        return "https:" + href
    if not href.startswith("http"):
        return "https://" + href
    return href


def _is_ad(url: str) -> bool:
    try:
        host = urllib.parse.urlsplit(url).netloc.lower()
    except Exception:
        return True
    if "duckduckgo.com" in host and "/y.js" in url:
        return True
    return "ad_domain=" in url or "/aclick" in url


def _parse_ddg(html_text: str) -> list[dict]:
    titles = re.findall(
        r'result__a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.DOTALL
    )
    snippets = re.findall(
        r'class="result__snippet"[^>]*>(.*?)</a>', html_text, re.DOTALL
    )
    results: list[dict] = []
    for i, (href, title) in enumerate(titles[:10]):
        title = _strip_tags(title)
        if not title:
            continue
        snippet = _strip_tags(snippets[i]) if i < len(snippets) else ""
        if len(snippet) > 420:
            snippet = snippet[:420] + "…"
        url = _uddg_url(href)
        if _is_ad(url):
            continue
        results.append({"title": title, "url": url, "snippet": snippet})
    return results


def _rss_fallback(query: str, max_results: int) -> list[dict]:
    try:
        res = httpx.get(
            "https://news.google.com/rss/search",
            params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            headers={"User-Agent": USER_AGENTS[0]},
            timeout=8,
        )
        items = re.findall(r"<item>(.*?)</item>", res.text, re.DOTALL)
        out: list[dict] = []
        for item in items:
            m = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
            l = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
            d = re.search(r"<description>(.*?)</description>", item, re.DOTALL)
            title = html.unescape(m.group(1)) if m else ""
            link = l.group(1).strip() if l else ""
            snippet = _strip_tags(d.group(1)) if d else ""
            if title and link:
                out.append(
                    {
                        "title": title,
                        "url": link,
                        "snippet": snippet[:420] or "News article result.",
                    }
                )
            if len(out) >= max_results:
                break
        return out
    except Exception:
        return []


def search_web(query: str, max_results: int = 6) -> list[dict]:
    cached = _search_cache.get(query)
    if cached and time.time() - cached[0] < SEARCH_TTL:
        return cached[1]

    results: list[dict] = []
    errors: list[str] = []
    for ua in USER_AGENTS:
        if results:
            break
        for base in (
            f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}",
            f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}",
        ):
            try:
                res = httpx.get(
                    base,
                    headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"},
                    timeout=10,
                    follow_redirects=True,
                )
                parsed = _parse_ddg(res.text)
                if parsed:
                    results = parsed
                    break
            except Exception as exc:
                errors.append(str(exc))

    if not results:
        results = _rss_fallback(query, max_results)

    if results:
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in results:
            if r["title"] in seen or r["url"] in seen:
                continue
            seen.add(r["title"])
            seen.add(r["url"])
            deduped.append(r)
            if len(deduped) >= max_results:
                break
        results = deduped
        _search_cache[query] = (time.time(), results)

    return results


def web_context(query: str, max_results: int = 5) -> str:
    results = search_web(query, max_results)
    if not results:
        return ""

    lines: list[str] = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**")
        lines.append(f"   URL: {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        lines.append("")
    return "\n".join(lines).strip()


GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hey boss",
    "yo",
    "sup",
    "morning",
    "gm",
    "good morning",
    "good afternoon",
    "good evening",
    "good night",
    "how are you",
    "how are you doing",
    "how's it going",
    "how are things",
    "whats up",
    "what's up",
    "hows it going",
    "good afternoon boss",
    "good morning boss",
    "good evening boss",
    "hey there",
    "hello there",
    "hi boss",
    "hello boss",
}

_INTEREST = [
    "latest",
    "current",
    "today",
    "right now",
    "update",
    "updates",
    "news",
    "news",
    "price",
    "prices",
    "salary",
    "score",
    "weather",
    "trend",
    "trending",
    "compare",
    "comparison",
    "difference",
    "release",
    "releases",
    "version",
    "2025",
    "2026",
    "how to",
    "tutorial",
    "guide",
    "example",
    "best",
    "top ",
    "recommend",
    "worth",
    "date",
    "deadline",
    "launch",
    "startup",
    "company",
    "ai",
    "model",
    "feature",
    "announced",
    "report",
    "study",
    "stock",
    "market",
]

_STARTERS = {
    "what",
    "whats",
    "what's",
    "who",
    "how",
    "why",
    "where",
    "when",
    "which",
    "is",
    "are",
    "can",
    "do",
    "does",
    "explain",
    "define",
    "describe",
    "tell",
    "search",
    "find",
    "check",
    "list",
    "name",
    "give",
    "compare",
}


def should_search(text: str) -> bool:
    t = re.sub(r"\s+", " ", (text or "").strip().lower().rstrip("!?."))
    if not t:
        return False
    if t in GREETINGS:
        return False
    if len(t) <= 3:
        return False

    if any(k in t for k in ("what did i say", "remember", "what did we", "my name")):
        return False

    if any(k in t for k in _INTEREST):
        return True
    if "?" in text:
        return True
    first = t.split()[0].rstrip(",")
    if first in _STARTERS:
        return True
    return False