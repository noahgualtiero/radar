// API von Radar (Cloudflare Pages Function mit Datenbank D1 unter env.DB).
//
// Wer angemeldet ist, sagt Cloudflare Access: Jede Anfrage trägt ein signiertes Token
// (Cf-Access-Jwt-Assertion) mit der E-Mail. Ohne gültiges Token gibt es keine Antwort.
// Lokal (wrangler pages dev) ersetzt DEV_USER aus .dev.vars die Anmeldung.
//
// Quellen wählt jede Person für sich: Standardquellen sind für alle an, jede Person kann sie für
// sich ausschalten und weitere aufnehmen. Abgerufen werden alle Quellen, die jemand nutzt; das
// Briefing entsteht aus allen.
//
//   GET  /api/state       eigene Votes und Quellen, Team-Zahlen pro Artikel, Gemerkt (eigenes und
//                         vom Team), Vorschläge
//   POST /api/vote        {id, value: 1 | -1 | 0, source, domain, kind}
//   POST /api/click       {id, source, domain, kind}
//   POST /api/save        {id, item | null}
//   POST /api/my-source   {source, on: true | false}   Quelle im eigenen Feed an- oder ausschalten
//   POST /api/suggestion  {key, action: "accept" | "dismiss"}
//   POST /api/config      {op, ...}  Quelle aufnehmen, Themen, Suchbegriffe, Regeln

const WINDOW_DAYS = 45;          // Votes und Klicks, die für Zahlen und Reihenfolge zählen
const DAY = 864e5;
const KINDS = ["feed", "entdecken"];

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
const iso = (offsetDays = 0) => new Date(Date.now() + offsetDays * DAY).toISOString();
const hostOf = (url) => { try { return new URL(url).hostname.replace(/^www\./, "").toLowerCase(); } catch (e) { return ""; } };
const text = (v, max = 300) => String(v ?? "").trim().slice(0, max);
// Ist eine Quelle im Feed dieser Person? Eigene Wahl vor Standard
const inFeed = (q, mine) => (mine[q.name] === 1 ? true : mine[q.name] === -1 ? false : q.standard !== false);

export async function onRequest(context) {
  const { request, env, params } = context;
  const path = (params.path || []).join("/");
  let me;
  try {
    me = await currentUser(request, env);
  } catch (e) {
    return json({ error: "Nicht angemeldet" }, 401);
  }
  try {
    if (request.method === "GET" && path === "state") return json(await state(env, me));
    if (request.method !== "POST") return json({ error: "Unbekannt" }, 404);
    const body = await request.json();
    if (path === "vote") return json(await vote(env.DB, me, body));
    if (path === "click") return json(await click(env.DB, me, body));
    if (path === "save") return json(await save(env.DB, me, body));
    if (path === "my-source") return json(await mySource(context, me, body));
    if (path === "suggestion") return json(await answerSuggestion(context, me, body));
    if (path === "config") return json(await editConfig(context, me, body));
    return json({ error: "Unbekannt" }, 404);
  } catch (e) {
    return json({ error: String(e.message || e) }, e.status || 500);
  }
}

function fail(message, status = 400) {
  const e = new Error(message);
  e.status = status;
  return e;
}

// ---------- Anmeldung über Cloudflare Access ----------

let certCache = { at: 0, keys: [] };

