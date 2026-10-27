"""Baut Radar, den Paid-Search-Newsfeed.

Holt alle Feeds aus sources.yaml, führt sie mit dem bisherigen Bestand zusammen
(items.json der live Seite oder einer lokalen Datei), entfernt Duplikate,
behält die letzten 30 Tage, ordnet Themen zu, erkennt Studien, Vortages-Themen
und Trends und schreibt site/index.html + site/items.json.

Aufruf:
    python build.py [--previous URL_ODER_PFAD] [--out site]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
MAX_AGE_DAYS = 30
SNIPPET_CHARS = 240
TIMEOUT = 25
USER_AGENT = "paid-search-newsfeed/1.0 (+https://github.com)"
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|source$)")
TZ = ZoneInfo("Europe/Zurich")
DISCOVER = "Entdecken"
COMMUNITY = "Community"
STUDIES = "Studien"
TREND_DAYS = 3
# Stellenanzeigen sind keine Artikel: Titel- und Link-Muster, die für alle Quellen gelten
JOB_TITLE = re.compile(
    r"working student|werkstudent|\binternship\b|\bintern\b|praktikum|praktikant|all genders|"
    r"\([mwd/]{5}\)|we.re hiring|job opening|stellenangebot|find [\w ]*jobs",
    re.I,
)
JOB_LINK = re.compile(r"(//|\.)(careers|jobs|karriere)\.|/(careers|jobs|karriere|stellen)/", re.I)
OG_IMAGE_LIMIT = 40  # Titelbilder, die pro Lauf höchstens nachgeladen werden
OG_IMAGE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)["\']',
    re.I,
)
# Wörter, an denen ein Beitrag aus einer beliebigen festen Quelle als Studie erkannt wird
STUDY_PATTERN = re.compile(
    r"\b(study|studies|studie|studien|benchmarks?|survey|umfrage|whitepaper|research|"
    r"we analy[sz]ed|analysis of|data shows|report finds|new report|state of|forecast|prognose)\b"
)
STOPWORDS = set("""
    about after again also among and from have here into just more most must over than that their them
    then there these they this those through under what when where which while will with without your
    google ads says said adds gets launches launch update updates new now how why the for are you can
    über eine einen einem einer nicht noch oder sich sind wird werden wurde zum zur beim bei dass mehr
    neue neuer neues jetzt diese dieser dieses wie was mit von für und der die das den dem des auf aus
