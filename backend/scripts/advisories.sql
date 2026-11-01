-- Platform advisories: fixes for GLOBAL problems (a PHP-wide CVE, a Postgres bug...)
-- published by us, the service provider, without waiting for any company to hit it first.
-- Run once:  psql "$YB_URL" -f scripts/advisories.sql
CREATE TABLE IF NOT EXISTS advisories (
  id           TEXT PRIMARY KEY,         -- 'adv_3f2a9c1b'
  title        TEXT NOT NULL,
  category     TEXT NOT NULL,            -- 'security', 'database', 'runtime'...
  severity     TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
  affects      JSONB NOT NULL DEFAULT '[]',   -- stack keywords, e.g. ["php"], or ["*"] for everyone
  summary      TEXT NOT NULL,
  fix          TEXT NOT NULL,
  mitigation   TEXT,
  source_url   TEXT,
  meko_ref     TEXT,                     -- the shared memory in Meko, when stored
  published_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
