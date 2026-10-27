"""Übernimmt eine Änderung aus einem GitHub-Issue in sources.yaml.

Die Formulare in den Einstellungen der Seite öffnen ein Issue, dessen Titel die Art der
Änderung nennt und dessen Text die Felder als «schlüssel: wert» enthält:

    Quelle: <URL>              url, kategorie, name        Feed suchen und aufnehmen
    Quelle entfernen: <Name>   name                        Quelle deaktivieren (aktiv: false)
    Thema: <Name>              name, gewicht, stichwoerter, entfernen
    Suchbegriff: <Begriff>     begriff, sprache, entfernen

Die Action settings.yml ruft das Skript mit ISSUE_TITLE und ISSUE_BODY auf. Kommentare und
Verweise (*paid, *marketing) in sources.yaml bleiben erhalten. Das Ergebnis geht nach
$GITHUB_OUTPUT (status, message, summary).

Lokal:  ISSUE_TITLE="Thema: YouTube" ISSUE_BODY="gewicht: 1" python apply_issue.py
"""

from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from build import LOCALES, domain_of
from find_feed import discover

SOURCES = Path(__file__).parent / "sources.yaml"


def field(body: str, key: str) -> str:
    match = re.search(rf"^\s*{key}\s*:[ \t]*(.*?)\s*$", body, re.I | re.M)
    return match.group(1).strip() if match else ""


def flag(body: str, key: str) -> bool:
    return field(body, key).lower() in ("ja", "yes", "true", "1")


class Result(Exception):
    def __init__(self, status: str, message: str, summary: str = ""):
        super().__init__(message)
        self.status, self.message, self.summary = status, message, summary


def add_source(data, body: str, title_value: str) -> None:
    url = field(body, "url") or title_value
    if not re.match(r"^https?://", url):
        raise Result("fehler", f"Keine gültige URL gefunden ({url!r}).")
    category = field(body, "kategorie") or "News"
    if category not in list(data.get("kategorien") or []):
        category = "News"
    found = discover(url)
    if not found:
        raise Result("fehler", f"Kein Feed gefunden für {domain_of(url)}. Alternative: RSS.app oder Google News mit site:{domain_of(url)}.")
    feed_url, feed_title, count = found
    for source in data["quellen"]:
        if source.get("url") == feed_url or (source.get("url") and domain_of(source["url"]) == domain_of(feed_url)):
            if source.get("aktiv") is False:
                del source["aktiv"]
                raise Result("ok", f"{source['name']} war deaktiviert und ist wieder aktiv.", f"Quelle reaktiviert: {source['name']}")
            raise Result("vorhanden", f"{domain_of(feed_url)} ist bereits eine Quelle ({source['name']}).")
    name = field(body, "name") or feed_title.strip() or domain_of(url)
    entry = CommentedMap(name=name, url=feed_url, kategorie=category)
    data["quellen"].append(entry)
    raise Result("ok", f"Aufgenommen: {name} ({category}), Feed {feed_url} mit {count} Einträgen.", f"Quelle aufgenommen: {name}")


def remove_source(data, body: str, title_value: str) -> None:
    name = field(body, "name") or title_value
    for source in data["quellen"]:
        if source.get("name") == name:
            source["aktiv"] = False
            raise Result("ok", f"{name} ist deaktiviert (aktiv: false). Erneut aufnehmen macht sie wieder aktiv.", f"Quelle deaktiviert: {name}")
    raise Result("fehler", f"Keine Quelle mit dem Namen {name!r} gefunden.")


def edit_topic(data, body: str, title_value: str) -> None:
    name = field(body, "name") or title_value
    if not name:
        raise Result("fehler", "Kein Themenname angegeben.")
    topics = data["themen"]
    existing = next((t for t in topics if t["name"].lower() == name.lower()), None)
    if flag(body, "entfernen"):
        if not existing:
            raise Result("fehler", f"Thema {name!r} gibt es nicht.")
        topics.remove(existing)
        raise Result("ok", f"Thema {existing['name']} entfernt.", f"Thema entfernt: {existing['name']}")
    words = [w.strip() for w in re.split(r"[,\n;]", field(body, "stichwoerter")) if w.strip()]
    raw_weight = field(body, "gewicht")
    weight = int(raw_weight) if raw_weight in ("1", "2", "3") else None
    if existing:
        if weight:
            existing["gewicht"] = weight
        if words:
            existing["stichwoerter"] = flow(words)
        raise Result("ok", f"Thema {existing['name']} aktualisiert: Gewicht {existing.get('gewicht', 1)}, {len(existing['stichwoerter'])} Stichwörter.",
                     f"Thema aktualisiert: {existing['name']}")
    if not words:
        raise Result("fehler", f"Für das neue Thema {name!r} fehlen Stichwörter.")
    topics.append(CommentedMap(name=name, gewicht=weight or 1, stichwoerter=flow(words)))
    raise Result("ok", f"Thema {name} angelegt: Gewicht {weight or 1}, {len(words)} Stichwörter.", f"Thema angelegt: {name}")


def edit_search(data, body: str, title_value: str) -> None:
    term = field(body, "begriff") or title_value
    if not term:
        raise Result("fehler", "Kein Suchbegriff angegeben.")
    lang = field(body, "sprache") or "en"
    if lang not in LOCALES:
        lang = "en"
    terms = data["suchen"]["begriffe"]
    existing = next((t for t in terms if t["begriff"] == term and t.get("sprache", "en") == lang), None)
    if flag(body, "entfernen"):
        if not existing:
            raise Result("fehler", f"Suchbegriff {term!r} ({lang}) gibt es nicht.")
        terms.remove(existing)
        raise Result("ok", f"Suchbegriff {term} ({lang}) entfernt.", f"Suchbegriff entfernt: {term}")
    if existing:
        raise Result("vorhanden", f"Suchbegriff {term} ({lang}) gibt es schon.")
    entry = CommentedMap(begriff=term, sprache=lang)
    entry.fa.set_flow_style()
    terms.append(entry)
    raise Result("ok", f"Suchbegriff {term} ({lang}) hinzugefügt.", f"Suchbegriff hinzugefügt: {term}")


def flow(words: list[str]) -> CommentedSeq:
    seq = CommentedSeq(words)
    seq.fa.set_flow_style()
    return seq


ACTIONS = [
    ("quelle entfernen", remove_source),
    ("quelle", add_source),
    ("thema", edit_topic),
    ("suchbegriff", edit_search),
]


def output(status: str, message: str, summary: str = "") -> None:
    lines = [f"status={status}", f"message={message}", f"summary={summary}"]
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> int:
    title = os.environ.get("ISSUE_TITLE", "").strip()
    body = os.environ.get("ISSUE_BODY", "")
    prefix, _, value = title.partition(":")
    handler = next((fn for key, fn in ACTIONS if prefix.strip().lower() == key), None)
    if not handler:
        output("fehler", f"Unbekannte Änderung: {title!r}")
        return 0

    rt = YAML()
    rt.preserve_quotes = True
    rt.width = 4096
    rt.indent(mapping=2, sequence=4, offset=2)
    data = rt.load(SOURCES.read_text(encoding="utf-8"))
    try:
        handler(data, body, value.strip())
    except Result as result:
        if result.status == "ok":
            buf = io.StringIO()
            rt.dump(data, buf)
            yaml.safe_load(buf.getvalue())  # bricht ab, falls die Datei kaputt wäre
            SOURCES.write_text(buf.getvalue(), encoding="utf-8")
        output(result.status, result.message, result.summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
