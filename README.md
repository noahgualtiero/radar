# Radar

Newsradar für Paid Search. Logo: `static/logo.svg`.

Ein Feed im Stil von Instagram mit Neuigkeiten aus fest gewählten Paid-Search-Quellen. Dazu
kommen Suchfunde, Studien und ein tägliches Briefing. Das Team arbeitet gemeinsam darin: Die
Daumen und die geöffneten Artikel aller Personen bestimmen die Reihenfolge, und Radar schlägt
Quellen zum Aufnehmen und Entfernen vor.

## Aufbau

| Teil | Wo | Kosten |
|---|---|---|
| Abruf, KI, Bau der Seite (`build.py`, `ai.py`) | GitHub Actions, alle 3 Stunden | gratis |
| Bestand zwischen den Läufen (`items.json`) | Branch `data` im Repo | gratis |
| Seite, API (`functions/api/`), Datenbank D1 | Cloudflare Pages | Gratis-Kontingent |
| Anmeldung per E-Mail-Code | Cloudflare Access | gratis bis 50 Personen |
| KI (Einordnung, Briefing, Websuche) | OpenAI-API | rund 1–2 USD pro Monat, Budget einstellbar |

Alle Quellen sind gratis: offene RSS-Feeds und Google News.

## Die App

Fünf Tabs, auf dem Desktop links, auf dem Handy unten:

| Tab | Inhalt |
|---|---|
| **Feed** | Die festen Quellen. Oben Themen-Chips und «Team-Tipps» (Artikel, die andere hochgevotet haben). Gelegentlich erscheint ein Vorschlag |
| **Entdecken** | Suchfunde (Google News, KI-Websuche) und Community (Reddit). Chips nach Typ: Studie, Kennzahlen, Best Practice, News, Diskussion |
| **Briefing** | Ein Briefing pro Tag: Lauftext, die drei wichtigsten Beiträge mit Begründung, Studien und Community des Tages; oben die Trend-Begriffe |
| **Gemerkt** | Persönlich und auf allen Geräten gleich. «+ Link» legt fremde Artikel ab, «Kopieren» kopiert die Liste |
| **Quellen** | Quellen mit Votes und Klicks, Regeln, Themen, Suchbegriffe, Farbschema, letzter Lauf mit KI-Kosten |

Bei jedem Beitrag gibt es vier Aktionen:
- **Daumen hoch:** guter Artikel. Die Zahl daneben zählt alle Daumen im Team.
- **Daumen runter:** nicht relevant.
- **Teilen**
- **Merken**

Melden mehrere Quellen dasselbe, steht der Beitrag nur einmal da, mit dem Vermerk «Auch bei …».

Sichtbare Profile gibt es keine. Cloudflare Access weiss, wer angemeldet ist. Damit zählt jede
Person pro Artikel nur einmal, und Gemerkt bleibt persönlich.

Mit der Taste «/» oder dem Chip «Suchen» lässt sich suchen. Direktlinks wie `#discover`,
`#briefing`, `#saved` oder `#sources` öffnen einen Tab direkt.

## Wie Radar sortiert und vorschlägt

**Reihenfolge in Feed und Entdecken:** Aktualität × (1 + Schub).
- **Aktualität:** halbiert sich alle 36 Stunden.
- **Schub:** setzt sich zusammen aus
  - den Votes und Klicks am Artikel
  - dem Schnitt der Quelle über ihre Beiträge der letzten 30 Tage
  - dem Themen-Gewicht
  - in Entdecken zusätzlich der KI-Relevanz
- **Deckel:** Der Schub bleibt zwischen −0,3 und +0,5, damit nicht immer dieselben Quellen oben stehen.
- **Neu seit dem letzten Besuch:** steht im Feed zusätzlich zuoberst.

Alle Gewichte stehen unter `gewichtung` in `sources.yaml`.

**Vorschläge oben im Feed** (Schwellen unter `vorschlaege`):

- **Aufnehmen?** Das Team hat in 30 Tagen mindestens 3 Suchfunde derselben Website geöffnet
  oder hochgevotet.
- **Entfernen?** Eine Quelle hat in 30 Tagen mindestens 5 Votes mit negativem Saldo, oder
  seit 60 Tagen hat sie niemand geöffnet.
- **Antworten:**
  - «Nein, danke» blendet den Vorschlag 90 Tage aus.
  - «Aufnehmen» trägt die Website ein. Den Feed sucht der nächste Abruf. Ohne Feed dient eine
    Google-News-Suche nach `site:Domain`.

