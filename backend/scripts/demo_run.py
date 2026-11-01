"""Demo driver: one full incident for one company, through the LIVE Group API and real Meko.

    python -m scripts.demo_run pinecart      (first: no lesson yet, proves every candidate)
    python -m scripts.demo_run tealbox       (second: recalls Pinecart's lesson, proves one)

Stands in for the parts Person 1 has not connected yet:
  - the alert is sent the way Alertmanager would send it (real /ingest/alertmanager)
  - evidence is the shop's real schema, written out (not read from a live database)
  - fork proofs are SIMULATED (proof method "fake"): say so to the judges
Everything else is real: ingest, incident, Meko recall/store/share, the approval guard,
a human approving in the web app, the lesson registry and trust score.
Reads each company's key from .env.agent-a / .env.agent-b.
"""
import os
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx
from dotenv import dotenv_values

API = os.environ.get("API_URL", "https://fixnet-api-onrender-com.onrender.com").rstrip("/")

COMPANIES = {
    "pinecart": {"env": ".env.agent-a", "shop": "a", "engineer": "Arjun (arjun@pinecart.demo)",
                 "endpoint": "GET /customers/{id}/orders", "table": "orders",
                 "filter": "customer_id", "sort": "created_at", "rows": "1,000,000"},
    "tealbox": {"env": ".env.agent-b", "shop": "b", "engineer": "Priya (priya@tealbox.demo)",
                "endpoint": "GET /buyers/{id}/purchases", "table": "purchases",
                "filter": "buyer_id", "sort": "placed_at", "rows": "1,000,000"},
}
SYMPTOMS = ["p95 latency spike", "full table scan on a large table", "followed a release",
            "no lock waits"]
SAFE_DESCRIPTION = {
    "filter_then_sort_desc": "Recreate an index on the filtered column followed by the sort column, "
                             "newest first, built without blocking writes.",
    "filter_only": "Create an index on the filtered column, built without blocking writes.",
}
AFTER_MS = {"filter_then_sort_desc": 45.0, "filter_only": 60.0}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def event(op: str, text: str) -> dict:
    return {"op": op, "text": text[:300], "at": now()}


def ok(r: httpx.Response):
    if r.status_code >= 400:
        sys.exit(f"{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:300]}")
    return r.json()


name = sys.argv[1] if len(sys.argv) > 1 else ""
if name not in COMPANIES:
    sys.exit("usage: python -m scripts.demo_run pinecart|tealbox")
c = COMPANIES[name]
key = dotenv_values(c["env"]).get("COMPANY_API_KEY")
if not key or not key.startswith("fx_"):
    sys.exit(f"No COMPANY_API_KEY in {c['env']}")
api = httpx.Client(base_url=API, timeout=90, headers={"Authorization": f"Bearer {key}"})
put = lambda iid, **f: ok(api.put(f"/agent/incidents/{iid}", json=f))
t0 = time.monotonic()

# 1. Detection: the alert, exactly as Alertmanager posts it
print(f"[{name}] 1. Alert: p95 latency above 500 ms on {c['endpoint']}")
ok(api.post("/ingest/alertmanager", json={"receiver": f"shop-{c['shop']}", "status": "firing", "alerts": [{
    "status": "firing",
    "labels": {"alertname": "HighLatencyP95", "shop": c["shop"], "severity": "critical", "service": "shop-api"},
    "annotations": {"summary": "p95 latency above 500 ms", "description": f"{c['endpoint']} p95 is 2.1 s"},
    "startsAt": now(), "fingerprint": uuid.uuid4().hex[:16]}]}))

# 2. The agent picks it up and opens an incident
work = ok(api.get("/agent/work"))
finding = next((f for f in work["new_findings"] if f["test"] == "latency"), None)
if finding is None:
    sys.exit("No new latency finding handed out (is a real agent running and claiming it?)")
meko_mode = work["meko_mode"]
iid = ok(api.post("/agent/incidents", json={"finding_ids": [finding["id"]], "meko_mode": meko_mode}))["id"]
print(f"[{name}] 2. Incident {iid} opened (Meko {meko_mode.upper()})")

# 3. Evidence and diagnosis (the shop's real schema; values from the v2.3 release)
evidence = [
    {"check": "latency_history", "query": "p95 per endpoint from request_metrics",
     "result": f"{c['endpoint']}: p95 2100 ms now, 80 ms in the hour before"},
    {"check": "query_plan", "query": f"EXPLAIN (FORMAT JSON) SELECT ... FROM {c['table']} WHERE {c['filter']} = 1 ORDER BY {c['sort']} DESC LIMIT 20",
     "result": f"Seq Scan on {c['table']} (about {c['rows']} rows), filtering on {c['filter']}, then sorted by {c['sort']}"},
    {"check": "locks", "query": "SELECT count(*) FROM pg_locks WHERE NOT granted", "result": "0 sessions waiting on locks"},
    {"check": "releases", "query": "SELECT version, description FROM releases ORDER BY applied_at DESC LIMIT 1",
     "result": "v2.3: hot index removed in this release"},
]
put(iid, status="diagnosed", timeline={"diagnosed_at": now()}, diagnosis={
    "cause_class": "MISSING_INDEX", "evidence": evidence,
    "explanation": (f"Since release v2.3, {c['endpoint']} reads the whole {c['table']} table: the index on "
                    f"{c['filter']} and {c['sort']} is gone, so p95 rose from 80 ms to 2100 ms. "
                    "No sessions are waiting on locks.")})
