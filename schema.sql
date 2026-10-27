-- Datenbank von Radar (Cloudflare D1). Einmal ausführen:
--   npx wrangler d1 execute radar --remote --file schema.sql
-- Lokal zum Testen:  npx wrangler d1 execute radar --local --file schema.sql

-- Daumen hoch (1) oder runter (-1), pro Person und Artikel einmal
CREATE TABLE IF NOT EXISTS votes (
  article_id TEXT NOT NULL,
  user       TEXT NOT NULL,
  value      INTEGER NOT NULL,
  source     TEXT NOT NULL,
  domain     TEXT NOT NULL,
  kind       TEXT NOT NULL,          -- feed (feste Quelle) oder entdecken (Suchfund)
  created_at TEXT NOT NULL,
  PRIMARY KEY (article_id, user)
);

-- Geöffnete Artikel, pro Person und Artikel einmal gezählt
CREATE TABLE IF NOT EXISTS clicks (
  article_id TEXT NOT NULL,
  user       TEXT NOT NULL,
  source     TEXT NOT NULL,
  domain     TEXT NOT NULL,
  kind       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (article_id, user)
);

-- Gemerkt, pro Person; data hält den Artikel, damit er auch nach 30 Tagen noch da ist
CREATE TABLE IF NOT EXISTS saved (
  user       TEXT NOT NULL,
  article_id TEXT NOT NULL,
  data       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user, article_id)
);

-- Beantwortete Vorschläge («aufnehmen?», «entfernen?») erscheinen bis «until» nicht wieder
CREATE TABLE IF NOT EXISTS dismissed (
  key   TEXT PRIMARY KEY,
  until TEXT NOT NULL
);

-- Einstellungen (Quellen, Themen, Regeln, Suchen, KI) als ein JSON-Dokument unter key 'main'
CREATE TABLE IF NOT EXISTS config (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);

CREATE INDEX IF NOT EXISTS votes_created ON votes (created_at);
CREATE INDEX IF NOT EXISTS clicks_created ON clicks (created_at);