""".split())
NEWS_SEARCH = "https://news.google.com/rss/search?q={q}+when:{days}d&{locale}"
# Google-News-Ausgaben, in denen jeder Suchbegriff gesucht wird: USA, UK, Irland und DACH
LOCALES = {
    "US": "hl=en-US&gl=US&ceid=US:en",
    "UK": "hl=en-GB&gl=GB&ceid=GB:en",
    "IE": "hl=en-IE&gl=IE&ceid=IE:en",
    "DE": "hl=de&gl=DE&ceid=DE:de",
    "AT": "hl=de&gl=AT&ceid=AT:de",
    "CH": "hl=de&gl=CH&ceid=CH:de",
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


def search_sources(config: dict) -> list[dict]:
    """Macht aus jedem Suchbegriff eine Google-News-Suche, die wie eine Quelle abgerufen wird."""
    days = int(config.get("zeitraum_tage", 7))
    sources = []
    for term in config.get("begriffe") or []:
        # Jeder Begriff läuft in allen Ausgaben (US, UK, IE, DE, AT, CH); doppelte Treffer werden zusammengeführt
        for lang, locale in LOCALES.items():
            sources.append({
                "name": f"Suche: {term} ({lang})",
                "url": NEWS_SEARCH.format(q=quote_plus(term), days=days, locale=locale),
                "kategorie": DISCOVER,
                "suche": term,
            })
    return sources


def passes_rules(rules: dict, title: str, link: str) -> bool:
    """Regeln für alle Quellen gleich: Mindestlänge des Titels, Stellenanzeigen, ausgeschlossene Begriffe.
    Die Themen-Regel (mindest_gewicht) greift später, nach der Themenzuordnung."""
    if len(title.split()) < int(rules.get("min_woerter") or 0):
        return False
    if rules.get("stellenanzeigen_ausblenden", True) and (JOB_TITLE.search(title) or JOB_LINK.search(link)):
        return False
    return not any(t.lower() in title.lower() for t in rules.get("ausschliessen") or [])


def parse_source(source: dict, seen_at: str, rules: dict) -> list[dict]:
    feed = feedparser.parse(fetch(source["url"]))
    if not feed.entries:
        if source.get("suche") and not feed.get("bozo"):
            return []  # Suche ohne Treffer in dieser Ausgabe ist kein Fehler
        reason = feed.get("bozo_exception") or "keine Einträge im Feed"
        raise ValueError(str(reason))

    items = []
    for entry in feed.entries:
        link = entry.get("link")
        title = strip_html(entry.get("title", ""))
        if not link or not title:
            continue
        # Aggregatoren (z.B. Google News) nennen den Publisher separat und hängen
        # " - Quellname" an den Titel
        origin = entry.get("source") or {}
        publisher = origin.get("title")
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3]
        teaser = snippet(entry.get("summary") or (entry.get("content") or [{}])[0].get("value", ""))
        if not passes_rules(rules, title, link):
            continue
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


def load_previous(location: str | None) -> dict:
    """Bisheriger Stand (items.json): Beiträge und das zuletzt geschriebene Briefing."""
    if not location:
        return {}
    try:
        if re.match(r"^https?://", location):
            raw = fetch(location)
        else:
            path = Path(location)
            if not path.exists():
                return {}
            raw = path.read_bytes()
        return json.loads(raw)
    except Exception as exc:  # erster Lauf oder Seite noch nicht online
        print(f"Hinweis: bisheriger Bestand nicht geladen ({exc})", file=sys.stderr)
        return {}


def merge(previous: list[dict], fresh: list[dict], active_feeds: set[str], rules: dict) -> list[dict]:
    by_id: dict[str, dict] = {}
    for item in previous:
        # Bestand nur von aktiven Quellen und nach den aktuellen Regeln (geänderte Regeln wirken sofort)
        if item.get("feed", item.get("source")) in active_feeds and passes_rules(rules, item["title"], item["link"]):
            by_id[item["id"]] = item
    for item in fresh:
        old = by_id.get(item["id"])
        if old:
            item["first_seen"] = old.get("first_seen", item["first_seen"])
            if not item["image"]:
                item["image"] = old.get("image")
                item["image_checked"] = old.get("image_checked", False)
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


def tag_topics(items: list[dict], topics: list[dict]) -> None:
    """Ordnet jedem Artikel die Themenbereiche zu, deren Stichwörter im Titel oder Anriss vorkommen."""
    for item in items:
        text = f" {item['title']} {item['snippet']} ".lower()
        item["topics"] = [t["name"] for t in topics if any(w.lower() in text for w in t["stichwoerter"])]


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
            "articles": [{"title": h["title"], "link": h["link"], "published": h["published"]}
                         for h in sorted(hits, key=lambda h: h["published"], reverse=True)[:5]],
        })
    rows.sort(key=lambda r: (-r["count"], r["domain"]))
    return rows


def add_cover_images(items: list[dict]) -> None:
    """Holt für Beiträge ohne Bild das Titelbild (og:image) der Artikelseite, einmal pro Beitrag."""
    todo = [i for i in items if not i.get("image") and not i.get("image_checked")
            and i["category"] != DISCOVER and "news.google.com" not in i["link"] and "reddit.com" not in i["link"]]
    for item in todo[:OG_IMAGE_LIMIT]:
        item["image_checked"] = True
        try:
            req = urllib.request.Request(item["link"], headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=8) as resp:
                head = resp.read(200_000).decode("utf-8", "ignore")
        except Exception:
            continue
        match = OG_IMAGE.search(head)
        url = html.unescape(next((g for g in match.groups() if g), "")) if match else ""
        if url.startswith("http"):
            item["image"] = url


def mark_studies(items: list[dict]) -> None:
    for item in items:
        text = f"{item['title']} {item['snippet']}".lower()
        item["study"] = item["category"] == STUDIES or (
            item["category"] not in (DISCOVER, COMMUNITY) and bool(STUDY_PATTERN.search(text))
        )


def local_date(item: dict):
    return datetime.fromisoformat(item["published"]).astimezone(TZ).date()


def pick_articles(items: list[dict], n: int = 3) -> list[dict]:
    """Bevorzugt offizielle Quellen, dann je Quelle nur einen Beitrag, neueste zuerst."""
    ranked = sorted(items, key=lambda i: (i["category"] == "Offiziell", i["published"]), reverse=True)
    picked, sources = [], set()
    for item in ranked:
        if item["source"] not in sources:
            sources.add(item["source"])
            picked.append(item)
    return picked[:n]


def day_topics(items: list[dict], weights: dict[str, int], day) -> dict:
    """Wichtigste Themen eines Tages: Beiträge × Quellen, gewichtet mit der Themen-Wichtigkeit."""
    pool = [i for i in items if i["category"] not in (DISCOVER, COMMUNITY) and local_date(i) == day]
    rows = []
    for name, weight in weights.items():
        hits = [i for i in pool if name in i["topics"]]
        if not hits:
            continue
        sources = {i["source"] for i in hits}
        rows.append({
            "topic": name, "weight": weight, "count": len(hits), "sources": len(sources),
            "score": weight * (len(hits) + len(sources)), "articles": pick_articles(hits),
        })
    rows.sort(key=lambda r: -r["score"])
    return {"date": day.isoformat(), "total": len(pool), "topics": rows[:5]}


def title_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-zäöüß0-9][a-zäöüß0-9\-]+", title.lower())
    return {w for w in words if len(w) >= 4 and w not in STOPWORDS}


def story_clusters(items: list[dict], weights: dict[str, int]) -> list[dict]:
    """Geschichten, über die mehrere feste Quellen in den letzten Tagen berichten (Titel-Ähnlichkeit)."""
    cutoff = now_utc() - timedelta(days=TREND_DAYS)
    pool = [i for i in items if i["category"] not in (DISCOVER, COMMUNITY)
            and datetime.fromisoformat(i["published"]) >= cutoff]
    tokens = [title_tokens(i["title"]) for i in pool]
    parent = list(range(len(pool)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in range(len(pool)):
        for b in range(a + 1, len(pool)):
            shared = tokens[a] & tokens[b]
            if len(shared) >= 2 and len(shared) / len(tokens[a] | tokens[b]) >= 0.3:
                parent[find(a)] = find(b)

    groups: dict[int, list[dict]] = {}
    for idx, item in enumerate(pool):
        groups.setdefault(find(idx), []).append(item)
    clusters = []
    for members in groups.values():
        sources = {i["source"] for i in members}
        if len(sources) < 2:
            continue
        topic_counts = Counter(t for i in members for t in i["topics"])
        weight = max((weights.get(t, 1) for t in topic_counts), default=1)
        articles = pick_articles(members, n=5)
        clusters.append({
            "title": articles[0]["title"], "sources": len(sources), "weight": weight,
            "topics": [t for t, _ in topic_counts.most_common(2)],
            "latest": max(i["published"] for i in members), "articles": articles,
        })
    clusters.sort(key=lambda c: (c["sources"] * c["weight"], c["latest"]), reverse=True)
    return clusters[:6]


# Allgemeine Wörter, die als Trend nichts aussagen
GENERIC = set("""
    advertisers advertiser advertising marketing marketers search campaigns campaign data report reports
    brands brand users user business businesses update updates feature features tool tools test tests
    study guide tips strategy strategies performance results growth companies company year week today
    first best better ways things people help helps make makes using used get gets announces announced
    launches launched introduces rolls rolling expands adds says shows find finds more less don't can't
    werbung marketing unternehmen kampagne kampagnen neue neues studie zeigt mehr jahr
    a an the of to in on at by as it its is be are was vs or if so up no us we our you how why what who
    ein eine der die das und im am zu von mit für ist""".split())


def trending_terms(items: list[dict], limit: int = 6) -> list[dict]:
    """Konkrete Begriffe (1–3 Wörter) aus den Titeln, die in den letzten Tagen bei mehreren Quellen
    auftauchen und deutlich häufiger sind als im 30-Tage-Schnitt."""
    now = now_utc()
    pool = [i for i in items if i["category"] not in (DISCOVER, COMMUNITY)]
    stats: dict[str, dict] = {}
    for item in pool:
        words = re.findall(r"[A-Za-zÄÖÜäöüß0-9][\w’'\-]*", item["title"])
        recent = (now - datetime.fromisoformat(item["published"])).days < TREND_DAYS
        seen: set[str] = set()
        for n in (1, 2, 3):
            for k in range(len(words) - n + 1):
                gram = words[k:k + n]
                low = [w.lower().strip("’'") for w in gram]
                if low[0] in STOPWORDS | GENERIC or low[-1] in STOPWORDS | GENERIC:
                    continue
                if any(w.isdigit() for w in low):  # lose Zahlen ("GPT-6 1 Terra") ergeben keinen Begriff
                    continue
                key = " ".join(low)
                if key in seen:
                    continue
                seen.add(key)
                row = stats.setdefault(key, {"recent": 0, "before": 0, "sources": set(), "forms": Counter()})
                row["forms"][" ".join(gram)] += 1
                if recent:
                    row["recent"] += 1
                    row["sources"].add(item["source"])
                else:
                    row["before"] += 1

    candidates = []
    for key, row in stats.items():
        # Einzelwörter sind unschärfer ("traffic", "pages") und brauchen deshalb drei Quellen
        min_sources = 3 if " " not in key else 2
        if row["recent"] < 2 or len(row["sources"]) < min_sources or len(key) < 4:
            continue
        baseline = row["before"] / (MAX_AGE_DAYS - TREND_DAYS)
        ratio = (row["recent"] / TREND_DAYS) / max(baseline, 0.15)
        if ratio < 2:
            continue
        candidates.append({"key": key, "term": row["forms"].most_common(1)[0][0], "count": row["recent"],
                           "sources": len(row["sources"]), "ratio": round(ratio, 1),
                           "score": len(row["sources"]) * ratio * (1 + 0.3 * key.count(" "))})
    candidates.sort(key=lambda c: -c["score"])
    picked: list[dict] = []
    for cand in candidates:
        # Kein Begriff, der in einem schon gewählten steckt oder ihn enthält ("AI Max" vs. "Max")
        if any(cand["key"] in p["key"] or p["key"] in cand["key"] for p in picked):
            continue
        picked.append(cand)
        if len(picked) == limit:
            break
    return picked


WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
MODELS_URL = "https://models.github.ai/inference/chat/completions"
MODEL = "openai/gpt-4.1-mini"


def german_date(day) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day.day}. {MONTHS[day.month - 1]}"


def fallback_summary(day, pool: list[dict], topics: list[dict]) -> str:
    """Zusammengesetzter Text, wenn keine KI verfügbar ist."""
    if not pool:
        return f"Am {german_date(day)} sind in deinen Quellen keine passenden Beiträge erschienen."
    sources = len({i["source"] for i in pool})
    text = f"Am {german_date(day)} erschienen {len(pool)} Beiträge aus {sources} Quellen."
    if topics:
        lead = topics[0]
        top = lead["articles"][0]
        text += f" Am meisten Thema war {lead['topic']} ({lead['count']} Beiträge), etwa «{top['title']}» ({top['source']})."
        rest = [f"{t['topic']} ({t['count']})" for t in topics[1:4]]
        if rest:
            text += " Ausserdem: " + ", ".join(rest[:-1]) + (" und " if len(rest) > 1 else "") + rest[-1] + "."
    return text


def ai_briefing(day, pool: list[dict]) -> tuple[dict | None, str]:
    """Briefing über GitHub Models (gratis in GitHub Actions): Lauftext plus die drei wichtigsten
    Beiträge mit je einem Satz, warum sie relevant sind. Gibt (Ergebnis, Hinweis) zurück; der Hinweis
    erklärt, warum es kein KI-Ergebnis gab."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None, "kein GITHUB_TOKEN (lokaler Lauf)"
    if not pool:
        return None, "keine Beiträge am Vortag"
    candidates = pool[:40]
    lines = [f"[{n}] {i['title']} — {i['snippet'][:220]} ({i['source']}; {i['category']})"
             for n, i in enumerate(candidates, 1)]
    payload = {
        "model": MODEL,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": (
                "Du schreibst das Morgen-Briefing für Paid-Search-Spezialisten in einer Schweizer Agentur. "
                "Schreibe Schweizer Hochdeutsch (ss statt ß), sachlich, konkret, ohne Floskeln. "
                "Verwende nur, was in den Beiträgen steht; erfinde nichts und nenne keine Zahlen, die dort nicht stehen. "
                "Antworte als JSON: {\"text\": \"3 bis 4 Sätze Fliesstext: was ist passiert, wichtigste Entwicklung zuerst\", "
                "\"punkte\": [{\"nr\": Nummer des Beitrags, \"warum\": \"ein Satz, was das für Google-Ads-, "
                "Microsoft-Ads- oder Shopping-Kampagnen bedeutet oder worauf man achten sollte\"}]}. "
                "Wähle genau 3 Punkte, bevorzugt offizielle Ankündigungen und neue Funktionen oder Änderungen.")},
            {"role": "user", "content": f"Beiträge vom {german_date(day)}:\n" + "\n".join(lines)},
        ],
    }
    req = urllib.request.Request(MODELS_URL, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json",
    })
    raw = b""
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
        content = json.loads(raw)["choices"][0]["message"]["content"] or ""
        answer = parse_json_answer(content)
        points = []
        for point in answer.get("punkte") or []:
            nr = int(point.get("nr", 0))
            if 1 <= nr <= len(candidates):
                points.append({**article_ref(candidates[nr - 1]), "why": str(point.get("warum", "")).replace("ß", "ss")})
        text = str(answer.get("text", "")).replace("ß", "ss").strip()
        if text:
            return {"text": text, "points": points[:3]}, ""
        reason = "leere Antwort"
    except urllib.error.HTTPError as exc:
        reason = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')[:300]}"
    except Exception as exc:
        snippet = raw.decode("utf-8", "ignore")[:200].replace("\n", " ")
        reason = f"{type(exc).__name__}: {str(exc)[:150]} | Antwort: {snippet or '(leer)'}"
    print(f"Hinweis: KI-Briefing nicht verfügbar ({reason})", file=sys.stderr)
    return None, reason


