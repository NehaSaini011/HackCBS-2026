"""Improvement 3: seed the lesson library with four lessons from REAL public postmortems.

    python -m scripts.seed_lessons        (from backend/, with .env loaded)

Safe to run again: it updates the four rows instead of duplicating them.

Status 'seeded' + source 'postmortem' means: shown in the lesson library as outside
knowledge, but never offered as a fix by /lessons/match (that only returns 'proven'
lessons, i.e. ones a company in the group has proven on its own database).
Like every shared lesson, they hold no table names, column names or SQL.
"""
import psycopg
from psycopg.types.json import Jsonb

from app.settings import settings

GROUP_ID = "g_fund1"

LESSONS = [
    {
        "id": "les_5eed0001",
        "cause_class": "LOCK_CONTENTION",
        "symptoms": ["every query on one table waits", "a migration waits for a lock",
                     "long-running queries hold the table", "database connection slots run out"],
        "fix_template": "lock_timeout_migration",
        "fix_description": ("Run schema migrations with a short lock timeout, so a blocked migration fails in "
                            "seconds instead of queueing every query behind it; alert on hours-long queries and "
                            "find the blocking session before retrying. Public postmortem: LLM Gateway, "
                            "19 Oct 2026 (dashboard and API down 48 min)."),
    },
    {
        "id": "les_5eed0002",
        "cause_class": "MISSING_INDEX",
        "symptoms": ["p95 latency spike", "indexes stop being used after a schema change",
                     "part of API requests fail"],
        "fix_template": "check_plans_before_schema_change",
        "fix_description": ("Before changing a column's collation or type, compare the query plans of the hot "
                            "queries before and after on a copy of the database; if their indexes stop being "
                            "used, revert the change or rebuild the indexes. Public postmortem: Autumn, "
                            "15 Mar 2026 (about 10% of API requests failed for 75 min)."),
    },
    {
        "id": "les_5eed0003",
        "cause_class": "LOCK_CONTENTION",
        "symptoms": ["a rollback waits for a lock", "active queries hold the table",
                     "the outage lasts longer than the bad change"],
        "fix_template": "lock_timeout_migration",
        "fix_description": ("A rollback that alters a table needs the same locks as the change it undoes: plan "
                            "the rollback in advance, run it with a lock timeout, and clear or wait out the "
                            "queries holding the table first. Public postmortem: Autumn, 15 Mar 2026."),
    },
    {
        "id": "les_5eed0004",
        "cause_class": "LOCK_CONTENTION",
        "symptoms": ["lock wait timeouts for users", "a large data migration is running",
                     "all users affected"],
        "fix_template": "batched_migration",
        "fix_description": ("Split large data migrations into small batches, or run them in a quiet maintenance "
                            "window, so they never hold locks long enough to block user traffic. Public "
                            "postmortem: Open Build Service, 29 Jan 2026 (all users affected for about "
                            "1 h 45 min)."),
    },
]

SQL = """
INSERT INTO lessons (id, group_id, cause_class, symptoms, fix_template, fix_shape,
                     fix_description, status, source, confirmations, failures, created_by)
VALUES (%s, %s, %s, %s, %s, NULL, %s, 'seeded', 'postmortem', 0, 0, NULL)
ON CONFLICT (id) DO UPDATE SET
  cause_class = EXCLUDED.cause_class, symptoms = EXCLUDED.symptoms,
  fix_template = EXCLUDED.fix_template, fix_description = EXCLUDED.fix_description,
  status = 'seeded', source = 'postmortem'
"""

with psycopg.connect(settings.yb_url) as conn:
    for les in LESSONS:
        conn.execute(SQL, (les["id"], GROUP_ID, les["cause_class"], Jsonb(les["symptoms"]),
                           les["fix_template"], les["fix_description"]))
    rows = conn.execute("SELECT id, cause_class, status, source FROM lessons "
                        "WHERE source = 'postmortem' ORDER BY id").fetchall()

for r in rows:
    print(*r)
print(f"{len(rows)} postmortem lessons in the library")
