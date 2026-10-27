# Paid Search Newsfeed

Ein Newsfeed im Stil von LinkedIn mit Neuigkeiten aus selbst festgelegten Paid-Search-Quellen.
Läuft kostenlos über **GitHub Actions** (alle 3 Stunden) und **GitHub Pages**. Alle Quellen
sind gratis: offene RSS-Feeds und Google News.

## Was die Seite zeigt

| Tab | Inhalt |
|---|---|
| **Feed** | Beiträge der festen Quellen, oben «Gestern wichtig» und «Trends» |
| **Studien** | Beiträge aus Studien-Quellen (Optmyzr, McKinsey, BCG, IAB …) und alle Beiträge fester Quellen, die nach Studie, Umfrage, Benchmark oder Report klingen |
| **Community** | Reddit r/PPC und r/googleads, oben die häufigsten Themen der Woche |
| **Entdecken** | Google-News-Treffer der Suchbegriffe von Seiten, die noch keine feste Quelle sind |
| **Gemerkt** | mit «Merken» gespeicherte Beiträge und von Hand abgelegte Links |
| **Blog-Ideen** | mit «Blog» vorgemerkte Beiträge als Themen für den eigenen Blog |
| **Quellen** | Auswertung pro Quelle und Vorschläge für neue Quellen |

**Gestern wichtig:** Die Themen des Vortages, sortiert nach *Beiträge + Quellen × Gewicht des
Themas*, je mit den wichtigsten Artikeln (offizielle Quellen zuerst, je Quelle einer).

**Trends:** Geschichten, über die mindestens zwei feste Quellen in den letzten 3 Tagen
berichten (erkannt über ähnliche Titel). Dazu **steigende Themen**: Themen, die in den letzten
3 Tagen mindestens 1,5-mal so oft vorkommen wie im 30-Tage-Schnitt.

**Reihenfolge im Feed:** neueste zuerst. Wichtige Themen rücken leicht nach oben (6 Stunden
pro Gewichtsstufe), bewertete Quellen deutlich (±2 Tage).

Die Seite hat `noindex` gesetzt und sperrt Suchmaschinen per `robots.txt` aus.

## Bedienung

Unter jedem Beitrag:

- **Mehr / Weniger** bewertet die *Quelle*. «Mehr» rückt alle Beiträge dieser Quelle um zwei
  Tage nach oben, «Weniger» um zwei Tage nach unten und blasst sie ab. Erneutes Klicken hebt
  die Bewertung auf. Der Filter «Abgewertete Quellen ausblenden» blendet sie ganz aus.
- **Merken** legt den Beitrag unter «Gemerkt» ab.
- **Blog** legt ihn unter «Blog-Ideen» ab.
- **Lesen** öffnet das Original.
- **#Thema** filtert auf diesen Themenbereich.

In «Gemerkt» und «Blog-Ideen» lassen sich auch **Links von anderswo ablegen** (Link, Titel,
Thema). «Liste als Text kopieren» gibt die Liste mit Links für Mail oder Dokument aus.

Bewertungen, Gemerkt und Blog-Ideen werden **im Browser** gespeichert, also pro Gerät und
Browser. Wer die Browserdaten löscht, verliert sie.

## Aufbau

| Datei | Zweck |
|---|---|
| `sources.yaml` | Quellen, Themenkatalog, Suchbegriffe – **alles Inhaltliche wird hier gepflegt** |
| `build.py` | Holt alle Feeds, entfernt Duplikate, ordnet Themen zu, berechnet Überblick und Trends, baut die Seite |
| `find_feed.py` | Findet den Feed einer Seite und gibt den Eintrag für `sources.yaml` aus |
| `templates/index.html.j2` | Vorlage der Webseite |
| `.github/workflows/build.yml` | Automatischer Lauf und Veröffentlichung |

## Quelle hinzufügen

1. Feed finden:

   ```bash
   .venv/bin/python find_feed.py https://example.com/ein-artikel Studien
   ```

   Das Skript prüft die Feed-Links der Seite und übliche Pfade (`/feed/`, `/rss.xml` …) und
   gibt den fertigen Eintrag aus. Findet es nichts: RSS.app verwenden oder eine Google-News-Suche
   mit `site:domain` (Beispiel BCG in `sources.yaml`).
