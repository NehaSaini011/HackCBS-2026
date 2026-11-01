CREATE TABLE IF NOT EXISTS groups (
  id   TEXT PRIMARY KEY,                 -- 'g_fund1'
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS companies (
  id         TEXT PRIMARY KEY,           -- 'c_pinecart'
  group_id   TEXT NOT NULL REFERENCES groups(id),
  name       TEXT NOT NULL,              -- 'Pinecart'
  shop       TEXT UNIQUE,                -- Person 1's shop letter: 'a'
  tech_stack TEXT
);

CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,           -- bcrypt hash, never the password
  role          TEXT NOT NULL CHECK (role IN ('group_admin', 'engineer')),
  group_id      TEXT NOT NULL REFERENCES groups(id),
  company_id    TEXT REFERENCES companies(id),
  CHECK (role = 'group_admin' OR company_id IS NOT NULL)   -- engineers must have a company
);

CREATE TABLE IF NOT EXISTS api_keys (
  key_hash   TEXT PRIMARY KEY,           -- sha256 of the key, never the key
  company_id TEXT NOT NULL REFERENCES companies(id),
  label      TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lessons (
  id              TEXT PRIMARY KEY,      -- 'les_041'
  group_id        TEXT NOT NULL REFERENCES groups(id),
  cause_class     TEXT NOT NULL,         -- 'MISSING_INDEX'
  symptoms        JSONB NOT NULL DEFAULT '[]',
  fix_template    TEXT NOT NULL,         -- 'create_index'
  fix_shape       TEXT,                  -- 'filter_then_sort_desc'
  fix_description TEXT NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('seeded', 'proven', 'failed', 'needs_review')),
  source          TEXT NOT NULL CHECK (source IN ('agent', 'postmortem')),
  confirmations   INT NOT NULL DEFAULT 0,
  failures        INT NOT NULL DEFAULT 0,
  meko_ref        TEXT,                  -- id of the memory in Meko
  created_by      TEXT REFERENCES companies(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lesson_events (
  id            TEXT PRIMARY KEY,
  lesson_id     TEXT NOT NULL REFERENCES lessons(id),
  company_id    TEXT NOT NULL REFERENCES companies(id),
  incident_id   TEXT,
  result        TEXT NOT NULL CHECK (result IN ('created', 'confirmed', 'failed')),
  before_p95_ms DOUBLE PRECISION,
  after_p95_ms  DOUBLE PRECISION,
  at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk_exposure (
  company_id TEXT NOT NULL REFERENCES companies(id),
  risk_type  TEXT NOT NULL,              -- the test name: 'missing_index', 'latency'...
  group_id   TEXT NOT NULL,
  status     TEXT NOT NULL CHECK (status IN ('open', 'pushed', 'resolved')),
  finding_id TEXT,
  lesson_id  TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (company_id, risk_type)    -- one row per company per risk
);

CREATE TABLE IF NOT EXISTS audit_log (
  id         TEXT PRIMARY KEY,
  at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor      TEXT NOT NULL,              -- email, or 'agent:c_tealbox'
  action     TEXT NOT NULL,              -- 'approve', 'reject', 'push', 'apply', 'meko_mode'
  company_id TEXT,
  target_id  TEXT,
  details    JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value JSONB NOT NULL
);

-- Used only while MEKO_BACKEND=mock, so you can build before Meko works
CREATE TABLE IF NOT EXISTS meko_mock (
  id         TEXT PRIMARY KEY,
  company_id TEXT,
  shared     BOOLEAN NOT NULL DEFAULT false,
  content    TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO settings (key, value) VALUES ('meko_mode', '"on"')
ON CONFLICT (key) DO NOTHING;