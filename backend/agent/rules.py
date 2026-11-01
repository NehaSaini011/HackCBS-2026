LARGE_TABLE_ROWS = 100_000
DEFAULT_SYMPTOMS = ["p95 latency spike", "full table scan on a large table"]


def decide(facts: dict) -> tuple[str, list[str]]:
    """Cause class + generic symptom phrases (safe to share: a fixed vocabulary)."""
    symptoms = []
    now_ms, before_ms = facts.get("p95_now", 0), facts.get("p95_before", 0)
    if now_ms > 500 and (before_ms == 0 or now_ms > 3 * before_ms):
        symptoms.append("p95 latency spike")
    target = facts.get("target")
    big_scan = bool(target) and target["rows"] >= LARGE_TABLE_ROWS
    if big_scan:
        symptoms.append("full table scan on a large table")
    if facts.get("recent_release"):
        symptoms.append("followed a release")

    if facts.get("lock_waits", 0) > 0:
        return "LOCK_CONTENTION", symptoms + ["sessions waiting on locks"]
    symptoms.append("no lock waits")
    if big_scan:
        return "MISSING_INDEX", symptoms
    return "UNKNOWN", symptoms
