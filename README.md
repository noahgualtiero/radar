# Radar

Newsradar für Paid Search. Logo: `static/logo.svg`.

Ein Newsfeed im Stil von LinkedIn mit Neuigkeiten aus selbst festgelegten Paid-Search-Quellen.
Läuft kostenlos über **GitHub Actions** (alle 3 Stunden) und **GitHub Pages**. Alle Quellen
sind gratis: offene RSS-Feeds und Google News.

## Was die Seite zeigt

Ruhige, moderne Oberfläche (Schrift Inter):

- **Desktop:** links eine schlanke Navigation mit Bereichen, Themen (Punkt rot = sehr wichtig,
  orange = wichtig) und unten den Einstellungen; rechts der Inhalt.
- **Handy:** oben die Themen-Chips, unten eine durchscheinende Tab-Leiste mit Feed, Studien,
  Community, Gemerkt und Einstellungen.
- **Suche:** auf dem Desktop als Feld oben in der Navigation (Taste «/» springt hinein, Esc
  setzt zurück); auf dem Handy als Lupe vor den Themen-Chips, die das Suchfeld aufklappt.
- Alle Links öffnen in einem neuen Tab, mit `rel="noopener nofollow external"`.

| Tab | Inhalt |
|---|---|
| **Feed** (Start) | Oben die Briefing-Karte zum Vortag (Lauftext, Trend-Begriffe und Themen als Chips), darunter die Beiträge der festen Quellen |
| **Studien** | Beiträge aus Studien-Quellen (Optmyzr, Smarter Ecommerce, Brainlabs, IAB …) und alle Beiträge fester Quellen, die nach Studie, Umfrage, Benchmark oder Report klingen |
| **Community** | Reddit r/PPC und r/googleads, oben die häufigsten Themen der Woche |
| **Gemerkt** | Umschalter «Gemerkt / Blog-Ideen», dazu «+ Link» zum Ablegen fremder Artikel und «Kopieren» |
| **Einstellungen** | Quellen, Regeln, Themen, Suchbegriffe, Darstellung, letzter Lauf |

**Briefing-Text:** In der GitHub Action schreibt eine KI über
[GitHub Models](https://github.com/marketplace/models) (gratis Kontingent, Modell
`openai/gpt-4.1-mini`) 3–4 Sätze aus den Schlagzeilen des Vortages – nur aus den
Schlagzeilen, ohne Erfindungen. Der Text entsteht einmal pro Tag und wird danach
wiederverwendet. Ist die KI nicht erreichbar (oder lokal), steht ein automatisch
zusammengesetzter Text da. Unter dem Text steht, welche Variante es ist.

**Themen:** Ein Tipp auf ein Thema filtert den aktuellen Tab. Ein Tipp auf den
Quellennamen in einem Beitrag zeigt nur diese Quelle.

**Im Trend:** konkrete Begriffe (z.B. «Review Summaries»), die in den letzten 3 Tagen bei
mindestens zwei Quellen auftauchen und mindestens doppelt so häufig sind wie im
30-Tage-Schnitt; Einzelwörter brauchen drei Quellen. Ein Klick sucht danach.

**Reihenfolge:** Was seit dem letzten Besuch neu ist, steht oben, danach die Linie
«Bis hier gelesen». Innerhalb davon neueste zuerst; wichtige Themen rücken leicht nach oben
(6 Stunden pro Gewichtsstufe), Quellen mit «Mehr von …» um 2 Tage.

**Einstellungen:** Quellen aufnehmen und entfernen, Themen und Suchbegriffe pflegen, Quellen-Auswertung, stummgeschaltete Quellen, Vorschläge für neue
Quellen mit ihren Artikeln, Farbschema und Status des letzten Laufs.

Die Seite hat `noindex` gesetzt und sperrt Suchmaschinen per `robots.txt` aus.

## Passwort

Vor der Seite steht eine einfache Passwort-Sperre. Nach einmaliger Eingabe bleibt der Browser
freigeschaltet. In `sources.yaml` unter `zugang:` steht nur der SHA-256-Hash des Passworts.
Neues Passwort setzen:

```bash
printf '%s' 'NEUES-PASSWORT' | shasum -a 256
```

