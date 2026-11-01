"""Checks every web-app endpoint on a running Group API, as all three demo users.

    python scripts/smoke_test.py https://fixnet-api-onrender-com.onrender.com

It asks for the three demo passwords (nothing is shown or saved).
It only READS data, except one approve call on an incident that is already
resolved, which the API must refuse. So it is safe to run on the live API.
"""
import getpass
import sys

import httpx

API = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
USERS = {
    "platform (group admin)": "platform@fund1.demo",
    "arjun (Pinecart)": "arjun@pinecart.demo",
    "priya (Tealbox)": "priya@tealbox.demo",
}
RESOLVED_TEALBOX_INCIDENT = "inc_5a5bcee4"     # from the Step 10 walkthrough

c = httpx.Client(base_url=API, timeout=90)     # 90 s: a sleeping Render service takes ~1 min to wake
ok = fails = 0


def show(label: str, r: httpx.Response, expect: int) -> None:
    global ok, fails
    good = r.status_code == expect
    ok, fails = ok + good, fails + (not good)
    body = r.text.replace("\n", " ")[:90]
    print(f"  {'PASS' if good else 'FAIL'}  {r.status_code} (want {expect})  {label}   {body}")


print(f"API: {API}")
show("GET /health", c.get("/health"), 200)

# Every GET route with no {id} in it, read from the API's own list of routes
spec = c.get("/openapi.json").json()
plain_gets = sorted(p for p, ops in spec["paths"].items()
                    if "get" in ops and "{" not in p
                    and p not in ("/health",) and not p.startswith("/agent") and not p.startswith("/docs"))
print("Web GET routes found:", ", ".join(plain_gets))

tokens = {}
for who, email in USERS.items():
    pw = getpass.getpass(f"Password for {email}: ")
    r = c.post("/auth/login", json={"email": email, "password": pw})
    show(f"login {who}", r, 200)
    if r.status_code == 200:
        d = r.json()
        tokens[who] = d.get("token") or d.get("access_token")

for who, tok in tokens.items():
    print(f"\nAs {who}:")
    h = {"Authorization": f"Bearer {tok}"}
    for path in plain_gets:
        r = c.get(path, headers=h)
        # Role rules: group pages and the Meko setting are group admin only;
        # findings are company engineers only. A 403 in those cases is correct.
        admin_only = path.startswith("/group") or path.startswith("/settings")
        engineer_only = path.startswith("/findings")
        is_admin = "platform" in who
        expect = 403 if (admin_only and not is_admin) or (engineer_only and is_admin) else 200
        show(f"GET {path}", r, expect)

print("\nIncident detail and approve:")
if "priya (Tealbox)" in tokens:
    h = {"Authorization": f"Bearer {tokens['priya (Tealbox)']}"}
    show(f"Priya reads {RESOLVED_TEALBOX_INCIDENT}", c.get(f"/incidents/{RESOLVED_TEALBOX_INCIDENT}", headers=h), 200)
    r = c.post(f"/incidents/{RESOLVED_TEALBOX_INCIDENT}/approve", headers=h)
    show("Priya approves a resolved incident (must be refused)", r, 409)
if "arjun (Pinecart)" in tokens:
    h = {"Authorization": f"Bearer {tokens['arjun (Pinecart)']}"}
    show("Arjun reads Tealbox's incident (must be hidden)",
         c.get(f"/incidents/{RESOLVED_TEALBOX_INCIDENT}", headers=h), 404)

print("\nCORS for the web app:")
for origin in ("http://localhost:5173", "http://localhost:5174"):
    r = c.options("/me", headers={"Origin": origin, "Access-Control-Request-Method": "GET",
                                  "Access-Control-Request-Headers": "authorization"})
    allowed = r.headers.get("access-control-allow-origin") == origin
    ok, fails = ok + allowed, fails + (not allowed)
    print(f"  {'PASS' if allowed else 'FAIL'}  {origin} allowed")

print(f"\n{ok} passed, {fails} failed")