def parse_json_answer(content: str) -> dict:
    """Liest das JSON aus der Modellantwort, auch wenn es in einem Code-Block oder Text steht."""
    content = content.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.S)
    if fence:
        content = fence.group(1)
    elif not content.startswith("{"):
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end > start:
            content = content[start:end + 1]
    return json.loads(content)


def article_ref(item: dict) -> dict:
    return {k: item[k] for k in ("title", "link", "source", "domain", "category")}


def fallback_points(pool: list[dict]) -> list[dict]:
    """Ohne KI: die drei wichtigsten Beiträge (offizielle zuerst, je Quelle einer) mit ihrem Anriss."""
    points = []
    for item in pick_articles(pool, n=3):
        teaser = item["snippet"]
        if len(teaser) > 160:
            teaser = teaser[:160].rsplit(" ", 1)[0] + " …"
        points.append({**article_ref(item), "why": teaser})
    return points


BRIEFING_DAYS = 62      # Briefings so lange aufbewahren (deckt den Vormonat ab)
AI_BACKFILL = 2         # ältere Tage ohne KI-Text, die pro Lauf nachgeholt werden


def brief_refs(items: list[dict], n: int) -> list[dict]:
    return [{**article_ref(i), "why": ""} for i in items[:n]]


def build_day(day, items: list[dict], weights: dict[str, int], use_ai: bool) -> tuple[dict | None, str]:
    """Briefing eines Tages aus den Beiträgen dieses Tages; None, wenn es keine gibt."""
    pool = [i for i in items if i["category"] not in (DISCOVER, COMMUNITY) and local_date(i) == day]
    if not pool:
        return None, ""
    pool.sort(key=lambda i: (i.get("weight", 0), i["category"] == "Offiziell", i["published"]), reverse=True)
    topics = day_topics(items, weights, day)["topics"]
    result, note = ai_briefing(day, pool) if use_ai else (None, "")
    by = "ki" if result else "auto"
    result = result or {"text": fallback_summary(day, pool, topics), "points": fallback_points(pool)}
    shown = {pt["link"] for pt in result["points"]}
    studies = [i for i in pool if i.get("study") and i["link"] not in shown]
    community = sorted((i for i in items if i["category"] == COMMUNITY and local_date(i) == day),
                       key=lambda i: (i.get("weight", 0), i["published"]), reverse=True)
    return {
        "date": day.isoformat(), "text": result["text"], "points": result["points"], "by": by,
        "total": len(pool), "topics": [{"topic": t["topic"], "count": t["count"]} for t in topics],
        "studies": brief_refs(studies, 3), "community": brief_refs(community, 3),
    }, note


