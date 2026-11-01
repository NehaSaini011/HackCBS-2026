from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pymongo import ReturnDocument

from app import meko, mongo, yb
from app.deps import Company, company_from_key
from app.models import IncidentCreate, IncidentUpdate, LessonIn, LessonMatchIn, LessonResultIn

router = APIRouter()

RECLAIM_AFTER = timedelta(minutes=10)    # if an agent crashed mid-way, hand the finding out again
LESSON_COLUMNS = ("id, cause_class, symptoms, fix_template, fix_shape, fix_description, status, "
                  "confirmations, failures, confirmations - 2 * failures AS trust_score")
# Words that must never appear in a shared lesson
BLOCKED_PATTERNS = ["select ", " from ", " where ", "create index", "_id", "://", "@", ".com", ".net"]


def now() -> datetime:
    return datetime.now(timezone.utc)


def event(op: str, text: str) -> dict:
    return {"op": op, "text": text[:300], "at": now()}


def own_incident(incident_id: str, company: Company) -> dict:
    inc = mongo.incidents.find_one({"_id": incident_id, "company_id": company.id})
    if inc is None:
        raise HTTPException(404, "Incident not found")
    return inc


# ---------------- Work ----------------

@router.get("/agent/work")
def agent_work(company: Company = Depends(company_from_key)):
    # Note: this GET also "claims" findings, so each one is handed out once.
    new = []
    for _ in range(5):
        doc = mongo.findings.find_one_and_update(
            {"company_id": company.id, "status": "open", "incident_id": None,
             "$or": [{"claimed": False}, {"claimed_at": {"$lt": now() - RECLAIM_AFTER}}]},
            {"$set": {"claimed": True, "claimed_at": now()}},
            sort=[("first_seen", 1)], return_document=ReturnDocument.AFTER)
        if doc is None:
            break
        item = {"id": doc["_id"], "test": doc["test"], "summary": doc["summary"],
                "severity": doc["severity"], "first_seen": doc["first_seen"], "lesson": None}
        if doc.get("lesson_id"):   # pushed by the group admin: hand over the lesson too
            item["lesson"] = yb.q1(f"SELECT {LESSON_COLUMNS} FROM lessons WHERE id = %s "
                                   "AND group_id = %s", (doc["lesson_id"], company.group_id))
        new.append(item)

    approved = [{"id": i["_id"], "fix": i["fix"], "proof": i["proof"],
                 "recalled_lesson": i.get("recalled_lesson"), "meko_mode": i.get("meko_mode")}
                for i in mongo.incidents.find({"company_id": company.id, "status": "applying",
                                               "applied": False})]
    return {"new_findings": new, "approved_incidents": approved,
            "meko_mode": yb.get_setting("meko_mode", "on")}


# ---------------- Incidents ----------------

@router.post("/agent/incidents", status_code=201)
def create_incident(body: IncidentCreate, company: Company = Depends(company_from_key)):
    docs = list(mongo.findings.find({"_id": {"$in": body.finding_ids}, "company_id": company.id}))
    if not docs or len(docs) != len(set(body.finding_ids)):
        raise HTTPException(404, "Unknown finding")
    iid = yb.new_id("inc")
    mongo.incidents.insert_one({
        "_id": iid, "group_id": company.group_id, "company_id": company.id,
        "finding_ids": body.finding_ids, "status": "open",
        "diagnosis": None, "recalled_lesson": None, "fix": None, "proof": None,
        "decision": None, "applied": False, "meko_activity": [], "meko_mode": body.meko_mode,
        "timeline": {"first_alert_at": min(d["first_seen"] for d in docs), "diagnosed_at": None,
                     "proven_at": None, "decided_at": None, "resolved_at": None},
    })
    mongo.findings.update_many({"_id": {"$in": body.finding_ids}}, {"$set": {"incident_id": iid}})
    return {"id": iid}


@router.put("/agent/incidents/{incident_id}")
def update_incident(incident_id: str, body: IncidentUpdate,
                    company: Company = Depends(company_from_key)):
    inc = own_incident(incident_id, company)
    if inc["status"] == "rejected":
        raise HTTPException(409, "Incident was rejected by an engineer")
    if body.status == "applying":
        raise HTTPException(403, "Only an engineer's approval can start applying a fix")
    if body.status == "awaiting_approval":
        proof = body.proof.model_dump() if body.proof else (inc.get("proof") or {})
        fix = body.fix.model_dump() if body.fix else (inc.get("fix") or {})
        if not proof.get("passed") or proof.get("fix_sql") != fix.get("sql"):
            raise HTTPException(409, "awaiting_approval needs a passing proof of this exact fix")

    sets: dict = {}
    for field in ("status", "diagnosis", "recalled_lesson", "fix", "proof", "applied"):
        value = getattr(body, field)
        if value is not None:
            sets[field] = value.model_dump() if hasattr(value, "model_dump") else value
    for key, value in body.timeline.items():
        sets[f"timeline.{key}"] = value
    update: dict = {}
    if sets:
        update["$set"] = sets
    if body.meko_activity_add:
        update["$push"] = {"meko_activity": {"$each": [e.model_dump() for e in body.meko_activity_add]}}
    if update:
        mongo.incidents.update_one({"_id": incident_id}, update)

    if body.status:   # keep the findings' status in step with the incident
        extra = {"resolved_at": now()} if body.status == "resolved" else {}
        mongo.findings.update_many({"_id": {"$in": inc["finding_ids"]}},
                                   {"$set": {"status": body.status, **extra}})
    if body.status == "resolved":
        for f in mongo.findings.find({"_id": {"$in": inc["finding_ids"]}}, {"test": 1}):
            yb.run("UPDATE risk_exposure SET status = 'resolved', updated_at = now() "
                   "WHERE company_id = %s AND risk_type = %s", (company.id, f["test"]))
    if body.applied:
        yb.audit(f"agent:{company.id}", "apply", company.id, incident_id,
                 {"fix_sql": (inc.get("fix") or {}).get("sql")})
    return {"ok": True}


