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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
MAX_AGE_DAYS = 30
SNIPPET_CHARS = 240
TIMEOUT = 25
USER_AGENT = "paid-search-newsfeed/1.0 (+https://github.com)"
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|source$)")


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


def parse_source(source: dict, seen_at: str) -> list[dict]:
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
        # Aggregatoren (z.B. Google News) hängen " - Quellname" an den Titel
        origin = (entry.get("source") or {}).get("title")
        if origin and title.endswith(f" - {origin}"):
            title = title[: -len(origin) - 3]
        teaser = snippet(entry.get("summary") or (entry.get("content") or [{}])[0].get("value", ""))
        if normalize_title(teaser).startswith(normalize_title(title)):
            teaser = ""
        published = entry_date(entry)
        items.append({
            "id": normalize_url(link),
            "title": title,
            "link": link,
            "source": source["name"],
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


def merge(previous: list[dict], fresh: list[dict], active_sources: set[str]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for item in previous:
        if item.get("source") in active_sources:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", help="URL oder Pfad zur bisherigen items.json")
    parser.add_argument("--out", default="site")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))
    categories = config.get("kategorien", [])
    sources = [s for s in config.get("quellen") or [] if s.get("aktiv", True) and s.get("url")]

    seen_at = now_utc().isoformat()
    fresh, errors = [], []
    for source in sources:
        try:
            items = parse_source(source, seen_at)
            fresh.extend(items)
            print(f"ok    {source['name']}: {len(items)} Artikel")
        except Exception as exc:
            errors.append({"source": source["name"], "error": str(exc)[:160]})
            print(f"FEHLER {source['name']}: {exc}", file=sys.stderr)

    items = merge(load_previous(args.previous), fresh, {s["name"] for s in sources})

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
        sources=sorted({s["name"] for s in sources}),
        errors=errors,
        generated=generated,
        max_age_days=MAX_AGE_DAYS,
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"{len(items)} Artikel, {len(errors)} fehlerhafte Quellen → {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