def build_briefings(items: list[dict], weights: dict[str, int], previous: dict) -> tuple[list[dict], str]:
    """Ein Briefing pro Tag, neueste zuerst. Gespeicherte Briefings bleiben BRIEFING_DAYS Tage erhalten,
    auch wenn ihre Beiträge schon aus dem 30-Tage-Fenster gefallen sind. Die KI schreibt den Vortag und
    holt pro Lauf AI_BACKFILL ältere Tage nach; ein KI-Text wird nie neu erzeugt."""
    today = datetime.now(TZ).date()
    stored = {b["date"]: b for b in previous.get("briefings") or []}
    legacy = previous.get("briefing") or {}
    if legacy.get("date") and legacy["date"] not in stored and legacy.get("by") == "ki":
        stored[legacy["date"]] = legacy
    has_token = bool(os.environ.get("GITHUB_TOKEN"))
    backfill, note = AI_BACKFILL, ""
    result = {}
    for offset in range(1, MAX_AGE_DAYS + 1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        old = stored.get(key)
        if old and old.get("by") == "ki":
            result[key] = old
            continue
        use_ai = has_token and (offset == 1 or backfill > 0)
        entry, reason = build_day(day, items, weights, use_ai)
        if offset == 1:
            note = reason
        if use_ai and offset > 1:
            backfill -= 1
        if entry:
            result[key] = entry
        elif old:
            result[key] = old
    cutoff = (today - timedelta(days=BRIEFING_DAYS)).isoformat()
    for key, old in stored.items():
        if key not in result and key >= cutoff:
            result[key] = old
    briefings = [result[k] for k in sorted(result, reverse=True)]
    for b in briefings:
        day = datetime.fromisoformat(b["date"]).date()
        b["label"] = german_date(day)
        b["weekday"] = WEEKDAYS[day.weekday()]
        b["daymonth"] = f"{day.day}. {MONTHS[day.month - 1]}"
        b["relative"] = {1: "Gestern", 2: "Vorgestern"}.get((today - day).days, "")
        b["month"] = f"{MONTHS[int(b['date'][5:7]) - 1]} {b['date'][:4]}"
    return briefings, note


def community_topics(items: list[dict]) -> list[tuple[str, int]]:
    cutoff = now_utc() - timedelta(days=7)
    return Counter(
        t for i in items if i["category"] == COMMUNITY and datetime.fromisoformat(i["published"]) >= cutoff
        for t in i["topics"]
    ).most_common(6)


def source_stats(sources: list[dict], items: list[dict]) -> list[dict]:
    rows = []
    for source in sources:
        hits = [i for i in items if i.get("feed") == source["name"]]
        rows.append({
            "name": source["name"], "category": source["kategorie"], "count": len(hits),
            "topic_share": round(100 * sum(1 for i in hits if i["topics"]) / len(hits)) if hits else None,
            "studies": sum(1 for i in hits if i.get("study")),
            "latest": max((i["published"] for i in hits), default=None),
            "host": domain_of(source["url"]),
            "domain": Counter(i["domain"] for i in hits).most_common(1)[0][0] if hits else domain_of(source["url"]),
        })
    return rows


def repo_slug() -> str:
    """owner/repo für Links auf GitHub: in Actions aus der Umgebung, lokal aus dem Git-Remote."""
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    try:
        remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True).stdout
    except OSError:
        return ""
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?\s*$", remote)
    return match.group(1) if match else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", help="URL oder Pfad zur bisherigen items.json")
    parser.add_argument("--out", default="site")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))
    sources = [s for s in config.get("quellen") or [] if s.get("aktiv", True) and s.get("url")]
    searches = config.get("suchen") or {}
    rules = config.get("regeln") or {}
    feeds = sources + search_sources(searches)

    seen_at = now_utc().isoformat()
    fresh, errors = [], []
    last_host = None
    for source in feeds:
        host = domain_of(source["url"])
        if host == last_host and "reddit.com" in host:
            time.sleep(8)  # Reddit drosselt schnelle Folgeabrufe (HTTP 429)
        last_host = host
        try:
            items = parse_source(source, seen_at, rules)
            fresh.extend(items)
            print(f"ok    {source['name']}: {len(items)} Artikel")
        except Exception as exc:
            errors.append({"source": source["name"], "error": str(exc)[:160]})
            print(f"FEHLER {source['name']}: {exc}", file=sys.stderr)

    previous = load_previous(args.previous)
    items = merge(previous.get("items", []), fresh, {f["name"] for f in feeds}, rules)
    items = filter_discoveries(items, {d.lower() for d in searches.get("ignorieren") or []})
    topics = config.get("themen") or []
    tag_topics(items, topics)
    weights = {t["name"]: int(t.get("gewicht", 1)) for t in topics}
    for item in items:
        item["weight"] = max((weights.get(t, 1) for t in item["topics"]), default=0)
    # Themen-Regel für alle Quellen: nur Beiträge, die ein Thema mit mindestens diesem Gewicht treffen
    items = [i for i in items if i["weight"] >= int(rules.get("mindest_gewicht") or 0)]
    mark_studies(items)
    add_cover_images(items)

    briefings, briefing_note = build_briefings(items, weights, previous)

    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    generated = now_utc().isoformat()
    (out / "items.json").write_text(
        json.dumps({"generated": generated, "briefing_note": briefing_note,
                    "briefings": [{k: v for k, v in b.items() if k not in ("label", "month", "weekday", "daymonth", "relative")} for b in briefings],
                    "items": items},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    shutil.copytree(ROOT / "static", out, dirs_exist_ok=True)

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape())
    shown = [i for i in items if i["category"] != DISCOVER]  # Entdecken erscheint nur als Vorschlagsliste
    repo = repo_slug()
    page = env.get_template("index.html.j2").render(
        items=shown,
        unknown=unknown_sources(items),
        topics=[t["name"] for t in topics],
        topic_defs=topics,
        search_defs=searches.get("begriffe") or [],
        weights=weights,
        briefings=briefings,
        briefing_note=briefing_note,
        stories=story_clusters(items, weights),
        trends=trending_terms(items),
        community=community_topics(items),
        stats=source_stats(sources, items),
        topic_counts=Counter(t for i in shown for t in i["topics"]),
        errors=errors,
        generated=generated,
        max_age_days=MAX_AGE_DAYS,
        repo=repo,
        site_url=f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/" if "/" in repo else "",
        categories=[c for c in config.get("kategorien", []) if c != DISCOVER],
        rules=rules,
        password_hash=(config.get("zugang") or {}).get("passwort_sha256", ""),
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"{len(items)} Artikel, {len(errors)} fehlerhafte Quellen → {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
