"""Wipe test data so the demo starts clean. Keeps users, companies, keys and the
four seeded postmortem lessons.

    python -m scripts.reset_demo        (from backend/, with .env loaded)

Removes: all findings and incidents (Atlas), agent-made lessons and their events,
risk-board rows, and advisories. Meko keeps old memories, but recall only offers
lessons still in the registry, so deleted lessons can never be proposed again.
"""
from app import mongo, yb

yb.pool.open()
lessons = yb.q("SELECT id FROM lessons WHERE source = 'agent'")
yb.run("DELETE FROM lesson_events WHERE lesson_id IN (SELECT id FROM lessons WHERE source = 'agent')")
yb.run("DELETE FROM lessons WHERE source = 'agent'")
yb.run("DELETE FROM risk_exposure")
yb.run("DELETE FROM advisories")
f = mongo.findings.delete_many({}).deleted_count
i = mongo.incidents.delete_many({}).deleted_count
yb.run("INSERT INTO settings (key, value) VALUES ('meko_mode', '\"on\"') "
       "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value")
yb.pool.close()
print(f"Removed {f} findings, {i} incidents, {len(lessons)} agent lessons. Meko mode set to ON.")
