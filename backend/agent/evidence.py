import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from agent import config

NAME = re.compile(r"^[a-z_][a-z0-9_]*$")     # what a safe table or column name looks like

LATENCY_SQL = """
WITH recent AS (
  SELECT endpoint, percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95, count(*) AS n
  FROM request_metrics WHERE time > now() - interval '2 minutes' GROUP BY endpoint),
earlier AS (
  SELECT endpoint, percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95
  FROM request_metrics
  WHERE time BETWEEN now() - interval '65 minutes' AND now() - interval '5 minutes'
  GROUP BY endpoint)
SELECT r.endpoint, round(r.p95::numeric) AS p95_now, round(e.p95::numeric) AS p95_before, r.n
FROM recent r LEFT JOIN earlier e USING (endpoint)
ORDER BY r.p95 DESC LIMIT 3"""

# Slowest single runs. Our own monitoring queries are filtered out.
SLOW_SQL = r"""
SELECT query, calls, round(mean_exec_time::numeric, 1) AS mean_ms,
       round(max_exec_time::numeric, 1) AS max_ms
FROM pg_stat_statements
WHERE query ILIKE 'select%' AND query NOT ILIKE '%pg\_%' AND query NOT ILIKE '%request_metrics%'
  AND query NOT ILIKE '%information_schema%' AND calls >= 5
ORDER BY max_exec_time DESC LIMIT 5"""

LOCKS_SQL = "SELECT count(*) AS waiting FROM pg_locks WHERE NOT granted"
RELEASE_SQL = ("SELECT version, description, applied_at, "
               "now() - applied_at < interval '30 minutes' AS recent "
               "FROM releases ORDER BY applied_at DESC LIMIT 1")
TABLE_ROWS_SQL = "SELECT reltuples::bigint AS n FROM pg_class WHERE relname = %s AND relkind = 'r'"
COLUMNS_SQL = ("SELECT column_name FROM information_schema.columns "
               "WHERE table_schema = 'public' AND table_name = %s")
NAMES_SQL = """
SELECT table_name AS n FROM information_schema.tables WHERE table_schema = 'public'
UNION SELECT column_name FROM information_schema.columns WHERE table_schema = 'public'
UNION SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"""
RECENT_P95_SQL = ("SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95 "
                  "FROM request_metrics WHERE endpoint = %s "
                  "AND time > now() - make_interval(secs => %s)")


def rows(sql: str, params: tuple | None = None) -> list[dict]:
    """Run one read-only query on this company's database."""
    with psycopg.connect(config.SHOP_READONLY_URL, row_factory=dict_row, autocommit=True) as conn:
        conn.execute("SET statement_timeout = '10s'")
        conn.execute("SET default_transaction_read_only = on")   # belt and braces
        return conn.execute(sql, params).fetchall()


@dataclass
class Evidence:
    items: list[dict] = field(default_factory=list)   # shown to the engineer (C4 evidence)
    facts: dict = field(default_factory=dict)          # used by the rules


def _walk(node: dict):
    yield node
    for child in node.get("Plans", []):
        yield from _walk(child)


def _safe(table: str, columns: list[str]) -> bool:
    """Names must look like plain identifiers AND really exist in this table."""
    real = {r["column_name"] for r in rows(COLUMNS_SQL, (table,))}
    return bool(NAME.match(table)) and all(NAME.match(c) and c in real for c in columns)


def scan_target(query: str) -> dict | None:
    """If Postgres reads a whole table to answer this query, return what it scans."""
    if not query.lstrip().lower().startswith("select"):
        return None
    sql = re.sub(r"\$\d+", "1", query)          # fill $1, $2 placeholders so EXPLAIN can plan it
    try:
        plan = rows("EXPLAIN (FORMAT JSON) " + sql)[0]["QUERY PLAN"][0]["Plan"]
    except Exception as e:
        print("explain failed:", e)
        return None
    sort_col = None
    for node in _walk(plan):
        if "Sort" in node.get("Node Type", "") and node.get("Sort Key"):
            sort_col = node["Sort Key"][0].split()[0].split(".")[-1]    # "t.placed_at DESC" -> placed_at
    for node in _walk(plan):
        if "Seq Scan" in node.get("Node Type", "") and node.get("Filter"):
            m = re.match(r"\(+(\w+) = ", node["Filter"])                 # "(buyer_id = 1)" -> buyer_id
            if not m:
                continue
            table, filter_col = node["Relation Name"], m.group(1)
            if not _safe(table, [filter_col] + ([sort_col] if sort_col else [])):
                return None
            n = rows(TABLE_ROWS_SQL, (table,))
            return {"table": table, "filter_col": filter_col, "sort_col": sort_col,
                    "rows": int(n[0]["n"]) if n else 0, "explained": sql}
    return None


def collect() -> Evidence:
    ev = Evidence()

    lat = rows(LATENCY_SQL)
    if lat:
        top = lat[0]
        ev.facts.update(endpoint=top["endpoint"], p95_now=float(top["p95_now"] or 0),
                        p95_before=float(top["p95_before"] or 0))
        ev.items.append({"check": "latency_history", "query": LATENCY_SQL.strip(),
                         "result": f"{top['endpoint']}: p95 {top['p95_now']} ms now, "
                                   f"{top['p95_before'] or 'unknown'} ms in the hour before"})

    slow = rows(SLOW_SQL)
    ev.items.append({"check": "slow_queries", "query": SLOW_SQL.strip(),
                     "result": (f"slowest run {slow[0]['max_ms']} ms (mean {slow[0]['mean_ms']} ms) "
                                f"over {slow[0]['calls']} calls") if slow else "no slow queries"})
    for s in slow:
        target = scan_target(s["query"])
        if target:
            ev.facts["target"] = target
            sort = f", then sorted by {target['sort_col']}" if target["sort_col"] else ""
            ev.items.append({"check": "query_plan", "query": "EXPLAIN (FORMAT JSON) " + target["explained"],
                             "result": f"Seq Scan on {target['table']} (about {target['rows']:,} rows), "
                                       f"filtering on {target['filter_col']}{sort}"})
            break

    waiting = rows(LOCKS_SQL)[0]["waiting"]
    ev.facts["lock_waits"] = waiting
    ev.items.append({"check": "locks", "query": LOCKS_SQL, "result": f"{waiting} sessions waiting on locks"})

    rel = rows(RELEASE_SQL)
    if rel:
        ev.facts["recent_release"] = bool(rel[0]["recent"])
        ev.items.append({"check": "releases", "query": RELEASE_SQL,
                         "result": f"{rel[0]['version']} at {rel[0]['applied_at']:%H:%M} UTC: "
                                   f"{rel[0]['description']}"})
    return ev


def slowest_endpoint() -> str | None:
    lat = rows(LATENCY_SQL)
    return lat[0]["endpoint"] if lat else None


def recent_p95(endpoint: str, seconds: int = 20) -> float | None:
    r = rows(RECENT_P95_SQL, (endpoint, seconds))
    return float(r[0]["p95"]) if r and r[0]["p95"] is not None else None


def private_names() -> list[str]:
    """Every name that must never leave this company: tables, columns, indexes, host."""
    names = {r["n"].lower() for r in rows(NAMES_SQL)}
    host = (urlparse(config.SHOP_READONLY_URL).hostname or "").lower()
    names |= {host, *host.split(".")}
    return sorted(n for n in names if len(n) >= 3)


if __name__ == "__main__":       # python -m agent.evidence
    e = collect()
    print(json.dumps(e.facts, indent=2, default=str))
    for item in e.items:
        print("-", item["check"], ":", item["result"])