async function currentUser(request, env) {
  if (env.DEV_USER) return env.DEV_USER.toLowerCase();
  const token = request.headers.get("cf-access-jwt-assertion");
  if (!token || !env.ACCESS_TEAM_DOMAIN) throw new Error("kein Access-Token");
  const [h, p, s] = token.split(".");
  const header = JSON.parse(b64text(h)), payload = JSON.parse(b64text(p));
  // Mit ACCESS_AUD gilt nur das Token dieser Application; ohne genügt ein gültiges Token des Teams
  const aud = [].concat(payload.aud || []);
  if ((env.ACCESS_AUD && !aud.includes(env.ACCESS_AUD)) || payload.exp * 1000 < Date.now()) throw new Error("Token ungültig");
  const issuer = "https://" + env.ACCESS_TEAM_DOMAIN.replace(/^https?:\/\//, "");
  if (payload.iss && payload.iss !== issuer) throw new Error("Token von fremdem Team");
  const key = (await accessKeys(env.ACCESS_TEAM_DOMAIN)).find((k) => k.kid === header.kid);
  if (!key) throw new Error("Schlüssel unbekannt");
  const pub = await crypto.subtle.importKey("jwk", key, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", pub, b64bytes(s), new TextEncoder().encode(h + "." + p));
  if (!ok || !payload.email) throw new Error("Signatur ungültig");
  return payload.email.toLowerCase();
}

async function accessKeys(team) {
  if (Date.now() - certCache.at < 36e5 && certCache.keys.length) return certCache.keys;
  const res = await fetch(`https://${team.replace(/^https?:\/\//, "")}/cdn-cgi/access/certs`);
  certCache = { at: Date.now(), keys: (await res.json()).keys || [] };
  return certCache.keys;
}

function b64bytes(s) {
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(s.length / 4) * 4, "="));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}
const b64text = (s) => new TextDecoder().decode(b64bytes(s));

// ---------- Lesen ----------

async function state(env, me) {
  const db = env.DB, since = iso(-WINDOW_DAYS);
  const [counts, clicks, mine, saved, teamSaved, config, sources] = await Promise.all([
    db.prepare(`SELECT article_id, SUM(value > 0) AS up, SUM(value < 0) AS down,
                SUM(CASE WHEN value > 0 AND user <> ?1 THEN 1 ELSE 0 END) AS team
                FROM votes WHERE created_at >= ?2 GROUP BY article_id`).bind(me, since).all(),
    db.prepare("SELECT article_id, COUNT(*) AS n FROM clicks WHERE created_at >= ? GROUP BY article_id").bind(since).all(),
    db.prepare("SELECT article_id, value FROM votes WHERE user = ?").bind(me).all(),
    db.prepare("SELECT data FROM saved WHERE user = ? ORDER BY created_at DESC").bind(me).all(),
    // Was andere gemerkt haben: pro Artikel einmal, mit Anzahl Personen, ohne Namen
    db.prepare(`SELECT article_id, COUNT(*) AS n, MAX(created_at) AS last, MAX(data) AS data FROM saved
                WHERE user <> ? GROUP BY article_id ORDER BY last DESC LIMIT 150`).bind(me).all(),
    loadConfig(env),
    mySources(db, me),
  ]);
  const articles = {};
  for (const r of counts.results) articles[r.article_id] = { up: r.up, down: r.down, team: r.team, clicks: 0 };
  for (const r of clicks.results) (articles[r.article_id] ||= { up: 0, down: 0, team: 0, clicks: 0 }).clicks = r.n;
  return {
    me,
    articles,
    votes: Object.fromEntries(mine.results.map((r) => [r.article_id, r.value])),
    saved: saved.results.map((r) => JSON.parse(r.data)),
    teamSaved: teamSaved.results.map((r) => Object.assign(JSON.parse(r.data), { team: r.n, saved: r.last })),
    sources,
    suggestions: config ? await suggestions(db, config, me, sources) : [],
    autoRebuild: !!(env.GITHUB_TOKEN && env.GITHUB_REPO),
  };
}

async function mySources(db, me) {
  const rows = await db.prepare("SELECT source, value FROM user_sources WHERE user = ?").bind(me).all();
  return Object.fromEntries(rows.results.map((r) => [r.source, r.value]));
}