# ---------------- Lessons ----------------

@router.post("/lessons/match")
def match_lessons(body: LessonMatchIn, company: Company = Depends(company_from_key)):
    # Meko OFF is enforced here too, not only in the agent: no recall reaches Meko or the registry
    if yb.get_setting("meko_mode", "on") == "off":
        return {"lessons": [], "meko_activity": [event("skipped", "Meko is OFF: no recall")]}
    activity = []
    ids: list[str] = []
    try:
        # Searches only the group's SHARED (promoted) knowledge, never another company's private memories
        texts = meko.search(f"{body.cause_class} " + " ".join(body.symptoms), company_id=company.id, limit=5)
        ids = meko.lesson_ids(texts)
        activity.append(event("recall", f"knowledgebase_search → {len(ids)} lesson(s)"))
    except Exception as e:
        activity.append(event("error", f"Meko search failed: {e}"))
    lessons = []
    if ids:
        # Meko finds by meaning; YugabyteDB decides which are proven and how trusted
        lessons = yb.q(f"SELECT {LESSON_COLUMNS} FROM lessons WHERE id = ANY(%s) AND group_id = %s "
                       "AND cause_class = %s AND status = 'proven'",
                       (ids, company.group_id, body.cause_class))
        lessons.sort(key=lambda r: -r["trust_score"])
        if lessons:
            best = lessons[0]
            activity[-1]["text"] += f" (best: {best['cause_class']}, proven ×{best['confirmations']})"
    return {"lessons": lessons, "meko_activity": activity}


@router.post("/lessons", status_code=201)
def create_lesson(body: LessonIn, company: Company = Depends(company_from_key)):
    inc = own_incident(body.incident_id, company)
    if not (inc.get("proof") or {}).get("passed") or not (inc.get("decision") or {}).get("approved"):
        raise HTTPException(409, "Only proven and approved fixes become lessons")

    # Second redaction check, on the server
    text = " ".join([body.fix_description, *body.symptoms]).lower()
    names = [r["name"].lower() for r in yb.q("SELECT name FROM companies")]
    hits = [p for p in BLOCKED_PATTERNS + names if p in text]
    if hits:
        raise HTTPException(422, f"Lesson contains private details: {hits}")

    lid = yb.new_id("les")
    activity, meko_ref = [], None
    try:
        meko_ref = meko.add(company.id, meko.memory_text(
            lid, body.cause_class, body.symptoms, body.fix_template, body.fix_shape,
            body.fix_description))
        activity.append(event("store", "memory_add → saved as a private memory"))
        meko.promote(meko_ref, company.id)
        activity.append(event("share", "memory_promote → shared with the group"))
    except Exception as e:
        activity.append(event("error", f"Meko failed, lesson kept for retry: {e}"))

    yb.run("INSERT INTO lessons (id, group_id, cause_class, symptoms, fix_template, fix_shape, "
           "fix_description, status, source, confirmations, meko_ref, created_by) "
           "VALUES (%s, %s, %s, %s, %s, %s, %s, 'proven', 'agent', 1, %s, %s)",
           (lid, company.group_id, body.cause_class, Jsonb(body.symptoms), body.fix_template,
            body.fix_shape, body.fix_description, meko_ref, company.id))
    yb.run("INSERT INTO lesson_events (id, lesson_id, company_id, incident_id, result, "
           "before_p95_ms, after_p95_ms) VALUES (%s, %s, %s, %s, 'created', %s, %s)",
           (yb.new_id("lev"), lid, company.id, body.incident_id, body.before_p95_ms, body.after_p95_ms))
    return {"id": lid, "meko_activity": activity}


def record_result(lesson_id: str, body: LessonResultIn, company: Company, result: str) -> dict:
    if yb.q1("SELECT 1 FROM lesson_events WHERE lesson_id = %s AND incident_id = %s",
             (lesson_id, body.incident_id)):
        return {"id": lesson_id, "already_recorded": True}      # safe to call twice
    if result == "confirmed":
        row = yb.q1("UPDATE lessons SET confirmations = confirmations + 1 "
                    "WHERE id = %s AND group_id = %s RETURNING id, confirmations, failures",
                    (lesson_id, company.group_id))
    else:
        row = yb.q1("UPDATE lessons SET failures = failures + 1, "
                    "status = CASE WHEN failures + 1 > confirmations THEN 'failed' ELSE status END "
                    "WHERE id = %s AND group_id = %s RETURNING id, confirmations, failures, status",
                    (lesson_id, company.group_id))
    if row is None:
        raise HTTPException(404, "Lesson not found")
    yb.run("INSERT INTO lesson_events (id, lesson_id, company_id, incident_id, result, "
           "before_p95_ms, after_p95_ms) VALUES (%s, %s, %s, %s, %s, %s, %s)",
           (yb.new_id("lev"), lesson_id, company.id, body.incident_id, result,
            body.before_p95_ms, body.after_p95_ms))
    return row


@router.post("/lessons/{lesson_id}/confirm")
def confirm_lesson(lesson_id: str, body: LessonResultIn, company: Company = Depends(company_from_key)):
    return record_result(lesson_id, body, company, "confirmed")


@router.post("/lessons/{lesson_id}/fail")
def fail_lesson(lesson_id: str, body: LessonResultIn, company: Company = Depends(company_from_key)):
    return record_result(lesson_id, body, company, "failed")
