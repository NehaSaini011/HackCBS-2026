import re
import time

import httpx
import psycopg

from agent import config, evidence

NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
TEST_PARAMS = [62]     # customer 62: the demo customer Person 1's prover uses


def candidate_shapes(target: dict) -> list[str]:
    """Fixes to try when there is no lesson. All come from the approved template."""
    return ["filter_then_sort_desc", "filter_only"] if target.get("sort_col") else ["filter_only"]


def shape_of(sql: str) -> str:
    return "filter_then_sort_desc" if " DESC)" in sql else "filter_only"


def build(shape: str, target: dict) -> dict:
    """Fill the create_index template with this company's own names. No AI involved."""
    t, f, s = target["table"], target["filter_col"], target.get("sort_col")
    for name in [t, f] + ([s] if s else []):
        if not NAME.match(name):
            raise ValueError(f"Unsafe name: {name!r}")
    if shape == "filter_then_sort_desc" and s:
        cols, idx = f"{f}, {s} DESC", f"idx_fix_{t}_{f}_{s}"
    else:
        cols, idx = f, f"idx_fix_{t}_{f}"
    order = f" ORDER BY {s} DESC" if s else ""
    return {"template": "create_index",
            "sql": f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx[:63]} ON {t} ({cols})",
            "test_sql": f"SELECT 1 FROM {t} WHERE {f} = %s{order} LIMIT 20",
            "params": TEST_PARAMS}


def prove(fix: dict) -> dict:
    """Ask Person 1's fork prover (contract C6). Never raises: failure = passed False."""
    if config.FAKE_PROVER:          # until the prover is up; shows as method "fake"
        time.sleep(5)
        after = 45.0 if shape_of(fix["sql"]) == "filter_then_sort_desc" else 60.0
        return {"method": "fake", "fix_sql": fix["sql"], "before_p95_ms": 2100.0,
                "after_p95_ms": after, "passed": True}
    try:
        r = httpx.post(config.PROVER_URL, timeout=300,     # forks are slow: allow 5 minutes
                       headers={"X-Prover-Token": config.PROVER_TOKEN},
                       json={"shop": config.SHOP, "fix_sql": fix["sql"],
                             "test_sql": fix["test_sql"], "params": fix["params"]})
        r.raise_for_status()
        res = r.json()
    except Exception as e:
        return {"method": "fork", "fix_sql": fix["sql"], "passed": False,
                "error": f"Could not test: {e}"[:300]}
    return {"method": "fork", "fix_sql": fix["sql"], "passed": bool(res.get("passed")),
            "before_p95_ms": res.get("before_p95_ms"), "after_p95_ms": res.get("after_p95_ms"),
            "error": res.get("error"), "fork_id": res.get("fork_id")}


def prove_shapes(shapes: list[str], target: dict):
    """Prove each shape in turn. Returns (passing [(fix, proof)], last (fix, proof) or None)."""
    passing, last = [], None
    for shape in shapes:
        fix = build(shape, target)
        proof = prove(fix)
        print(f"  proof {shape}: passed={proof['passed']} "
              f"{proof.get('before_p95_ms')} -> {proof.get('after_p95_ms')} ms {proof.get('error') or ''}")
        last = (fix, proof)
        if proof["passed"]:
            passing.append((fix, proof))
    return passing, last


def apply(sql: str) -> None:
    """Run an APPROVED fix with the write user. Only our own template is accepted."""
    if not sql.startswith("CREATE INDEX CONCURRENTLY IF NOT EXISTS "):
        raise ValueError("Not an approved fix template")
    idx = sql.split()[6]
    if not NAME.match(idx):
        raise ValueError("Unsafe index name")
    # CONCURRENTLY cannot run inside a transaction, hence autocommit
    with psycopg.connect(config.SHOP_WRITE_URL, autocommit=True) as conn:
        conn.execute("SET statement_timeout = '10min'")
        conn.execute(sql)
        ok = conn.execute("SELECT i.indisvalid FROM pg_index i JOIN pg_class c "
                          "ON c.oid = i.indexrelid WHERE c.relname = %s", (idx,)).fetchone()
        if not ok or not ok[0]:
            # A failed concurrent build leaves an invalid index that IF NOT EXISTS would skip forever
            conn.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {idx}")
            raise RuntimeError("Index build failed and was cleaned up; approve again to retry")


def verify(endpoint: str | None, threshold_ms: float = 500, wait_s: int = 120):
    """Wait until real traffic is fast again. Returns (recovered, latest p95)."""
    if not endpoint:
        return True, None
    deadline, p95 = time.monotonic() + wait_s, None
    while time.monotonic() < deadline:
        time.sleep(10)                      # the shop writes request_metrics every 5 s
        p95 = evidence.recent_p95(endpoint, seconds=20)
        if p95 is not None and p95 < threshold_ms:
            return True, p95
    return False, p95