print(f"[{name}] 3. Diagnosed: MISSING_INDEX (full scan of {c['table']} since v2.3)")

# 4. Recall from the fund's shared memory
lesson = None
if meko_mode == "on":
    m = ok(api.post("/lessons/match", json={"cause_class": "MISSING_INDEX", "symptoms": SYMPTOMS}))
    lesson = m["lessons"][0] if m["lessons"] else None
    put(iid, meko_activity_add=m["meko_activity"])
    print(f"[{name}] 4. Meko recall: " + (f"found {lesson['id']} (proven x{lesson['confirmations']})" if lesson else "nothing yet"))
else:
    put(iid, meko_activity_add=[event("skipped", "Meko is OFF: no recall")])
    print(f"[{name}] 4. Meko OFF: no recall")

# 5. Prove on a fork (SIMULATED here): the recalled fix only, or every candidate
put(iid, status="proving")
shapes = [lesson["fix_shape"]] if lesson else ["filter_then_sort_desc", "filter_only"]
best = None
for shape in shapes:
    cols = f"{c['filter']}, {c['sort']} DESC" if shape == "filter_then_sort_desc" else c["filter"]
    idx = f"idx_fix_{c['table']}_{c['filter']}" + (f"_{c['sort']}" if shape == "filter_then_sort_desc" else "")
    fix = {"template": "create_index",
           "sql": f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx} ON {c['table']} ({cols})"}
    print(f"[{name}] 5. Proving {shape} on a fork ...", end="", flush=True)
    time.sleep(8)
    proof = {"method": "fake", "fix_sql": fix["sql"], "before_p95_ms": 2100.0,
             "after_p95_ms": AFTER_MS[shape], "passed": True}
    print(f" 2100 -> {AFTER_MS[shape]:.0f} ms")
    if best is None or proof["after_p95_ms"] < best[1]["after_p95_ms"]:
        best = (fix, proof)
fix, proof = best
if lesson:   # only now does the incident count as using the lesson (its fix passed here)
    put(iid, recalled_lesson={k: lesson.get(k) for k in ("id", "cause_class", "confirmations", "status", "fix_shape")})
put(iid, status="awaiting_approval", fix=fix, proof=proof, timeline={"proven_at": now()})
proven_s = time.monotonic() - t0
print(f"[{name}] 6. Proven in {proven_s:.0f} s with {len(shapes)} proof(s). "
      f"Now approve it in the web app as {c['engineer']} ...")

# 6. Wait for the human
while True:
    approved = [i for i in ok(api.get("/agent/work"))["approved_incidents"] if i["id"] == iid]
    if approved:
        break
    time.sleep(3)
inc = approved[0]
print(f"[{name}] 7. Approved. Applying: {fix['sql']}")
put(iid, applied=True)
time.sleep(3)
put(iid, status="resolved", timeline={"resolved_at": now()})
print(f"[{name}] 8. Resolved: p95 back under 500 ms")

# 7. Learn
if meko_mode == "off":
    put(iid, meko_activity_add=[event("skipped", "Meko is OFF: nothing stored")])
    print(f"[{name}] 9. Meko OFF: nothing stored")
elif inc.get("recalled_lesson"):
    lid = inc["recalled_lesson"]["id"]
    r = ok(api.post(f"/lessons/{lid}/confirm", json={"incident_id": iid, "before_p95_ms": proof["before_p95_ms"],
                                                     "after_p95_ms": proof["after_p95_ms"]}))
    put(iid, meko_activity_add=[event("share", f"{lid} confirmed here (confirmations {r.get('confirmations', '?')})")])
    print(f"[{name}] 9. Lesson {lid} confirmed: it worked at a second company")
else:
    shape = "filter_then_sort_desc" if " DESC)" in fix["sql"] else "filter_only"
    r = ok(api.post("/lessons", json={
        "cause_class": "MISSING_INDEX", "symptoms": SYMPTOMS, "fix_template": "create_index",
        "fix_shape": shape, "fix_description": SAFE_DESCRIPTION[shape], "incident_id": iid,
        "before_p95_ms": proof["before_p95_ms"], "after_p95_ms": proof["after_p95_ms"]}))
    put(iid, meko_activity_add=r["meko_activity"])
    print(f"[{name}] 9. New lesson {r['id']} stored and shared through Meko")
print(f"[{name}] Done. Alert to proven fix: {proven_s:.0f} s")
