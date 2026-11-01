
import json
import os
import statistics

import psycopg


INDEX_NAME = "idx_orders_customer_created"

QUERY = """
SELECT id, customer_id, status, total_amount, created_at
FROM orders
WHERE customer_id = %s
ORDER BY created_at DESC
LIMIT 20
"""

PROPOSED_FIX = """
CREATE INDEX IF NOT EXISTS idx_orders_customer_created
ON orders (customer_id, created_at DESC)
"""


def explain_query(conn, customer_id):
    result = conn.execute(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + QUERY,
        (customer_id,),
    ).fetchone()

    root_plan = result[0][0]["Plan"]

    def find_scan(node):
        node_type = node["Node Type"]

        # Check children first to find the actual index scan.
        for child in node.get("Plans", []):
            scan = find_scan(child)
            if scan:
                return scan

        if node_type in (
            "Index Scan",
            "Index Only Scan",
            "Bitmap Index Scan",
            "Seq Scan",
        ):
            return {
                "node_type": node_type,
                "index_name": node.get("Index Name"),
            }

        return None

    scan = find_scan(root_plan) or {
        "node_type": root_plan["Node Type"],
        "index_name": None,
    }

    return {
        "execution_time_ms": result[0][0]["Execution Time"],
        "plan": scan["node_type"],
        "index_name": scan["index_name"],
    }


def benchmark(conn, customer_id, runs=15):
    # Warm-up query
    explain_query(conn, customer_id)

    timings = []
    plans = []

    for _ in range(runs):
        result = explain_query(conn, customer_id)
        timings.append(result["execution_time_ms"])
        plans.append(result)

    return {
        "median_ms": round(statistics.median(timings), 4),
        "runs": runs,
        "plan": plans[-1]["plan"],
        "index_name": plans[-1]["index_name"],
    }


def prove_fix(database_url, customer_id=62):
    with psycopg.connect(database_url, autocommit=True) as conn:

        # Safety: this must be a disposable test fork.
        conn.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")

        # Measure before applying the fix.
        before = benchmark(conn, customer_id)

        # Apply the proposed fix on the fork only.
        conn.execute(PROPOSED_FIX)
        conn.execute("ANALYZE orders")

        # Measure after applying the fix.
        after = benchmark(conn, customer_id)

        # Verify that the index exists.
        index_exists = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'orders'
                  AND indexname = %s
            )
            """,
            (INDEX_NAME,),
        ).fetchone()[0]

        improvement_percent = 0.0

        if before["median_ms"] > 0:
            improvement_percent = (
                (before["median_ms"] - after["median_ms"])
                / before["median_ms"]
            ) * 100

        # PASS requires the proposed index to exist
        # and PostgreSQL to actually use it.
        passed = (
            index_exists
            and after["index_name"] == INDEX_NAME
        )

        return {
            "status": "PASS" if passed else "FAIL",
            "customer_id": customer_id,
            "before": before,
            "after": after,
            "improvement_percent": round(improvement_percent, 2),
            "index_created": index_exists,
            "index_used": after["index_name"] == INDEX_NAME,
            "note": (
                "Verification checks index existence and actual "
                "query-plan usage. Performance measurements on "
                "small datasets may not represent production."
            ),
        }


if __name__ == "__main__":
    database_url = os.getenv("TIGER_FORK_URI")

    if not database_url:
        raise RuntimeError("TIGER_FORK_URI is not configured")

    result = prove_fix(database_url)
    print(json.dumps(result, indent=2))
