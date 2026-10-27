"""KI für Radar über die OpenAI-API (Responses API).

Drei Aufgaben, alle mit kleinen, günstigen Modellen:
  - einordnen:  jeder neue Beitrag einmal: Typ (Studie, Kennzahlen, Best Practice, News,
                Diskussion) und Relevanz 1–5 für ein Paid-Search-Team, viele Beiträge pro Aufruf
  - briefing:   einmal pro Tag ein Lauftext aus den relevantesten Beiträgen des Vortags
  - websuche:   einmal pro Woche eine Websuche nach Studien, Kennzahlen und Best Practices

Jeder Aufruf wird mit Tokens und Kosten protokolliert. Ist das Monatsbudget aufgebraucht oder
fehlt OPENAI_API_KEY, läuft Radar ohne KI weiter (Regeln statt Einordnung, zusammengesetzter
Text statt Briefing).
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.openai.com/v1/responses"
TYPES = ["Studie", "Kennzahlen", "Best Practice", "News", "Diskussion"]
CHUNK = 50  # Beiträge pro Einordnungs-Aufruf


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


class AI:
    def __init__(self, config: dict, state: dict):
        self.cfg = config or {}
        self.key = os.environ.get("OPENAI_API_KEY", "")
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        state = dict(state or {})
        if state.get("month") != month:  # neuer Monat, neues Budget
            state.update(month=month, spent_usd=0.0)
        self.state = state
        self.log: list[dict] = []

    # ---------- Kosten ----------

    @property
    def budget(self) -> float:
        return float(self.cfg.get("budget_monat_usd", 5))

    def unavailable(self) -> str:
        """Grund, warum die KI nicht läuft, sonst leer."""
        if not self.key:
            return "kein OPENAI_API_KEY"
        if self.state["spent_usd"] >= self.budget:
            return f"Monatsbudget von {self.budget:.2f} USD erreicht"
        return ""

    def price(self, model: str) -> tuple[float, float]:
        prices = self.cfg.get("preise_usd_pro_mio_tokens") or {}
        if model in prices:
            return tuple(prices[model])
        # Unbekanntes Modell: vorsichtshalber mit dem teuersten bekannten Preis rechnen
        return max((tuple(p) for p in prices.values()), default=(2.0, 8.0))

    def model(self, task: str) -> str:
        return (self.cfg.get("modelle") or {}).get(task, "gpt-5.4-nano")

    # ---------- Aufruf ----------

    def call(self, task: str, instructions: str, prompt: str, *, web: bool = False, max_output: int = 4000) -> str:
        model = self.model(task)
        payload = {"model": model, "instructions": instructions, "input": prompt, "max_output_tokens": max_output}
        effort = (self.cfg.get("denkaufwand") or {}).get(task)
        if effort:
            payload["reasoning"] = {"effort": effort}
        if web:
            payload["tools"] = [{"type": "web_search"}]
        else:
            payload["text"] = {"format": {"type": "json_object"}}
        try:
            data = self._post(payload)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")
            # Nicht jedes Modell kennt den Denkaufwand: einmal ohne versuchen
            if exc.code == 400 and "reasoning" in payload and "reasoning" in detail:
                del payload["reasoning"]
                data = self._post(payload)
            else:
                raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}") from None

        usage = data.get("usage") or {}
        tokens_in, tokens_out = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
        searches = sum(1 for o in data.get("output", []) if o.get("type") == "web_search_call")
        p_in, p_out = self.price(model)
        cost = tokens_in * p_in / 1e6 + tokens_out * p_out / 1e6 + searches * float(self.cfg.get("websuche_usd_pro_aufruf", 0.01))
        self.state["spent_usd"] = round(self.state["spent_usd"] + cost, 6)
        self.log.append({"task": task, "model": model, "in": tokens_in, "out": tokens_out, "searches": searches,
                         "usd": round(cost, 5), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        print(f"KI {task}: {model}, {tokens_in}+{tokens_out} Tokens, {searches} Suchen, {cost:.4f} USD")

        text = "".join(c.get("text", "") for o in data.get("output", []) if o.get("type") == "message"
                       for c in o.get("content", []) if c.get("type") == "output_text")
        if not text.strip():
            raise RuntimeError(f"leere Antwort ({data.get('status')}, {data.get('incomplete_details')})")
        return text

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(API, data=json.dumps(payload).encode(), method="POST", headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read())

    # ---------- Aufgaben ----------

    def classify(self, items: list[dict]) -> str:
        """Ordnet Beiträge ohne KI-Einordnung ein (Feld «ai»: typ, rel). Gibt einen Hinweis zurück, falls etwas fehlte."""
        todo = [i for i in items if not i.get("ai")]
        todo.sort(key=lambda i: i["published"], reverse=True)
        todo = todo[: int(self.cfg.get("einordnung_max_pro_lauf", 300))]
        instructions = (
            "Du bewertest Beiträge für das Paid-Search-Team einer Schweizer Digitalagentur "
            "(Google Ads, Microsoft Ads, Shopping, Tracking und Messung, KI-Suche und ChatGPT Ads, Retail Media). "
            "Für jeden Beitrag: t = Typ, genau einer von " + ", ".join(TYPES) + ". "
            "Studie = eigene Erhebung, Report oder Umfrage; Kennzahlen = Benchmarks oder konkrete Zahlen im Zentrum; "
            "Best Practice = Anleitung, Tipps, Vorgehen; Diskussion = Frage oder Erfahrungsaustausch in einem Forum; "
            "sonst News. r = Relevanz 1 bis 5: 5 = muss das Team diese Woche wissen (neue Funktion, Änderung, "
            "starke Zahlen), 3 = nützlich, 1 = kein Bezug zu bezahlter Suche oder Werbung. "
            "Bewerte nur nach Titel und Anriss, erfinde nichts. "
            'Antworte als JSON: {"r": [{"n": Nummer, "t": "Typ", "r": Zahl}]}, ein Eintrag pro Beitrag.')
        missing = 0
        for start in range(0, len(todo), CHUNK):
            if self.unavailable():
                return self.unavailable()
            chunk = todo[start:start + CHUNK]
            lines = [f"[{n}] {i['title']} — {(i.get('snippet') or '')[:180]} ({i['source']})" for n, i in enumerate(chunk, 1)]
            try:
                answer = parse_json_answer(self.call("einordnung", instructions, "\n".join(lines), max_output=6000))
            except Exception as exc:
                print(f"Hinweis: Einordnung fehlgeschlagen ({exc})", file=sys.stderr)
                return f"Einordnung fehlgeschlagen: {str(exc)[:200]}"
            for row in answer.get("r") or []:
                try:
                    item = chunk[int(row["n"]) - 1]
                except (KeyError, ValueError, IndexError, TypeError):
                    continue
                typ = row.get("t") if row.get("t") in TYPES else None
                try:
                    rel = min(5, max(1, int(row.get("r"))))
                except (TypeError, ValueError):
                    rel = None
                if typ and rel:
                    item["ai"] = {"typ": typ, "rel": rel}
            missing += sum(1 for i in chunk if not i.get("ai"))
        return f"{missing} Beiträge ohne Einordnung" if missing else ""

    def briefing(self, label: str, pool: list[dict]) -> dict:
        """Lauftext und die drei wichtigsten Beiträge eines Tages; pool ist nach Relevanz sortiert."""
        lines = [f"[{n}] {i['title']} — {(i.get('snippet') or '')[:220]} ({i['source']}; {i.get('type', '')})"
                 for n, i in enumerate(pool, 1)]
        instructions = (
            "Du schreibst das Morgen-Briefing für Paid-Search-Spezialisten in einer Schweizer Agentur. "
            "Schreibe Schweizer Hochdeutsch (ss statt ß), sachlich, konkret, ohne Floskeln. "
            "Verwende nur, was in den Beiträgen steht; erfinde nichts und nenne keine Zahlen, die dort nicht stehen. "
            "Antworte als JSON: {\"text\": \"3 bis 4 Sätze Fliesstext: was ist passiert, wichtigste Entwicklung zuerst\", "
            "\"punkte\": [{\"nr\": Nummer des Beitrags, \"warum\": \"ein Satz, was das für Google-Ads-, "
            "Microsoft-Ads- oder Shopping-Kampagnen bedeutet oder worauf man achten sollte\"}]}. "
            "Wähle genau 3 Punkte, bevorzugt offizielle Ankündigungen, neue Funktionen, Änderungen und Studien.")
        answer = parse_json_answer(self.call("briefing", instructions, f"Beiträge vom {label}:\n" + "\n".join(lines)))
        points = []
        for point in answer.get("punkte") or []:
            try:
                nr = int(point.get("nr", 0))
            except (TypeError, ValueError):
                continue
            if 1 <= nr <= len(pool):
                points.append((pool[nr - 1], str(point.get("warum", "")).replace("ß", "ss")))
        return {"text": str(answer.get("text", "")).replace("ß", "ss").strip(), "points": points[:3]}

    def websearch_due(self) -> bool:
        last = self.state.get("last_websearch")
        days = float(self.cfg.get("websuche_alle_tage", 7))
        if days <= 0:  # 0 schaltet die Websuche ab
            return False
        if not last:
            return True
        return (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() >= days * 86400 - 3600

    def websearch(self, known_domains: set[str], topics: list[str]) -> list[dict]:
        """Sucht im Web nach neuen Veröffentlichungen; gibt Funde mit Titel, URL, Quelle, Datum, Typ, Relevanz zurück."""
        instructions = (
            "Du recherchierst für das Paid-Search-Team einer Schweizer Digitalagentur. Suche im Web nach Veröffentlichungen "
            "der letzten 7 Tage zu bezahlter Suche und Shopping-Werbung (Themen: " + ", ".join(topics) + "). "
            "Gesucht sind vor allem Studien, Benchmarks und Kennzahlen sowie Best Practices von Fachleuten, Tool-Anbietern "
            "und Beratungen (z.B. Gartner, McKinsey, BCG, Forrester, Think with Google, IAB), in Englisch oder Deutsch. "
            "Nur Seiten mit einem erkennbaren Veröffentlichungsdatum in den letzten 7 Tagen. Keine Stellenanzeigen, "
            "keine Produktwerbung, keine Seiten dieser Domains: " + ", ".join(sorted(known_domains)) + ". "
            "Erfinde keine Titel oder Links; nimm nur, was die Suche tatsächlich gefunden hat. "
            "Antworte nur mit JSON: {\"funde\": [{\"titel\": \"\", \"url\": \"\", \"quelle\": \"Name der Website\", "
            "\"datum\": \"JJJJ-MM-TT\", \"typ\": \"" + "|".join(TYPES) + "\", \"relevanz\": 1-5, "
            "\"anriss\": \"ein Satz auf Deutsch, worum es geht\"}]}, höchstens 15 Funde, die relevantesten zuerst.")
        text = self.call("websuche", instructions, "Was ist in den letzten 7 Tagen erschienen?", web=True, max_output=8000)
        self.state["last_websearch"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        found = []
        for row in parse_json_answer(text).get("funde") or []:
            url = str(row.get("url", "")).strip()
            if not url.startswith("http"):
                continue
            try:
                rel = min(5, max(1, int(row.get("relevanz"))))
            except (TypeError, ValueError):
                rel = 3
            found.append({"title": str(row.get("titel", "")).strip(), "url": url, "source": str(row.get("quelle", "")).strip(),
                          "date": str(row.get("datum", ""))[:10], "typ": row.get("typ") if row.get("typ") in TYPES else "News",
                          "rel": rel, "snippet": str(row.get("anriss", "")).replace("ß", "ss").strip()})
        return found
