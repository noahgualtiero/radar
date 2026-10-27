# Paid Search Newsfeed

Eine schlichte Webseite, die neue Artikel aus festgelegten Paid-Search-Quellen als Karten
anzeigt, neueste zuerst. Keine Zusammenfassungen, keine Bewertungen: Titel, Quelle, Datum,
Anrisstext aus dem Feed und Link zum Original.

- Läuft kostenlos über **GitHub Actions** (alle 3 Stunden) und **GitHub Pages**.
- Zeigt die Artikel der letzten **30 Tage**, Duplikate werden entfernt.
- Filter nach Kategorie und Quelle, Suchfeld, Hell-/Dunkelmodus, mobil lesbar.
- Markierung **«Neu»** für alles, was seit dem letzten Besuch dazugekommen ist (im Browser
  gespeichert, pro Gerät).
- Ist eine Quelle nicht erreichbar, läuft der Rest weiter; die betroffene Quelle steht
  dezent im Footer.
- Die Seite ist mit `noindex` versehen und sperrt Suchmaschinen per `robots.txt` aus.

## Aufbau

| Datei | Zweck |
|---|---|
| `sources.yaml` | Liste der Quellen – **nur hier** werden Quellen ergänzt |
| `build.py` | Holt alle Feeds, entfernt Duplikate, sortiert, baut die Seite |
| `templates/index.html.j2` | Vorlage der Webseite |
| `.github/workflows/build.yml` | Automatischer Lauf und Veröffentlichung |

## Quelle hinzufügen

1. `sources.yaml` öffnen (auf GitHub direkt über das Stift-Symbol bearbeitbar).
2. Unter `quellen:` einen Eintrag ergänzen:

   ```yaml
   - name: Name der Quelle
     url: https://example.com/feed/
     kategorie: News
   ```

   `kategorie` muss eine der Kategorien oben in der Datei sein:
   Offiziell, News, Studien, DACH, LinkedIn.
3. Speichern (Commit auf `main`). Die Seite wird automatisch neu gebaut.

**Feed-URL finden:** Bei WordPress-Seiten funktioniert meist `…/feed/`. Sonst im
Seitenquelltext nach `application/rss+xml` suchen. Ob die URL taugt, zeigt ein Aufruf im
Browser: Es muss XML mit `<item>`- oder `<entry>`-Einträgen erscheinen.

**LinkedIn:** LinkedIn bietet keine eigenen Feeds. Profile oder Unternehmensseiten zuerst
bei [RSS.app](https://rss.app) in einen Feed umwandeln, dann die RSS.app-URL mit
`kategorie: LinkedIn` eintragen. Ein Beispiel steht auskommentiert in `sources.yaml`.

**Quelle vorübergehend ausblenden:** `aktiv: false` beim Eintrag setzen.

**Nur bestimmte Themen einer Quelle:** Mit `nur_kategorien: [PPC]` werden nur Artikel
übernommen, die im Feed diese Kategorie tragen.

## Suchbegriffe und unbekannte Quellen

Neben den festen Quellen fragt der Lauf für jeden Suchbegriff unter `suchen:` in
`sources.yaml` Google News ab (Zeitraum: letzte 7 Tage). Treffer von Seiten, die schon als
feste Quelle geführt sind, werden ausgeblendet. Der Rest erscheint in der Kategorie
**Entdecken**, mit dem Suchbegriff auf der Karte.

Unten auf der Seite listet **Unbekannte Quellen** alle Domains aus diesen Treffern, häufigste
zuerst, mit Anzahl, letztem Treffer und den Suchbegriffen. «Treffer zeigen» filtert die
Karten auf diese Domain. Danach:

- Passende Seite → Feed-URL suchen und unter `quellen:` aufnehmen.
- Rauschen → Domain unter `suchen: ignorieren:` eintragen.

Suchbegriff ergänzen:

```yaml
    - { begriff: '"Consent Mode" Google Ads', sprache: en }
```

`sprache: en` fragt die US-Ausgabe von Google News ab, `sprache: de` die Schweizer Ausgabe.
Anführungszeichen erzwingen die exakte Phrase, `OR` verbindet Alternativen.

## GitHub Pages aktivieren (einmalig)

1. Repository auf GitHub öffnen → **Settings** → **Pages**.
2. Unter **Build and deployment** bei **Source** «**GitHub Actions**» wählen.
3. Die Action einmal manuell starten (siehe unten). Nach 1–2 Minuten steht die Adresse
   der Seite oben unter Settings → Pages (Format `https://<konto>.github.io/<repo>/`).

Hinweis: Bei einem privaten Repository braucht GitHub Pages einen kostenpflichtigen Plan
(Pro/Team). Mit einem öffentlichen Repository ist alles kostenlos; die Seite selbst ist
dank `noindex` nicht in Suchmaschinen auffindbar, aber für alle mit dem Link erreichbar.

## Action manuell starten

1. Im Repository den Reiter **Actions** öffnen.
2. Links **«Newsfeed bauen und veröffentlichen»** wählen.
3. Rechts **Run workflow** → Branch `main` → **Run workflow**.

Ausserdem läuft die Action automatisch alle 3 Stunden und nach jeder Änderung auf `main`.
Hinweis: GitHub pausiert zeitgesteuerte Actions, wenn im Repository 60 Tage lang nichts
passiert ist. Dann unter Actions einmal «Enable workflow» klicken.

## Lokal testen

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python build.py
open site/index.html
```

## Bekannte Einschränkungen der Startquellen

- **Search Engine Land** blockiert automatisierte Abrufe seiner Feeds. Ersatzweise wird
  eine Google-News-Suche auf searchengineland.com verwendet, eingeschränkt auf
  PPC-Begriffe. Dadurch fehlen Bilder und Anrisstext, die Links führen über
  news.google.com, und vereinzelt rutscht ein SEO-Artikel durch.
- **Bloofusion** bietet derzeit keinen RSS-Feed an. Der Eintrag ist in `sources.yaml`
  vorbereitet und deaktiviert; sobald eine Feed-URL (z.B. via RSS.app) vorliegt, eintragen
  und `aktiv: false` entfernen.