## KI

Die KI läuft über die OpenAI-API (`ai.py`). Ihre Einstellungen stehen unter `ki` in `sources.yaml`.

| Aufgabe | Wie oft | Modell (Standard) |
|---|---|---|
| Einordnen: Typ und Relevanz 1–5 | jeder neue Beitrag einmal, 50 pro Aufruf | `gpt-5.4-nano` |
| Briefing | einmal pro Tag, aus den 25 relevantesten Beiträgen des Vortags | `gpt-5.4-mini` |
| Websuche nach Studien, Kennzahlen, Best Practices | alle 7 Tage (`websuche_alle_tage`, 0 = aus) | `gpt-5.4-mini` mit Websuche |

**Keine Erfindungen:** Die KI arbeitet nur mit dem, was in den Beiträgen steht.

**Kostenkontrolle:**
- Jeder Aufruf wird mit Tokens und Kosten protokolliert, im Feld `ai_log` in `items.json`. Die Summe steht im Tab Quellen.
- Ist `budget_monat_usd` erreicht, läuft Radar bis Monatsende ohne KI weiter:
  - Typ nach festen Mustern
  - Relevanz aus dem Themen-Gewicht
  - Briefing als zusammengesetzter Text
- Die Preise unter `preise_usd_pro_mio_tokens` dienen nur dieser Kontrolle. Bei einem Modellwechsel nachführen.

**Studien von Beratungen ohne eigenen Feed** (McKinsey, BCG, Gartner, Forrester, Think with
Google): Diese findet Radar über zwei Suchbegriffe und die wöchentliche KI-Websuche.

## Einstellungen

**Wo die Einstellungen liegen:**
- Grundeinstellung ist `sources.yaml`.
- Sobald jemand im Tab Quellen etwas ändert, liegen die Einstellungen in der Datenbank und gelten
  von dort. Neue Abschnitte aus `sources.yaml` werden dort ergänzt.

**Wann eine Änderung wirkt:**
- Ist `GITHUB_TOKEN` gesetzt (siehe unten), stösst jede Änderung sofort einen neuen Abruf an.
- Sonst wirkt sie beim nächsten regulären Lauf.

**Wer was ändern darf:**
- Quellen aufnehmen und entfernen, auch über die Vorschläge: nur die Admins aus `ADMIN_EMAILS`.
  Nur sie sehen die Vorschläge und die Knöpfe dazu, und die API lehnt solche Änderungen von anderen ab.
- Themen, Suchbegriffe und Regeln: alle Angemeldeten.

**Regeln:** Sie gelten für alle Quellen gleich:
- Mindestlänge des Titels
- Pflicht-Thema
- Stellenanzeigen ausblenden
- ausgeschlossene Begriffe

Sonderregeln pro Quelle gibt es bewusst nicht. Liefert eine Quelle damit nichts Brauchbares,
wird sie entfernt.

## Online stellen (einmalig, rund 30 Minuten)

Die Befehle laufen im Terminal im Repo-Ordner. Wrangler ist das Werkzeug von Cloudflare.

**1. Cloudflare: Datenbank und Projekt anlegen**

```bash
npx wrangler@4.149.0 login
```

```bash
npx wrangler@4.149.0 d1 create radar
```

Die ausgegebene `database_id` in `wrangler.toml` eintragen. Sie ist kein Geheimnis und darf ins Repo. Danach:

```bash
npx wrangler@4.149.0 d1 execute radar --remote --file schema.sql
```

```bash
npx wrangler@4.149.0 pages project create radar --production-branch main
```

**2. Cloudflare: API-Token für GitHub anlegen**
- Im Dashboard unter *My Profile → API Tokens → Create Token → Custom token*.
- Rechte: *Account · Cloudflare Pages · Edit* und *Account · D1 · Edit*.
- Die Account-ID steht im Dashboard rechts unten auf der Startseite des Kontos.

**3. OpenAI vorbereiten**
- Auf platform.openai.com einen API-Key anlegen.
- Guthaben laden, mindestens 5 USD.
- Unter *Limits* ein Monatslimit setzen, z.B. 10 USD, als zweite Bremse.

**4. GitHub: Secrets und Variablen** (Repo → *Settings → Secrets and variables → Actions*)

| Art | Name | Wert |
|---|---|---|
| Secret | `OPENAI_API_KEY` | Key aus Schritt 3 |
| Secret | `CLOUDFLARE_API_TOKEN` | Token aus Schritt 2 |
| Variable | `CLOUDFLARE_ACCOUNT_ID` | Account-ID |
| Variable | `D1_DATABASE_ID` | `database_id` aus Schritt 1 |

