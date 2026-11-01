"""Remove every platform advisory, so the demo can publish them fresh.

    python -m scripts.reset_advisories        (from backend/, with .env loaded)

Deletes: the advisories table rows, their risk-board rows, and their inbox findings.
The copies stored in Meko's shared knowledge stay (they are harmless: recall only
ever offers proven lessons from the registry).
"""
from app import mongo, yb

yb.pool.open()          # the server opens it at start-up; a script must open it itself
risks =yb.q("SELECT company_id FROM risk_exposure WHERE risk_type LIKE 'advisory:%%'")
yb.run("DELETE FROM risk_exposure WHERE risk_type LIKE 'advisory:%%'")
advisories = yb.q("SELECT id FROM advisories")
yb.run("DELETE FROM advisories")
findings = mongo.findings.delete_many({"source": "platform_advisory"}).deleted_count

yb.pool.close()
print(f"Removed {len(advisories)} advisories, {len(risks)} risk-board rows, {findings} inbox findings")