// Vorschläge für die eigene Quellenwahl: Websites, deren Suchfunde ich oft öffne oder hochvote,
// aufnehmen; Quellen, die ich meist negativ bewerte oder nie öffne, ausschalten.
// Schwellen stehen in den Einstellungen unter «vorschlaege».
async function suggestions(db, config, me, mine) {
  const rules = config.vorschlaege || {};
  const minAdd = +(rules.aufnehmen_ab_artikeln ?? 3);
  const minVotes = +(rules.entfernen_ab_votes ?? 3);
  const idleDays = +(rules.entfernen_ohne_klick_tage ?? 60);
  const since = iso(-30);
  const [dismissed, interest, verdict, lastClicks, first] = await Promise.all([
    db.prepare("SELECT key FROM dismissed WHERE user = ? AND until > ?").bind(me, iso()).all(),
    // Suchfunde, die ich geöffnet oder hochgevotet habe, nach Domain
    db.prepare(`SELECT domain, MAX(source) AS name, COUNT(DISTINCT article_id) AS n FROM (
                  SELECT article_id, domain, source FROM clicks WHERE user = ?1 AND kind = 'entdecken' AND created_at >= ?2
                  UNION ALL
                  SELECT article_id, domain, source FROM votes WHERE user = ?1 AND kind = 'entdecken' AND value > 0 AND created_at >= ?2)
                GROUP BY domain HAVING n >= ?3 ORDER BY n DESC`).bind(me, since, minAdd).all(),
    db.prepare(`SELECT source, COUNT(*) AS n, SUM(value) AS total FROM votes
                WHERE user = ? AND kind = 'feed' AND created_at >= ? GROUP BY source`).bind(me, since).all(),
    db.prepare("SELECT source, MAX(created_at) AS last FROM clicks WHERE user = ? AND kind = 'feed' GROUP BY source").bind(me).all(),
    db.prepare("SELECT MIN(created_at) AS first FROM clicks WHERE user = ?").bind(me).first(),
  ]);
  const skip = new Set(dismissed.results.map((r) => r.key));
  const ignored = (config.suchen?.ignorieren || []).map((d) => String(d).toLowerCase());
  const active = (config.quellen || []).filter((q) => q.aktiv !== false);
  const myHosts = new Set(active.filter((q) => inFeed(q, mine)).map((q) => hostOf(q.url)));
  const out = [];

  for (const r of interest.results) {
    const key = "add:" + r.domain;
    if (skip.has(key) || myHosts.has(r.domain) || ignored.some((d) => r.domain === d || r.domain.endsWith("." + d))) continue;
    out.push({ key, kind: "add", domain: r.domain, name: r.name,
      text: `Du hast ${r.n} Artikel von ${r.name} geöffnet oder hochgevotet – in deinen Feed aufnehmen?` });
  }

  const byVerdict = Object.fromEntries(verdict.results.map((r) => [r.source, r]));
  const lastClick = Object.fromEntries(lastClicks.results.map((r) => [r.source, r.last]));
  const usedLongEnough = first?.first && first.first < iso(-idleDays);
  for (const q of active) {
    const key = "remove:" + q.name;
    if (skip.has(key) || !inFeed(q, mine)) continue;
    const v = byVerdict[q.name];
    if (v && v.n >= minVotes && v.total < 0) {
      out.push({ key, kind: "remove", source: q.name,
        text: `Du hast ${q.name} zuletzt meist negativ bewertet – aus deinem Feed nehmen?` });
      continue;
    }
    const recent = q.seit && q.seit > iso(-idleDays);
    if (usedLongEnough && !recent && !(lastClick[q.name] > iso(-idleDays))) {
      out.push({ key, kind: "remove", source: q.name,
        text: `Du hast ${q.name} seit ${idleDays} Tagen nicht geöffnet – aus deinem Feed nehmen?` });
    }
  }
  return out.slice(0, 3);
}

// ---------- Schreiben ----------

function article(body) {
  const id = text(body.id, 600);
  if (!id) throw fail("id fehlt");
  return { id, source: text(body.source, 200), domain: text(body.domain, 200).toLowerCase(), kind: KINDS.includes(body.kind) ? body.kind : "feed" };
}

async function vote(db, me, body) {
  const a = article(body), value = Math.sign(+body.value || 0);
  if (!value) {
    await db.prepare("DELETE FROM votes WHERE article_id = ? AND user = ?").bind(a.id, me).run();
  } else {
    await db.prepare(`INSERT INTO votes (article_id, user, value, source, domain, kind, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)
                      ON CONFLICT (article_id, user) DO UPDATE SET value = excluded.value, created_at = excluded.created_at`)
      .bind(a.id, me, value, a.source, a.domain, a.kind, iso()).run();
  }
  return { ok: true };
}

async function click(db, me, body) {
  const a = article(body);
  await db.prepare("INSERT OR IGNORE INTO clicks (article_id, user, source, domain, kind, created_at) VALUES (?, ?, ?, ?, ?, ?)")
    .bind(a.id, me, a.source, a.domain, a.kind, iso()).run();
  return { ok: true };
}

