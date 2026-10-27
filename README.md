# Radar

Newsradar für Paid Search. Logo: `static/logo.svg`.

Ein Newsfeed im Stil von LinkedIn mit Neuigkeiten aus selbst festgelegten Paid-Search-Quellen.
Läuft kostenlos über **GitHub Actions** (alle 3 Stunden) und **GitHub Pages**. Alle Quellen
sind gratis: offene RSS-Feeds und Google News.

## Was die Seite zeigt

Moderne Oberfläche im Stil von Facebook (Meta), Schrift Inter:

- **Desktop:** links Bereiche und Themen (rotes # = sehr wichtig, oranges # = wichtig),
  in der Mitte der Feed, rechts das Briefing. Bis 1250 px steht das Briefing über dem Feed.
- **Handy:** unten eine Tab-Leiste, oben Themen-Chips als Filter.
- Oben die Suche in der Mitte und rechts das **Zahnrad** für die Einstellungen.
- Alle Links öffnen in einem neuen Tab, mit `rel="noopener nofollow external"`.

| Tab | Inhalt |
|---|---|
| **Feed** | Beiträge der festen Quellen, oben das **Briefing** |
| **Studien** | Beiträge aus Studien-Quellen (Optmyzr, McKinsey, BCG, IAB …) und alle Beiträge fester Quellen, die nach Studie, Umfrage, Benchmark oder Report klingen |
| **Community** | Reddit r/PPC und r/googleads, oben die häufigsten Themen der Woche |
| **Gemerkt** | Umschalter «Gemerkt / Blog-Ideen», dazu «+ Link» zum Ablegen fremder Artikel und «Kopieren» |

**Themen:** Ein Tipp auf ein Thema filtert den aktuellen Tab. Ein Tipp auf den
Quellennamen in einem Beitrag zeigt nur diese Quelle.

**Briefing** (einklappbar):
- *Gestern wichtig:* die 3 wichtigsten Themen des Vortages, je mit dem wichtigsten Artikel
  und einem Link auf die weiteren. Rangfolge nach *(Beiträge + Quellen) × Gewicht des Themas*.
- *Im Trend:* konkrete Begriffe (z.B. «Review Summaries»), die in den letzten 3 Tagen bei
  mindestens zwei Quellen auftauchen und mindestens doppelt so häufig sind wie im
  30-Tage-Schnitt. Einzelwörter brauchen drei Quellen. Ein Klick sucht danach. Erscheint
  nur, wenn es solche Begriffe gibt.
- *Mehrfach berichtet:* Geschichten, über die mehrere Quellen schreiben.

**Reihenfolge:** Was seit dem letzten Besuch neu ist, steht oben, danach die Linie
«Bis hier gelesen». Innerhalb davon neueste zuerst; wichtige Themen rücken leicht nach oben
(6 Stunden pro Gewichtsstufe), Quellen mit «Mehr von …» um 2 Tage.

**Zahnrad** (Einstellungen): Quellen aufnehmen und entfernen, Themen und Suchbegriffe pflegen, Quellen-Auswertung, stummgeschaltete Quellen, Vorschläge für neue
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
  blendet sie aus (mit «Rückgängig»; zurückholen unter dem Zahnrad).

Der Titel öffnet das Original, **#Thema** filtert auf dieses Thema.

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

In den Einstellungen (Zahnrad) lassen sich ohne Code ändern:

| Was | Wie |
|---|---|
| Quelle aufnehmen | Link eingeben, Kategorie wählen; der Feed wird automatisch gesucht |
| Quelle entfernen | «Entfernen» in der Quellen-Tabelle; setzt `aktiv: false` (erneut aufnehmen macht sie wieder aktiv) |
| Thema anlegen oder ändern | Name, Gewicht, Stichwörter; «Bearbeiten» füllt das Formular mit dem bestehenden Thema |
| Thema entfernen | «Entfernen» in der Themen-Tabelle |
| Suchbegriff hinzufügen oder entfernen | Begriff und Ausgabe (USA oder Schweiz) |

Jeder Knopf öffnet auf GitHub einen vorbereiteten Auftrag (Issue); dort auf «Create»
klicken. Die Action `settings.yml` («Einstellungen übernehmen») schreibt die Änderung in
`sources.yaml` – Kommentare und Verweise wie `*paid` bleiben erhalten –, committet sie,
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
   mit `site:domain` (Beispiel BCG in `sources.yaml`).
2. Eintrag in `sources.yaml` unter `quellen:` einfügen. `kategorie` ist eine der Kategorien
   oben in der Datei.
3. Speichern und committen. Die Seite wird automatisch neu gebaut.

Weitere Felder pro Quelle:

- `nur_begriffe: *paid` – nur Beiträge mit Paid-Search-Bezug (für breite Medien wie t3n)
- `nur_begriffe: *marketing` – nur Marketing-Themen (für Beratungen wie McKinsey)
- `nur_themen: 2` – nur Beiträge, die ein Thema mit Gewicht 2 oder 3 treffen
  (Qualitätsfilter für Quellen mit viel Nebensächlichem, z.B. PPC Land)
- `min_woerter: 5` – Beiträge mit kürzeren Titeln weglassen (z.B. Glossar-Einträge)
- `ausschliessen: [...]` – Beiträge mit diesen Begriffen im Titel weglassen
- `aktiv: false` – Quelle vorübergehend ausblenden

Stellenanzeigen («Working Student», «Internship», «(m/w/d)», Links auf /careers/ …) werden
bei allen Quellen automatisch weggelassen. Geänderte Filter wirken beim nächsten Lauf auch
auf den gespeicherten Bestand.

Breite Medien liefern im Feed nur ihre neuesten Artikel. Gefilterte Quellen füllen sich
deshalb mit jedem Lauf.

**Newsletter:** Mit [Kill the Newsletter](https://kill-the-newsletter.com) eine
Newsletter-Adresse erzeugen, den Newsletter mit dieser Adresse abonnieren und den
angezeigten Atom-Feed als Quelle aufnehmen. Jede Ausgabe erscheint dann als Beitrag.

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
Die Spalte «Themen» in der Quellen-Auswertung (Zahnrad) zeigt, welcher Anteil der Beiträge einer Quelle ein
Thema trifft – ein guter Hinweis darauf, ob eine Quelle passt.

## Entdecken und Vorschläge

Unter `suchen:` stehen Suchbegriffe für Google News (`sprache: en` = US-Ausgabe,
`sprache: de` = Schweizer Ausgabe). Treffer von Seiten, die schon feste Quelle sind, werden
ausgeblendet. Die übrigen Seiten erscheinen nicht im Feed, sondern unter dem Zahnrad als
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

- **Search Engine Land** und **BCG** sperren bzw. haben keinen Feed; beide laufen über eine
  Google-News-Suche (ohne Bilder, Links über news.google.com).
- **Bloofusion** hat keinen Feed; der Eintrag ist vorbereitet und deaktiviert.
- **Reddit** drosselt anonyme Abrufe. Fällt ein Abruf aus, steht das im Footer, die
  Beiträge des letzten Laufs bleiben erhalten.
- Die **Themenzuordnung** läuft über Stichwörter und ist grob (z.B. «Siri AI» → KI-Thema).
