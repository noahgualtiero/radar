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
| **Feed** | Die eigenen Quellen. Oben Themen-Chips. Gelegentlich erscheint ein Vorschlag |
| **Entdecken** | Suchfunde (Google News, KI-Websuche) und Community (Reddit). Chips nach Typ: Studie, Kennzahlen, Best Practice, News, Diskussion |
| **Briefing** | Ein Briefing pro Tag: Lauftext, die drei wichtigsten Beiträge mit Begründung, Studien und Community des Tages; oben die Trend-Begriffe |
| **Gemerkt** | Chips «Meine» (persönlich, auf allen Geräten gleich) und «Im Team» (was andere gemerkt haben, mit Anzahl Personen, ohne Namen); die Suche gilt für beide |
| **Einstellungen** (Zahnrad) | Quellen mit Schalter «in meinem Feed», Votes und Klicks, Regeln, Themen, Suchbegriffe, Farbschema, letzter Lauf mit KI-Kosten |

Bei jedem Beitrag gibt es vier Aktionen:
- **Daumen hoch:** guter Artikel. Die Zahl daneben zählt alle Daumen im Team.
- **Daumen runter:** nicht relevant.
- **Teilen**
- **Merken**

Melden mehrere Quellen dasselbe, steht der Beitrag nur einmal da, mit dem Vermerk «Auch bei …».

Sichtbare Profile gibt es keine. Cloudflare Access weiss, wer angemeldet ist. Damit zählt jede
Person pro Artikel nur einmal; Gemerkt und die Quellenwahl sind persönlich.

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

**Vorschläge oben im Feed**, für jede Person aus ihrem eigenen Verhalten (Schwellen unter `vorschlaege`):

- **Aufnehmen?** Ich habe in 30 Tagen mindestens 3 Suchfunde derselben Website geöffnet
  oder hochgevotet.
- **Aus dem Feed nehmen?** Ich habe eine Quelle in 30 Tagen mindestens 3-mal bewertet, mit
  negativem Saldo, oder sie seit 60 Tagen nicht geöffnet.
- **Antworten:**
  - «Nein, danke» blendet den Vorschlag 90 Tage aus.
  - «Aufnehmen» nimmt die Website in den eigenen Feed. Den Feed sucht der nächste Abruf. Ohne Feed dient eine
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

**Eigene Quellen:** Jede Person wählt im Tab Quellen per Schalter, was in ihrem Feed steht.
- Die Quellen aus `sources.yaml` sind Standard: für alle an, jede Person kann sie für sich ausschalten.
- Wer eine Quelle «nur für mich» aufnimmt, hat sie im eigenen Feed; für die anderen bleibt sie aus, bis sie sie anschalten. «Für alle» macht sie zur Standardquelle.
- Abgerufen werden alle Quellen, die jemand nutzt. Eine aufgenommene Quelle, die niemand mehr anhat, wird nicht mehr abgerufen.
- Das Briefing sowie «Im Team», «Meistgelesen» und «Top bewertet» unter Gemerkt berücksichtigen alle Quellen, unabhängig von der eigenen Wahl.

**Gemeinsam für alle:** Themen, Suchbegriffe und Regeln.

**Was angezeigt wird:** Die KI bewertet jeden Beitrag mit einer Relevanz von 1 bis 5. Unter
Einstellungen legt man fest, ab welcher Stufe Beiträge im Feed (Standard 2) und in Entdecken
(Standard 3) erscheinen. Immer und für alle Quellen gleich gilt: Stellenanzeigen und sehr kurze
Titel (z.B. Glossar-Einträge) fallen weg. Sonderregeln pro Quelle gibt es bewusst nicht.

**Themen:** Die KI ordnet jedem Beitrag 0 bis 3 Themen zu. Die Stichwörter pro Thema sind nur
Beispiele für die KI und Ersatz, falls sie nicht läuft. Der farbige Punkt zeigt das Gewicht.

**Quellen aufnehmen und entfernen:** jeweils «nur für mich» oder «für alle». Für alle entfernt,
wird eine Quelle nicht mehr abgerufen.

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
- Domains: `radar-5ar.pages.dev` und `*.radar-5ar.pages.dev`.
- Policy *Allow*, Include *Emails ending in* `@standout.ch`.
- Login-Methode *One-time PIN*, also ein Code per E-Mail.
- Danach in der Application den *Application Audience (AUD) Tag* kopieren.

**6. Variablen der Seite** (Dashboard → *Workers & Pages → radar → Settings → Variables and
Secrets*, Umgebung Production)

| Name | Wert |
|---|---|
| `ACCESS_TEAM_DOMAIN` | z.B. `standout.cloudflareaccess.com` (unter *Zero Trust → Settings*) |
| `ACCESS_AUD` | optional: AUD-Tag der Application. Ohne gilt jede gültige Anmeldung des Teams |
| `GITHUB_REPO` | optional: `noahgualtiero/radar` |
| `GITHUB_TOKEN` (Secret) | optional: Fine-grained Token, nur für dieses Repo, mit *Actions: Read and write*. Damit stösst eine Änderung in Radar sofort einen Abruf an |

Ohne gültige Anmeldung antwortet die API nicht. Sie prüft das Access-Token selbst.

**7. Starten**
- Auf GitHub unter *Actions → Radar abrufen und veröffentlichen → Run workflow* den ersten Lauf auslösen.
- Danach `https://radar-5ar.pages.dev` öffnen und mit der E-Mail anmelden.
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
printf 'DEV_USER=ich@lokal.test\n' > .dev.vars && npx wrangler@4.149.0 d1 execute radar --local --file schema.sql
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