async function save(db, me, body) {
  const id = text(body.id, 600);
  if (!id) throw fail("id fehlt");
  if (!body.item) {
    await db.prepare("DELETE FROM saved WHERE user = ? AND article_id = ?").bind(me, id).run();
  } else {
    const data = JSON.stringify(body.item);
    if (data.length > 8000) throw fail("Artikel zu gross");
    await db.prepare("INSERT OR REPLACE INTO saved (user, article_id, data, created_at) VALUES (?, ?, ?, ?)")
      .bind(me, id, data, body.item.saved || iso()).run();
  }
  return { ok: true };
}

async function setMySource(db, me, name, value) {
  await db.prepare(`INSERT INTO user_sources (user, source, value, created_at) VALUES (?, ?, ?, ?)
                    ON CONFLICT (user, source) DO UPDATE SET value = excluded.value, created_at = excluded.created_at`)
    .bind(me, name, value, iso()).run();
}

// Quelle im eigenen Feed an- oder ausschalten. Eine selbst aufgenommene Quelle, die niemand mehr
// nutzt, wird nicht mehr abgerufen; schaltet sie jemand wieder an, läuft sie wieder.
async function mySource(context, me, body) {
  const db = context.env.DB, config = await loadConfig(context.env);
  const q = (config?.quellen || []).find((s) => s.name === body.source);
  if (!q) throw fail("Quelle unbekannt", 404);
  const on = !!body.on;
  await setMySource(db, me, q.name, on ? 1 : -1);
  if (q.standard === false) {
    const users = await db.prepare("SELECT COUNT(*) AS n FROM user_sources WHERE source = ? AND value = 1").bind(q.name).first();
    const wanted = users.n > 0;
    if (wanted === (q.aktiv === false)) {
      if (wanted) delete q.aktiv; else q.aktiv = false;
      await storeConfig(context, me, config, "", wanted);
    }
  }
  return { ok: true, message: on ? `${q.name} ist in deinem Feed.` : `${q.name} ist aus deinem Feed.` };
}

// ---------- Einstellungen ----------

// Die Einstellungen liegen in D1. Vor der ersten Änderung gibt es dort noch nichts: dann gilt
// config.json, die der Abruf aus sources.yaml mit auf die Seite legt.
async function loadConfig(env) {
  const row = await env.DB.prepare("SELECT value FROM config WHERE key = 'main'").first();
  if (row) return JSON.parse(row.value);
  try {
    const res = await env.ASSETS.fetch(new Request("https://radar.local/config.json"));
    return res.ok ? await res.json() : null;
  } catch (e) {
    return null;
  }
}