Den ausgegebenen Wert bei `passwort_sha256` eintragen, committen, pushen.

Die Sperre ist ein Vorhang, kein Tresor: Das Repository und `items.json` sind öffentlich
lesbar. Für die Inhalte (öffentliche News) reicht das; Gemerkt und Bewertungen liegen ohnehin
nur im eigenen Browser.

## Bedienung

Unter jedem Beitrag:

- **Merken** – legt den Beitrag unter «Gemerkt» ab.
- **Blog-Idee** – legt ihn unter «Gemerkt → Blog-Ideen» ab.
- **⋯** – «Mehr von [Quelle]» rückt deren Beiträge nach oben; «[Quelle] stummschalten»
  blendet sie aus (mit «Rückgängig»; zurückholen in den Einstellungen).

Der Titel öffnet das Original, **#Thema** filtert auf dieses Thema.

**Neu laden auf dem Handy:** oben nach unten ziehen. Im Browser macht das Safari bzw.
Chrome selbst; in der App vom Home-Bildschirm übernimmt es Radar (Symbol oben, ab etwa
7 cm Zug lädt die Seite neu). Neue Beiträge gibt es nach jedem Lauf der Action.

Bewertungen, Gemerkt und Blog-Ideen werden **im Browser** gespeichert, also pro Gerät und
Browser. Wer die Browserdaten löscht, verliert sie.

## Aufbau

| Datei | Zweck |
|---|---|
| `sources.yaml` | Quellen, Themenkatalog, Suchbegriffe – **alles Inhaltliche wird hier gepflegt** |
| `build.py` | Holt alle Feeds, entfernt Duplikate, ordnet Themen zu, berechnet Überblick und Trends, baut die Seite |
| `find_feed.py` | Findet den Feed einer Seite und gibt den Eintrag für `sources.yaml` aus |
| `apply_issue.py` | Übernimmt Änderungen aus den Einstellungen (Issues) in `sources.yaml` |
| `.github/workflows/settings.yml` | Action dazu: «Einstellungen übernehmen» |
| `templates/index.html.j2` | Vorlage der Webseite |
| `.github/workflows/build.yml` | Automatischer Lauf und Veröffentlichung |

## Über die Seite pflegen

In den Einstellungen lassen sich ohne Code ändern:

| Was | Wie |
|---|---|
| Quelle aufnehmen | Link eingeben, Kategorie wählen; der Feed wird automatisch gesucht |
| Quelle entfernen | «Entfernen» in der Quellen-Tabelle; setzt `aktiv: false` (erneut aufnehmen macht sie wieder aktiv) |
| Thema anlegen oder ändern | Name, Gewicht, Stichwörter; «Bearbeiten» füllt das Formular mit dem bestehenden Thema |
| Thema entfernen | «Entfernen» in der Themen-Tabelle |
| Regeln für alle Quellen | Mindestlänge, Themen-Schwelle, Stellenanzeigen, ausgeschlossene Begriffe |
| Suchbegriff hinzufügen oder entfernen | Begriff eingeben; gesucht wird in den Ausgaben USA, UK, IE, DE, AT und CH |

Jeder Knopf öffnet auf GitHub einen vorbereiteten Auftrag (Issue); dort auf «Create»
klicken. Die Action `settings.yml` («Einstellungen übernehmen») schreibt die Änderung in
`sources.yaml` (Kommentare bleiben erhalten), committet sie,
baut die Seite neu und schreibt das Ergebnis als Kommentar ins Issue. Nach etwa 3 Minuten
ist die Änderung sichtbar. Nur Issues des Repo-Inhabers werden verarbeitet. Das Skript
dahinter ist `apply_issue.py`.

## Quelle hinzufügen

**Über die Seite:** siehe oben. Bei den «Vorschlägen für neue Quellen» füllt «Aufnehmen»
das Formular vor.

**Von Hand:**

1. Feed finden:

   ```bash
   .venv/bin/python find_feed.py https://example.com/ein-artikel Studien
   ```

   Das Skript prüft die Feed-Links der Seite und übliche Pfade (`/feed/`, `/rss.xml` …) und
   gibt den fertigen Eintrag aus. Findet es nichts: RSS.app verwenden oder eine Google-News-Suche
   mit `site:domain` (Beispiel Search Engine Land in `sources.yaml`).
