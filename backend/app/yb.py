import secrets

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb      # wrap Python dicts/lists before saving to JSONB
from psycopg_pool import ConnectionPool

from app.settings import settings

# A pool keeps a few connections open and lends them out. open=False: the app
# opens it when it starts (Step 5). dict_row: each row comes back as a dict.
pool = ConnectionPool(settings.yb_url, min_size=1, max_size=5, open=False,
                      kwargs={"row_factory": dict_row})


def q(sql: str, params: tuple = ()) -> list[dict]:
    """Run a query that returns rows (SELECT, or INSERT ... RETURNING)."""
    with pool.connection() as conn:          # commits when the block ends without error
        return conn.execute(sql, params).fetchall()


def q1(sql: str, params: tuple = ()) -> dict | None:
    """Same as q, but only the first row (or None)."""
    rows = q(sql, params)
    return rows[0] if rows else None


def run(sql: str, params: tuple = ()) -> None:
    """Run a write that returns nothing (INSERT, UPDATE, DELETE)."""
    with pool.connection() as conn:
        conn.execute(sql, params)


def new_id(prefix: str) -> str:
    """Short random ids such as 'les_9f3a1c2b'."""
    return f"{prefix}_{secrets.token_hex(4)}"


def audit(actor: str, action: str, company_id: str | None, target_id: str | None,
          details: dict | None = None) -> None:
    run("INSERT INTO audit_log (id, actor, action, company_id, target_id, details) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (new_id("aud"), actor, action, company_id, target_id, Jsonb(details or {})))


def get_setting(key: str, default=None):
    row = q1("SELECT value FROM settings WHERE key = %s", (key,))
    return row["value"] if row else default