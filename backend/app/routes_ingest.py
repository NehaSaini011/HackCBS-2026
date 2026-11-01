from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from app import mongo, yb
from app.deps import Company, company_from_key
from app.gemini import embed
from app.models import AMWebhook, FindingIn

router = APIRouter()

FINAL = ["resolved", "rejected", "unknown", "proof_failed"]   # statuses that are "over"
JOIN_WINDOW = timedelta(minutes=30)       # repeats within 30 minutes join the open finding
SIMILAR = 0.92                            # vector score that counts as "the same problem"
ALERT_TEST = {"HighLatencyP95": "latency", "CertificateExpiresSoon": "certificate"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def severity_of(value: str | None) -> str:
    return value if value in ("info", "warning", "critical") else "warning"


def find_similar_open(company: Company, test: str, summary: str, vec: list | None) -> str | None:
    """Id of an open finding at this company that is the same problem, or None."""
    since = now() - JOIN_WINDOW
    if vec:
        try:
            pipeline = [
                {"$vectorSearch": {"index": mongo.VECTOR_INDEX, "path": "embedding",
                                   "queryVector": vec, "numCandidates": 50, "limit": 5,
                                   "filter": {"company_id": company.id, "test": test}}},
                {"$project": {"status": 1, "last_seen": 1,
                              "score": {"$meta": "vectorSearchScore"}}},
            ]
            for m in mongo.findings.aggregate(pipeline):
                if m["score"] >= SIMILAR and m["status"] not in FINAL and m["last_seen"] >= since:
                    return m["_id"]
            return None
        except Exception as e:
            print("vector search failed, falling back to exact match:", e)
    # Fallback: same test and same summary text, still open, seen recently
    m = mongo.findings.find_one({"company_id": company.id, "test": test, "summary": summary,
                                 "status": {"$nin": FINAL}, "last_seen": {"$gte": since}})
    return m["_id"] if m else None


def bump(finding_id: str) -> None:
    mongo.findings.update_one({"_id": finding_id},
                              {"$inc": {"duplicates": 1}, "$set": {"last_seen": now()}})


def mark_risk(company: Company, risk_type: str, finding_id: str) -> None:
    """Record in YugabyteDB that this company has this open risk (for the group's risk board)."""
    yb.run(
        "INSERT INTO risk_exposure (company_id, risk_type, group_id, status, finding_id, updated_at) "
        "VALUES (%s, %s, %s, 'open', %s, now()) "
        "ON CONFLICT (company_id, risk_type) DO UPDATE SET "
        "  status = CASE WHEN risk_exposure.status = 'pushed' THEN 'pushed' ELSE 'open' END, "
        "  finding_id = EXCLUDED.finding_id, updated_at = now()",
        (company.id, risk_type, company.group_id, finding_id))


def save_finding(company: Company, *, source: str, test: str, severity: str, summary: str,
                 raw: dict, fingerprint: str | None = None, first_seen: datetime | None = None,
                 lesson_id: str | None = None) -> tuple[str, bool]:
    """Save a finding, or join it to an open one. Returns (finding_id, joined)."""
    # 1. Exact repeat of the same alert (Alertmanager gives each alert a fingerprint)
    if fingerprint:
        same = mongo.findings.find_one({"company_id": company.id, "fingerprint": fingerprint,
                                        "status": {"$nin": FINAL}})
        if same:
            bump(same["_id"])
            return same["_id"], True

    # 2. Same problem said differently (vector search), unless the group pushed a lesson
    vec = embed(f"{test}: {summary}")
    if not lesson_id:
        similar = find_similar_open(company, test, summary, vec)
        if similar:
            bump(similar)
            return similar, True

    # 3. A new finding
    fid = yb.new_id("f")
    t = now()
    mongo.findings.insert_one({
        "_id": fid, "group_id": company.group_id, "company_id": company.id,
        "source": source, "test": test, "severity": severity, "summary": summary[:500],
        "raw": raw, "fingerprint": fingerprint, "embedding": vec,
        "status": "open", "incident_id": None, "lesson_id": lesson_id, "claimed": False,
        "duplicates": 0, "first_seen": first_seen or t, "last_seen": t,
    })
    mark_risk(company, test, fid)
    return fid, False


def alert_resolved(company: Company, fingerprint: str) -> int:
    """Alertmanager says the problem stopped. Close what can be closed."""
    closed = 0
    for f in mongo.findings.find({"company_id": company.id, "fingerprint": fingerprint,
                                  "status": {"$nin": FINAL}}):
        inc = mongo.incidents.find_one({"_id": f["incident_id"]}) if f["incident_id"] else None
        # Only close if nobody is mid-decision: no incident yet, or the fix is being applied
        if inc is None or inc["status"] in ("applying", "resolved"):
            mongo.findings.update_one({"_id": f["_id"]},
                                      {"$set": {"status": "resolved", "resolved_at": now()}})
            if inc is not None and inc["status"] == "applying":
                mongo.incidents.update_one({"_id": inc["_id"]}, {"$set": {
                    "status": "resolved", "timeline.resolved_at": now()}})
            yb.run("UPDATE risk_exposure SET status = 'resolved', updated_at = now() "
                   "WHERE company_id = %s AND risk_type = %s", (company.id, f["test"]))
            closed += 1
        else:
            # Latency recovered on its own, but an engineer still has a decision open
            mongo.findings.update_one({"_id": f["_id"]}, {"$set": {"alert_resolved_at": now()}})
    return closed


@router.post("/ingest/alertmanager", status_code=202)
def ingest_alertmanager(body: AMWebhook, company: Company = Depends(company_from_key)):
    out = []
    for a in body.alerts:
        shop = a.labels.get("shop")
        if company.shop and shop and shop != company.shop:
            raise HTTPException(403, "This API key does not belong to that shop")
        if a.status == "firing":
            fid, joined = save_finding(
                company, source="alertmanager",
                test=ALERT_TEST.get(a.labels.get("alertname", ""), "latency"),
                severity=severity_of(a.labels.get("severity")),
                summary=a.annotations.get("summary") or a.labels.get("alertname", "alert"),
                raw=a.model_dump(mode="json"), fingerprint=a.fingerprint, first_seen=a.startsAt)
            out.append({"finding_id": fid, "joined": joined})
        else:
            out.append({"fingerprint": a.fingerprint, "closed": alert_resolved(company, a.fingerprint)})
    return {"accepted": len(body.alerts), "results": out}


@router.post("/ingest/finding", status_code=202)
def ingest_finding(body: FindingIn, company: Company = Depends(company_from_key)):
    if company.shop and body.shop != company.shop:
        raise HTTPException(403, "This API key does not belong to that shop")
    fid, joined = save_finding(company, source=body.source, test=body.test,
                               severity=body.severity, summary=body.summary, raw=body.raw,
                               first_seen=body.observed_at)
    return {"finding_id": fid, "joined": joined}