2. Eintrag in `sources.yaml` unter `quellen:` einfügen. `kategorie` ist eine der Kategorien
   oben in der Datei.
3. Speichern und committen. Die Seite wird automatisch neu gebaut.

Weitere Felder pro Quelle:

- `nur_begriffe: *paid` – nur Beiträge mit Paid-Search-Bezug (für breite Medien wie t3n)
- `nur_begriffe: *marketing` – nur Marketing-Themen (für Beratungen wie McKinsey)
- `aktiv: false` – Quelle vorübergehend ausblenden

Breite Medien liefern im Feed nur ihre neuesten Artikel. Gefilterte Quellen füllen sich
deshalb mit jedem Lauf.

**LinkedIn:** Profile oder Seiten bei [RSS.app](https://rss.app) in einen Feed umwandeln und
mit `kategorie: LinkedIn` eintragen.

## Themenkatalog

Unter `themen:` in `sources.yaml`. Jedes Thema hat ein **Gewicht** (1 = normal,
2 = wichtig, 3 = sehr wichtig) und **Stichwörter**. Ein Beitrag erhält jedes Thema, dessen
Stichwort in Titel oder Anriss vorkommt.

```yaml
  - name: YouTube
    gewicht: 1
    stichwoerter: [youtube, video ads, ctv]
```

Leerzeichen um ein Stichwort verhindern Teiltreffer: `" ki "` trifft nicht «Kiosk».
Die Spalte «Themen» im Tab «Quellen» zeigt, welcher Anteil der Beiträge einer Quelle ein
Thema trifft – ein guter Hinweis darauf, ob eine Quelle passt.

## Entdecken und Vorschläge

Unter `suchen:` stehen Suchbegriffe für Google News (`sprache: en` = US-Ausgabe,
`sprache: de` = Schweizer Ausgabe). Treffer von Seiten, die schon feste Quelle sind, werden
ausgeblendet; der Rest erscheint im Tab «Entdecken». Im Tab «Quellen» listet
«Vorschläge für neue Quellen» die Domains daraus, häufigste zuerst. Rauschen unter
`suchen: ignorieren:` eintragen.

## Bilder

Profilbild eines Beitrags ist das Favicon der Quelle (über den Favicon-Dienst von Google),
sonst die Initialen. Liefert ein Feed kein Bild, holt der Lauf das Titelbild (`og:image`) der
Artikelseite, höchstens 40 pro Lauf und einmal pro Artikel.

## GitHub Pages aktivieren (einmalig)

1. Repository auf GitHub öffnen → **Settings** → **Pages**.
2. Unter **Build and deployment** bei **Source** «**GitHub Actions**» wählen.
3. Die Action einmal manuell starten (siehe unten). Nach wenigen Minuten steht die Adresse
   unter Settings → Pages (`https://<konto>.github.io/<repo>/`).

GitHub Pages ist nur für **öffentliche** Repositories gratis. Die Seite ist dank `noindex`
nicht in Suchmaschinen, aber für alle mit dem Link erreichbar.

## Action manuell starten

1. Reiter **Actions** öffnen.
2. Links **«Newsfeed bauen und veröffentlichen»** wählen.
3. **Run workflow** → Branch `main` → **Run workflow**.

Sonst läuft sie alle 3 Stunden und nach jeder Änderung auf `main`. GitHub pausiert
zeitgesteuerte Actions nach 60 Tagen ohne Aktivität im Repository; dann unter Actions
«Enable workflow» klicken.

## Lokal testen

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python build.py
open site/index.html
```

## Bekannte Einschränkungen

- **Search Engine Land** und **BCG** sperren bzw. haben keinen Feed; beide laufen über eine
  Google-News-Suche (ohne Bilder, Links über news.google.com).
- **Bloofusion** hat keinen Feed; der Eintrag ist vorbereitet und deaktiviert.
- **Reddit** drosselt anonyme Abrufe. Fällt ein Abruf aus, steht das im Footer, die
  Beiträge des letzten Laufs bleiben erhalten.
- Die **Themenzuordnung** läuft über Stichwörter und ist grob (z.B. «Siri AI» → KI-Thema).
