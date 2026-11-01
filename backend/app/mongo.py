from pymongo import MongoClient

from app.settings import settings

# tz_aware=True: dates come back with their timezone, matching the rest of the app.
# serverSelectionTimeoutMS: fail after 5 s instead of hanging if Atlas is unreachable.
client = MongoClient(settings.mongodb_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
db = client[settings.mongodb_db]
findings = db["findings"]
incidents = db["incidents"]

VECTOR_INDEX = "findings_vector"


def clean(doc: dict | None) -> dict | None:
    """Shape a stored document for the outside world: _id -> id, no embedding, no internals."""
    if doc is None:
        return None
    out = {k: v for k, v in doc.items() if k not in ("_id", "embedding", "claimed", "claimed_at")}
    out["id"] = doc["_id"]
    return out