async function storeConfig(context, me, config, summary, rebuildWanted = true) {
  const { env } = context;
  await env.DB.prepare(`INSERT INTO config (key, value, updated_at, updated_by) VALUES ('main', ?, ?, ?)
                        ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at, updated_by = excluded.updated_by`)
    .bind(JSON.stringify(config), iso(), me).run();
  // Neuen Abruf anstossen, damit die Änderung in wenigen Minuten sichtbar ist (optional)
  let rebuild = false;
  if (rebuildWanted && env.GITHUB_TOKEN && env.GITHUB_REPO) {
    const res = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/build.yml/dispatches`, {
      method: "POST",
      headers: { authorization: `Bearer ${env.GITHUB_TOKEN}`, accept: "application/vnd.github+json", "user-agent": "radar" },
      body: JSON.stringify({ ref: "main" }),
    });
    rebuild = res.ok;
  }
  return { ok: true, message: summary, rebuild };
}

// Kommagetrennte Liste; ein Wort in Anführungszeichen behält seine Leerzeichen (" rsa " trifft nicht "Versa")
function keywords(value) {
  const out = [];
  for (const m of String(value || "").matchAll(/"([^"]*)"|([^,\n]+)/g)) {
    const w = m[1] !== undefined ? m[1] : m[2].trim();
    if (w.trim()) out.push(w);
  }
  return out.slice(0, 60);
}

async function editConfig(context, me, body) {
  const config = await loadConfig(context.env);
  if (!config) throw fail("Noch keine Einstellungen vorhanden – zuerst einen Abruf laufen lassen.", 409);
  config.quellen ||= []; config.themen ||= []; config.suchen ||= {}; config.suchen.begriffe ||= [];
  const today = iso().slice(0, 10);
  let summary;
  switch (body.op) {
    case "source_add": {
      // Jede Person darf aufnehmen; die Quelle landet in ihrem Feed, für andere bleibt sie aus,
      // bis sie sie selbst anschalten
      const url = text(body.url, 500);
      if (!/^https?:\/\//.test(url)) throw fail("Keine gültige URL");
      const host = hostOf(url);
      const existing = config.quellen.find((q) => q.url === url || hostOf(q.url) === host);
      if (existing) {
        await setMySource(context.env.DB, me, existing.name, 1);
        if (existing.aktiv !== false) return { ok: true, message: `${existing.name} ist in deinem Feed.`, rebuild: false };
        delete existing.aktiv;
        summary = `${existing.name} ist in deinem Feed und wird wieder abgerufen.`;
        break;
      }
      const cats = config.kategorien || [];
      const name = text(body.name, 80) || host;
      config.quellen.push({ name, url, kategorie: cats.includes(body.kategorie) ? body.kategorie : "News", seit: today, standard: false, von: me });
      await setMySource(context.env.DB, me, name, 1);
      summary = `${name} aufgenommen. Den Feed sucht der nächste Abruf.`;
      break;
    }
    case "topic_save": {
      const name = text(body.name, 60);
      if (!name) throw fail("Name fehlt");
      const words = keywords(body.stichwoerter);
      if (!words.length) throw fail("Mindestens ein Stichwort nötig");
      const gewicht = Math.min(3, Math.max(1, +body.gewicht || 1));
      const t = config.themen.find((x) => x.name === name);
      if (t) Object.assign(t, { gewicht, stichwoerter: words }); else config.themen.push({ name, gewicht, stichwoerter: words });
      summary = `Thema ${name} gespeichert.`;
      break;
    }
    case "topic_remove":
      config.themen = config.themen.filter((t) => t.name !== body.name);
      summary = `Thema ${body.name} entfernt.`;
      break;
    case "search_add": {
      const term = text(body.term, 200);
      if (!term) throw fail("Begriff fehlt");
      if (!config.suchen.begriffe.includes(term)) config.suchen.begriffe.push(term);
      summary = `Suchbegriff ${term} hinzugefügt.`;
      break;
    }
    case "search_remove":
      config.suchen.begriffe = config.suchen.begriffe.filter((t) => t !== body.term);
      summary = `Suchbegriff ${body.term} entfernt.`;
      break;
    case "rules_save":
      config.regeln = {
        min_woerter: Math.min(30, Math.max(0, +body.min_woerter || 0)),
        mindest_gewicht: Math.min(3, Math.max(0, +body.mindest_gewicht || 0)),
        stellenanzeigen_ausblenden: !!body.stellenanzeigen_ausblenden,
        ausschliessen: keywords(body.ausschliessen).map((w) => w.trim()),
      };
      summary = "Regeln gespeichert.";
      break;
    default:
      throw fail("Unbekannte Änderung");
  }
  return storeConfig(context, me, config, summary);
}

async function answerSuggestion(context, me, body) {
  const db = context.env.DB, key = text(body.key, 300);
  if (!/^(add|remove):/.test(key)) throw fail("Vorschlag unbekannt");
  const until = body.action === "dismiss" ? iso(90) : iso(3650);
  await db.prepare("INSERT OR REPLACE INTO dismissed (user, key, until) VALUES (?, ?, ?)").bind(me, key, until).run();
  if (body.action === "dismiss") return { ok: true, message: "Ausgeblendet für 90 Tage." };
  const [kind, value] = [key.slice(0, key.indexOf(":")), key.slice(key.indexOf(":") + 1)];
  if (kind === "add") return editConfig(context, me, { op: "source_add", url: "https://" + value, name: text(body.name, 80) || value, kategorie: "News" });
  return mySource(context, me, { source: value, on: false });
}