**5. Anmeldung mit Cloudflare Access einrichten**
- Dashboard → *Zero Trust → Access → Applications → Add an application → Self-hosted*.
- Domains: `radar.pages.dev` und `*.radar.pages.dev`.
- Policy *Allow*, Include *Emails ending in* `@standout.ch`.
- Login-Methode *One-time PIN*, also ein Code per E-Mail.
- Danach in der Application den *Application Audience (AUD) Tag* kopieren.

**6. Variablen der Seite** (Dashboard → *Workers & Pages → radar → Settings → Variables and
Secrets*, Umgebung Production)

| Name | Wert |
|---|---|
| `ACCESS_TEAM_DOMAIN` | z.B. `standout.cloudflareaccess.com` (unter *Zero Trust → Settings*) |
| `ACCESS_AUD` | AUD-Tag aus Schritt 5 |
| `ADMIN_EMAILS` | wer Quellen aufnehmen und entfernen darf, z.B. `noah.kaech@standout.ch` (mehrere mit Komma) |
| `GITHUB_REPO` | optional: `noahgualtiero/radar` |
| `GITHUB_TOKEN` (Secret) | optional: Fine-grained Token, nur für dieses Repo, mit *Actions: Read and write*. Damit stösst eine Änderung in Radar sofort einen Abruf an |

Ohne gültige Anmeldung antwortet die API nicht. Sie prüft das Access-Token selbst.

**7. Starten**
- Auf GitHub unter *Actions → Radar abrufen und veröffentlichen → Run workflow* den ersten Lauf auslösen.
- Danach `https://radar.pages.dev` öffnen und mit der E-Mail anmelden.
- Auf dem iPhone über *Teilen → Zum Home-Bildschirm* als App ablegen.

**8. Alte Seite abschalten**
- GitHub → *Settings → Pages* → GitHub Pages deaktivieren.
- Sonst bleibt die alte, öffentlich erreichbare Version stehen.

## Lokal testen

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python build.py --out site
```

```bash
printf 'DEV_USER=ich@lokal.test\nADMIN_EMAILS=ich@lokal.test\n' > .dev.vars && npx wrangler@4.149.0 d1 execute radar --local --file schema.sql
```

```bash
npx wrangler@4.149.0 pages dev site --port 8788
```

Dann `http://127.0.0.1:8788` öffnen.
- `DEV_USER` ersetzt lokal die Anmeldung.
- Ohne `OPENAI_API_KEY` läuft alles ohne KI.

## Icons

`static/logo.svg` ist das Logo und Favicon. Daraus erzeugt `tools/make_icons.py` die PNGs für
iOS, das Web-Manifest und das Vorschaubild:

```bash
.venv/bin/python tools/make_icons.py
```

## Dateien

| Datei | Zweck |
|---|---|
| `sources.yaml` | Grundeinstellung: Quellen, Regeln, Themen, KI, Gewichtung, Vorschläge, Suchen |
| `build.py` | Abruf, Zusammenführen, Themen, Duplikate, Briefing, Seite |
| `ai.py` | OpenAI: Einordnung, Briefing, Websuche, Kostenprotokoll |
| `find_feed.py` | Sucht den Feed einer Website, auch einzeln: `python find_feed.py URL` |
| `functions/api/[[path]].js` | API: Votes, Klicks, Gemerkt, Vorschläge, Einstellungen |
| `schema.sql`, `wrangler.toml` | Datenbank und Cloudflare-Projekt |
| `templates/index.html.j2` | Die App |
| `static/`, `tools/make_icons.py` | Logo, App-Icons, Manifest |

## Einschränkungen

- **Reddit** begrenzt anonyme Abrufe. Fällt der Feed aus, steht das im Tab Quellen unter «Letzter Lauf».
- **Search Engine Land** sperrt automatisierte Abrufe. Die Beiträge kommen deshalb über Google News, ohne Bilder.
- **Vorschläge brauchen Daten.** Solange wenige Personen Radar nutzen, erscheinen sie selten. Das ist
  gewollt, damit nicht ein einzelner Klick über eine Quelle entscheidet.
- **Rechtliches:** Radar zeigt Titel, kurze Anrisse und Vorschaubilder der Quellen und verlinkt auf sie.
  - Für die interne Nutzung hinter der Anmeldung ist das unkritisch.
  - Öffentlich oder mit Werbung wäre es neu zu prüfen.
