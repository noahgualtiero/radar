"""Nimmt eine Quelle aus einem GitHub-Issue in sources.yaml auf.

Das Formular «Quelle aufnehmen» in den Einstellungen der Seite öffnet ein Issue mit dem
Titel «Quelle: <URL>» und den Zeilen «url:», «kategorie:» und «name:» im Text. Die Action
add-source.yml ruft dieses Skript mit ISSUE_TITLE und ISSUE_BODY auf. Es sucht den Feed,
hängt den Eintrag an die Quellenliste an und schreibt das Ergebnis nach $GITHUB_OUTPUT.

Lokal:  ISSUE_TITLE="Quelle: https://example.com" ISSUE_BODY="kategorie: News" python add_source.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

from find_feed import discover
from build import domain_of

ROOT = Path(__file__).parent
SOURCES = ROOT / "sources.yaml"


def field(body: str, key: str) -> str:
    match = re.search(rf"^\s*{key}\s*:\s*(.+?)\s*$", body, re.I | re.M)
    return match.group(1).strip() if match else ""


def output(**values: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in values.items()]
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> int:
    title = os.environ.get("ISSUE_TITLE", "")
    body = os.environ.get("ISSUE_BODY", "")
    url = field(body, "url") or title.split(":", 1)[-1].strip()
    if not re.match(r"^https?://", url):
        output(status="fehler", message=f"Keine gültige URL gefunden ({url!r}).")
        return 0

    config = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    categories = config.get("kategorien") or []
    category = field(body, "kategorie") or "News"
    if category not in categories:
        category = "News"

    found = discover(url)
    if not found:
        output(status="fehler", message=f"Kein Feed gefunden für {domain_of(url)}. Alternative: RSS.app oder Google News mit site:{domain_of(url)}.")
        return 0
    feed_url, feed_title, count = found

    known = {domain_of(s.get("url", "")) for s in config.get("quellen") or []}
    if feed_url in {s.get("url") for s in config.get("quellen") or []} or domain_of(feed_url) in known:
        output(status="vorhanden", message=f"{domain_of(feed_url)} ist bereits eine Quelle.")
        return 0

    name = field(body, "name") or feed_title.strip() or domain_of(url)
    name = name.replace('"', "'")
    entry = f'\n  - name: "{name}"\n    url: {feed_url}\n    kategorie: {category}\n'
    SOURCES.write_text(SOURCES.read_text(encoding="utf-8").rstrip("\n") + "\n" + entry, encoding="utf-8")
    yaml.safe_load(SOURCES.read_text(encoding="utf-8"))  # bricht ab, falls die Datei kaputt wäre
    output(status="ok", message=f"Aufgenommen: {name} ({category}), Feed {feed_url} mit {count} Einträgen.", name=name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
