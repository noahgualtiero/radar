"""Baut den Paid Search Newsfeed.

Holt alle Feeds aus sources.yaml, führt sie mit dem bisherigen Bestand zusammen
(items.json der live Seite oder einer lokalen Datei), entfernt Duplikate,
behält die letzten 30 Tage und schreibt site/index.html + site/items.json.

Aufruf:
    python build.py [--previous URL_ODER_PFAD] [--out site]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit

import feedparser
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
MAX_AGE_DAYS = 30
SNIPPET_CHARS = 240
TIMEOUT = 25
USER_AGENT = "paid-search-newsfeed/1.0 (+https://github.com)"
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|source$)")
DISCOVER = "Entdecken"
NEWS_SEARCH = "https://news.google.com/rss/search?q={q}+when:{days}d&{locale}"
ARXIV_SEARCH = "https://export.arxiv.org/api/query?search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results=50"
OPENALEX_SEARCH = (
    "https://api.openalex.org/works?filter=primary_location.source.issn:{issns},"
    "title_and_abstract.search:{q},from_publication_date:{since}&sort=publication_date:desc&per-page=100"
)
LOCALES = {
    "en": "hl=en-US&gl=US&ceid=US:en",
    "de": "hl=de&gl=CH&ceid=CH:de",
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)]
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, urlencode(query), ""))


def domain_of(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", " ", title.lower()).strip()


def strip_html(text: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def snippet(text: str) -> str:
    text = strip_html(text)
    if len(text) <= SNIPPET_CHARS:
        return text
    cut = text[:SNIPPET_CHARS].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:–- ") + " …"


LOOSE_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%Y-%m-%d", "%d.%m.%Y")


def entry_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    # Nicht standardkonforme Angaben wie "October 22, 2026" (Microsoft Advertising)
    for key in ("published", "updated", "created"):
        raw = (entry.get(key) or "").strip()
        for fmt in LOOSE_DATE_FORMATS:
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return None


def entry_image(entry) -> str | None:
    for media in entry.get("media_content", []) + entry.get("media_thumbnail", []):
        url = media.get("url")
        if url and media.get("medium", "image") == "image":
            return url
    for link in entry.get("links", []) + entry.get("enclosures", []):
        if link.get("type", "").startswith("image/") and link.get("href"):
            return link["href"]
    blobs = [c.get("value", "") for c in entry.get("content", [])] + [entry.get("summary", "")]
    for blob in blobs:
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', blob or "", re.I)
        if match and match.group(1).startswith("http"):
            return html.unescape(match.group(1))
    return None


def entry_tags(entry) -> set[str]:
    return {(t.get("term") or "").strip().lower() for t in entry.get("tags", [])}


def search_sources(config: dict) -> list[dict]:
    """Macht aus jedem Suchbegriff eine Google-News-Suche, die wie eine Quelle abgerufen wird."""
    days = int(config.get("zeitraum_tage", 7))
    sources = []
    for entry in config.get("begriffe") or []:
        lang = entry.get("sprache", "en")
        sources.append({
            "name": f"Suche: {entry['begriff']} ({lang})",
            "url": NEWS_SEARCH.format(q=quote_plus(entry["begriff"]), days=days, locale=LOCALES[lang]),
            "kategorie": DISCOVER,
            "suche": entry["begriff"],
        })
    return sources


def research_sources(config: dict) -> list[dict]:
    """Wissenschaftliche Quellen: arXiv (Preprints) und ausgewählte Fachzeitschriften via OpenAlex."""
    category = config.get("kategorie", "Forschung")
    sources = []
    arxiv = config.get("arxiv") or {}
    if arxiv.get("begriffe"):
        query = " OR ".join(f"abs:{term}" for term in arxiv["begriffe"])
        sources.append({"name": "arXiv", "url": ARXIV_SEARCH.format(q=quote(query)), "kategorie": category})
    journals = config.get("fachzeitschriften") or {}
    if journals.get("begriffe") and journals.get("issn"):
        since = (now_utc() - timedelta(days=MAX_AGE_DAYS)).date().isoformat()
        sources.append({
            "name": "Fachzeitschriften",
            "url": OPENALEX_SEARCH.format(
                issns="|".join(journals["issn"]),
                q=quote("|".join(journals["begriffe"])),
                since=since,
            ),
            "kategorie": category,
            "art": "openalex",
            "begriffe": [term.strip('"').lower() for term in journals["begriffe"]],
        })
    return sources


def openalex_abstract(index: dict | None) -> str:
    if not index:
        return ""
    words = sorted((pos, word) for word, positions in index.items() for pos in positions)
    return " ".join(word for _, word in words)


def parse_openalex(source: dict, seen_at: str) -> list[dict]:
    """OpenAlex liefert JSON statt eines Feeds; Journal-Name wird als Quelle angezeigt."""
    works = json.loads(fetch(source["url"])).get("results", [])
    items = []
    for work in works:
        link = work.get("doi") or (work.get("primary_location") or {}).get("landing_page_url")
        title = strip_html(work.get("title") or "")
        if not link or not title:
            continue
        abstract = openalex_abstract(work.get("abstract_inverted_index"))
        # OpenAlex sucht mit Wortstämmen; nur behalten, was eine Phrase wörtlich enthält
        text = f"{title} {abstract}".lower()
        if not any(term in text for term in source["begriffe"]):
            continue
        journal = ((work.get("primary_location") or {}).get("source") or {}).get("display_name")
        items.append({
            "id": normalize_url(link),
            "title": title,
            "link": link,
            "feed": source["name"],
            "source": journal or source["name"],
            "domain": domain_of(link),
            "search": None,
            "category": source["kategorie"],
            "published": datetime.fromisoformat(work["publication_date"]).replace(tzinfo=timezone.utc).isoformat(),
            "first_seen": seen_at,
            "image": None,
            "snippet": snippet(abstract),
        })
    return items


def parse_source(source: dict, seen_at: str) -> list[dict]:
    if source.get("art") == "openalex":
        return parse_openalex(source, seen_at)
    feed = feedparser.parse(fetch(source["url"]))
    if not feed.entries:
        reason = feed.get("bozo_exception") or "keine Einträge im Feed"
        raise ValueError(str(reason))

    wanted = {c.lower() for c in source.get("nur_kategorien") or []}
    items = []
    for entry in feed.entries:
        link = entry.get("link")
        title = strip_html(entry.get("title", ""))
        if not link or not title:
            continue
        if wanted and not (wanted & entry_tags(entry)):
            continue
        # Aggregatoren (z.B. Google News) nennen den Publisher separat und hängen
        # " - Quellname" an den Titel
        origin = entry.get("source") or {}
        publisher = origin.get("title")
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3]
        teaser = snippet(entry.get("summary") or (entry.get("content") or [{}])[0].get("value", ""))
        if normalize_title(teaser).startswith(normalize_title(title)):
            teaser = ""
        published = entry_date(entry)
        items.append({
            "id": normalize_url(link),
            "title": title,
            "link": link,
            "feed": source["name"],
            "source": publisher if source.get("suche") and publisher else source["name"],
            "domain": domain_of(origin.get("href") or link),
            "search": source.get("suche"),
            "category": source["kategorie"],
            # Ohne Datum gilt der erste Abruf; merge() hält diesen Wert über Läufe hinweg fest
            "published": published.isoformat() if published else None,
            "first_seen": seen_at,
            "image": entry_image(entry),
            "snippet": teaser,
        })
    return items


def load_previous(location: str | None) -> list[dict]:
    if not location:
        return []
    try:
        if re.match(r"^https?://", location):
            raw = fetch(location)
        else:
            path = Path(location)
            if not path.exists():
                return []
            raw = path.read_bytes()
        data = json.loads(raw)
        return data.get("items", [])
    except Exception as exc:  # erster Lauf oder Seite noch nicht online
        print(f"Hinweis: bisheriger Bestand nicht geladen ({exc})", file=sys.stderr)
        return []


def merge(previous: list[dict], fresh: list[dict], active_feeds: set[str]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for item in previous:
        if item.get("feed", item.get("source")) in active_feeds:
            by_id[item["id"]] = item
    for item in fresh:
        old = by_id.get(item["id"])
        if old:
            item["first_seen"] = old.get("first_seen", item["first_seen"])
        if not item["published"]:
            item["published"] = old["published"] if old else item["first_seen"]
        by_id[item["id"]] = item

    cutoff = now_utc() - timedelta(days=MAX_AGE_DAYS)
    items = [i for i in by_id.values() if datetime.fromisoformat(i["published"]) >= cutoff]
    items.sort(key=lambda i: i["published"], reverse=True)

    # Gleicher Titel bei derselben Quelle (z.B. URL-Varianten) nur einmal behalten
    unique, seen = [], set()
    for item in items:
        key = (item["source"], normalize_title(item["title"]))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def filter_discoveries(items: list[dict], ignored: set[str]) -> list[dict]:
    """Suchtreffer nur behalten, wenn sie nicht schon über eine feste Quelle kommen."""
    fixed = [i for i in items if i["category"] != DISCOVER]
    known_domains = {i.get("domain") for i in fixed}
    known_titles = {normalize_title(i["title"]) for i in fixed}
    kept, seen_titles = [], set()
    for item in items:
        if item["category"] == DISCOVER:
            domain, title = item.get("domain", ""), normalize_title(item["title"])
            if domain in known_domains or title in known_titles or title in seen_titles:
                continue
            if any(domain == d or domain.endswith("." + d) for d in ignored):
                continue
            seen_titles.add(title)
        kept.append(item)
    return kept


def unknown_sources(items: list[dict]) -> list[dict]:
    """Domains aus den Suchtreffern, die noch nicht als feste Quelle geführt sind."""
    groups: dict[str, list[dict]] = {}
    for item in items:
        if item["category"] == DISCOVER:
            groups.setdefault(item["domain"], []).append(item)
    rows = []
    for domain, hits in groups.items():
        rows.append({
            "domain": domain,
            "name": Counter(h["source"] for h in hits).most_common(1)[0][0],
            "count": len(hits),
            "latest": max(h["published"] for h in hits),
            "searches": sorted({h["search"] for h in hits if h.get("search")}),
        })
    rows.sort(key=lambda r: (-r["count"], r["domain"]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", help="URL oder Pfad zur bisherigen items.json")
    parser.add_argument("--out", default="site")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))
    categories = config.get("kategorien", [])
    sources = [s for s in config.get("quellen") or [] if s.get("aktiv", True) and s.get("url")]
    searches = config.get("suchen") or {}
    feeds = sources + search_sources(searches) + research_sources(config.get("forschung") or {})

    seen_at = now_utc().isoformat()
    fresh, errors = [], []
    for source in feeds:
        try:
            items = parse_source(source, seen_at)
            fresh.extend(items)
            print(f"ok    {source['name']}: {len(items)} Artikel")
        except Exception as exc:
            errors.append({"source": source["name"], "error": str(exc)[:160]})
            print(f"FEHLER {source['name']}: {exc}", file=sys.stderr)

    items = merge(load_previous(args.previous), fresh, {f["name"] for f in feeds})
    items = filter_discoveries(items, {d.lower() for d in searches.get("ignorieren") or []})

    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    generated = now_utc().isoformat()
    (out / "items.json").write_text(
        json.dumps({"generated": generated, "items": items}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape())
    page = env.get_template("index.html.j2").render(
        items=items,
        categories=categories,
        sources=sorted({i["source"] for i in items if i["category"] != DISCOVER}),
        searches=sorted({f["suche"] for f in feeds if f.get("suche")}),
        unknown=unknown_sources(items),
        errors=errors,
        generated=generated,
        max_age_days=MAX_AGE_DAYS,
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"{len(items)} Artikel, {len(errors)} fehlerhafte Quellen → {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