2. Eintrag in `sources.yaml` unter `quellen:` einfügen. `kategorie` ist eine der Kategorien
   oben in der Datei.
3. Speichern und committen. Die Seite wird automatisch neu gebaut.

Pro Quelle gibt es **keine Sonderregeln**. Ausser `aktiv: false` (Quelle vorübergehend
ausblenden) hat eine Quelle nur Name, URL und Kategorie. Was erscheint, bestimmen die
Regeln für alle Quellen und der Themenkatalog. Liefert eine Quelle damit nichts
Brauchbares, wird sie entfernt.

**Newsletter:** Mit [Kill the Newsletter](https://kill-the-newsletter.com) eine
Newsletter-Adresse erzeugen, den Newsletter mit dieser Adresse abonnieren und den
angezeigten Atom-Feed als Quelle aufnehmen. Jede Ausgabe erscheint dann als Beitrag.

**LinkedIn:** Profile oder Seiten bei [RSS.app](https://rss.app) in einen Feed umwandeln und
mit `kategorie: LinkedIn` eintragen.

## Regeln für alle Quellen

Unter `regeln:` in `sources.yaml`, in den Einstellungen änderbar. Sie gelten für jede
Quelle gleich, auch für die Google-News-Suchen:

| Regel | Standard | Wirkung |
|---|---|---|
| `min_woerter` | 5 | Beiträge mit kürzerem Titel fallen weg (z.B. Glossar-Einträge) |
| `mindest_gewicht` | 1 | Nur Beiträge, die ein Thema treffen (0 = aus, 2 = ab «wichtig», 3 = nur «sehr wichtig») |
| `stellenanzeigen_ausblenden` | ja | «Working Student», «Internship», «(m/w/d)», Links auf /careers/ … |
| `ausschliessen` | – | Beiträge mit diesen Begriffen im Titel fallen weg |

Geänderte Regeln wirken beim nächsten Lauf auch auf den gespeicherten Bestand. Weil die
Themen-Regel am Katalog hängt, sind präzise Stichwörter entscheidend: ein zu breites
Stichwort («ai», «strategy») lässt Fremdes durch, ein fehlendes lässt Passendes weg.

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
Die Spalte «Themen» in der Quellen-Auswertung (Einstellungen) zeigt, welcher Anteil der Beiträge einer Quelle ein
Thema trifft – ein guter Hinweis darauf, ob eine Quelle passt.

## Entdecken und Vorschläge

Unter `suchen:` stehen Suchbegriffe für Google News; jeder Begriff wird in den Ausgaben
USA, Grossbritannien, Irland, Deutschland, Österreich und Schweiz gesucht. Treffer von Seiten, die schon feste Quelle sind, werden
ausgeblendet. Die übrigen Seiten erscheinen nicht im Feed, sondern in den Einstellungen als
«Vorschläge für neue Quellen», häufigste zuerst, mit ihren Artikeln. Rauschen unter
`suchen: ignorieren:` eintragen.

## Icons und Vorschaubild

`static/logo.svg` ist das Logo und Favicon. Daraus erzeugt `tools/make_icons.py` die PNGs:
iOS-Icon (`apple-touch-icon.png`), App-Icons für das Web-Manifest, PNG-Favicon und das
Vorschaubild für geteilte Links (`og.png`, 1200×630). Nur nötig, wenn sich das Logo ändert:

```bash
.venv/bin/python -m pip install Pillow
.venv/bin/python tools/make_icons.py
```

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

In den Einstellungen führt «Jetzt aktualisieren» direkt dorthin.

1. Reiter **Actions** öffnen.
2. Links **«Radar bauen und veröffentlichen»** wählen.
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

- **Search Engine Land** sperrt seinen Feed und läuft deshalb über eine
  Google-News-Suche (ohne Bilder, Links über news.google.com).
- **Bloofusion** hat keinen Feed; der Eintrag ist vorbereitet und deaktiviert.
- **Reddit** drosselt anonyme Abrufe. Fällt ein Abruf aus, steht das im Footer, die
  Beiträge des letzten Laufs bleiben erhalten.
- Die **Themenzuordnung** läuft über Stichwörter und ist grob (z.B. «Siri AI» → KI-Thema).
