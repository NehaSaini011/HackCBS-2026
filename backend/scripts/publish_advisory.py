"""Demo: publish a global advisory as the platform, in one command.

    python -m scripts.publish_advisory php2shell
    python -m scripts.publish_advisory postgres-feb-2026

Reads API_URL (default: the live Render API) and PROVIDER_TOKEN from the environment
(run `set -a; source .env; set +a` first).
"""
import os
import sys

import httpx

API = os.environ.get("API_URL", "https://fixnet-api-onrender-com.onrender.com").rstrip("/")

ADVISORIES = {
    # Real, 21 Oct 2026. Our demo fund runs Python, so the right answer is "0 exposed".
    "php2shell": {
        "title": "PHP2Shell: two critical flaws in PHP itself",
        "category": "security", "severity": "critical", "affects": ["php"],
        "summary": "CVE-2026-109618 and CVE-2026-109619 (CVSS 9.2) let an attacker run code on the "
                   "server over HTTP with no login. Updating plugins or the CMS does not fix it.",
        "fix": "Upgrade PHP to 8.5.12, 8.4.27, 8.3.36 or 8.2.35.",
        "mitigation": "Until upgraded: disable session.upload_progress.enabled, lower post_max_size, "
                      "enforce request-size limits at the proxy.",
        "source_url": "https://fieldeffect.com/blog/php-updates-critical-rce-flaws",
    },
    # Real, 26 Feb 2026 PostgreSQL security update. Both demo companies run Postgres.
    "postgres-feb-2026": {
        "title": "PostgreSQL security update, February 2026",
        "category": "database", "severity": "warning", "affects": ["postgres"],
        "summary": "The PostgreSQL Global Development Group released security fixes for every "
                   "supported major version on 26 Feb 2026.",
        "fix": "Upgrade to PostgreSQL 18.3, 17.9, 16.13, 15.17 or 14.22.",
        "source_url": "https://www.postgresql.org/about/newsarchive/security/20260226/",
    },
}

name = sys.argv[1] if len(sys.argv) > 1 else ""
if name not in ADVISORIES:
    sys.exit(f"usage: python -m scripts.publish_advisory {{{'|'.join(ADVISORIES)}}}")

r = httpx.post(f"{API}/advisories", json=ADVISORIES[name], timeout=90,
               headers={"X-Provider-Token": os.environ.get("PROVIDER_TOKEN", "")})
if r.status_code != 201:
    sys.exit(f"{r.status_code}: {r.text}")
d = r.json()
print(f"Published {d['id']}: {ADVISORIES[name]['title']}")
print(f"Meko: {d['meko']}")
print(f"Exposed companies: {len(d['exposed'])}")
for c in d["exposed"]:
    print(f"  - {c['name']} (finding {c['finding_id']})")
