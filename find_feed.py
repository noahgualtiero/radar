"""Sucht den RSS-/Atom-Feed einer Seite und gibt einen Eintrag für sources.yaml aus.

Aufruf:
    python find_feed.py https://example.com/blog/ein-artikel [Kategorie]
"""

from __future__ import annotations

import re
import sys
from urllib.parse import urljoin, urlsplit

import feedparser

from build import domain_of, fetch

COMMON_PATHS = ("/feed/", "/rss/", "/feed.xml", "/rss.xml", "/atom.xml", "/index.xml", "/blog/feed/", "/blog/rss/")


def advertised_feeds(page_url: str) -> list[str]:
    """Feed-Links, die die Seite selbst im <head> nennt."""
    try:
        page = fetch(page_url).decode("utf-8", "ignore")
    except Exception:
        return []
    links = re.findall(r"<link[^>]+>", page, re.I)
    feeds = []
    for link in links:
        if re.search(r"application/(rss|atom)\+xml", link, re.I):
            href = re.search(r'href=["\']?([^"\'\s>]+)', link, re.I)
            if href:
                feeds.append(urljoin(page_url, href.group(1)))
    return feeds


def check(url: str) -> tuple[str, int] | None:
    try:
        feed = feedparser.parse(fetch(url))
    except Exception:
        return None
    if feed.entries:
        return feed.feed.get("title") or domain_of(url), len(feed.entries)
    return None


def discover(url: str) -> tuple[str, str, int] | None:
    """Sucht den Feed zu einer Seiten- oder Artikel-URL: (Feed-URL, Titel, Anzahl Einträge)."""
    direct = check(url)
    if direct:  # schon ein Feed
        return url, direct[0], direct[1]
    parts = urlsplit(url)
    home = f"{parts.scheme}://{parts.netloc}"
    candidates = advertised_feeds(url) + advertised_feeds(home + "/")
    candidates += [home + path for path in COMMON_PATHS]
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        result = check(candidate)
        if result:
            return candidate, result[0], result[1]
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    url = sys.argv[1]
    category = sys.argv[2] if len(sys.argv) > 2 else "News"
    found = discover(url)
    if found:
        feed_url, title, count = found
        print(f"Feed gefunden: {feed_url} ({count} Einträge)\n")
        print(f"  - name: {title}\n    url: {feed_url}\n    kategorie: {category}")
        return 0
    print(f"Kein Feed gefunden für {domain_of(url)}. Alternative: RSS.app oder eine Google-News-Suche mit site:{domain_of(url)}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
