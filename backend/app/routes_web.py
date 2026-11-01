from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb

from app import mongo, yb
from app.deps import Company, User, current_user, engineer, group_admin
from app.models import MekoModeIn, PushIn, RejectIn
from app.routes_ingest import save_finding

router = APIRouter()

# Demo mapping: which lesson cause class can fix which risk type
RISK_TO_CAUSE = {"missing_index": "MISSING_INDEX", "latency": "MISSING_INDEX"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def company_names(group_id: str) -> dict[str, str]:
    rows = yb.q("SELECT id, name FROM companies WHERE group_id = %s", (group_id,))
    return {r["id"]: r["name"] for r in rows}


def shape(doc: dict, names: dict[str, str]) -> dict:
    """Atlas document -> contract shape (C3 or C4)."""
    out = mongo.clean(doc)
    for internal in ("group_id", "fingerprint", "raw"):
        out.pop(internal, None)
    cid = out.pop("company_id")
    out["company"] = {"id": cid, "name": names.get(cid, cid)}
    return out


def own_incident(incident_id: str, user: User) -> dict:
    """The incident, only if it belongs to the caller's company. Otherwise 404."""
    inc = mongo.incidents.find_one({"_id": incident_id, "company_id": user.company_id})
    if inc is None:
        raise HTTPException(404, "Incident not found")
    return inc


# ---------------- Engineer screens ----------------

@router.get("/findings")
def list_findings(user: User = Depends(engineer)):
    names = company_names(user.group_id)
    docs = mongo.findings.find({"company_id": user.company_id}).sort("last_seen", -1).limit(100)
    return [shape(d, names) for d in docs]


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, user: User = Depends(engineer)):
    return shape(own_incident(incident_id, user), company_names(user.group_id))


@router.post("/incidents/{incident_id}/approve")
def approve(incident_id: str, user: User = Depends(engineer)):
    inc = own_incident(incident_id, user)
    fix, proof = inc.get("fix") or {}, inc.get("proof") or {}
    if inc["status"] != "awaiting_approval" or inc.get("decision"):
        raise HTTPException(409, f"Cannot approve an incident that is {inc['status']}")
    if not proof.get("passed"):
        raise HTTPException(409, "Fix not tested, or the test failed")
    if proof.get("fix_sql") != fix.get("sql"):
        raise HTTPException(409, "The tested fix is not the fix on this incident")

    decision = {"approved": True, "by": user.email, "reason": None, "at": now()}
    # The filter repeats the checks, so two quick clicks cannot both succeed
    result = mongo.incidents.update_one(
        {"_id": incident_id, "company_id": user.company_id,
         "status": "awaiting_approval", "decision": None, "proof.passed": True},
        {"$set": {"decision": decision, "status": "applying", "applied": False,
                  "timeline.decided_at": decision["at"]}})
    if result.modified_count != 1:
        raise HTTPException(409, "Already decided")
    mongo.findings.update_many({"_id": {"$in": inc["finding_ids"]}}, {"$set": {"status": "applying"}})
    yb.audit(user.email, "approve", user.company_id, incident_id, {"fix_sql": fix["sql"]})
    return {"status": "applying", "decision": decision}


@router.post("/incidents/{incident_id}/reject")
def reject(incident_id: str, body: RejectIn, user: User = Depends(engineer)):
    inc = own_incident(incident_id, user)
    if inc.get("decision") or inc["status"] in ("applying", "resolved", "rejected"):
        raise HTTPException(409, f"Cannot reject an incident that is {inc['status']}")
    decision = {"approved": False, "by": user.email, "reason": body.reason, "at": now()}
    mongo.incidents.update_one({"_id": incident_id}, {"$set": {
        "decision": decision, "status": "rejected", "timeline.decided_at": decision["at"]}})
    mongo.findings.update_many({"_id": {"$in": inc["finding_ids"]}}, {"$set": {"status": "rejected"}})
    yb.audit(user.email, "reject", user.company_id, incident_id, {"reason": body.reason})
    return {"status": "rejected", "decision": decision}


# ---------------- Both roles ----------------

@router.get("/lessons")
def list_lessons(user: User = Depends(current_user)):
    # No created_by, no company names: lessons stay anonymous inside the group
    return yb.q(
        "SELECT id, cause_class, symptoms, fix_template, fix_shape, fix_description, status, "
        "confirmations, failures, confirmations - 2 * failures AS trust_score, source, created_at "
        "FROM lessons WHERE group_id = %s ORDER BY trust_score DESC, created_at DESC",
        (user.group_id,))


# ---------------- Group admin screens ----------------

@router.get("/group/overview")
def group_overview(user: User = Depends(group_admin)):
    cards = []
    for c in yb.q("SELECT id, name, tech_stack FROM companies WHERE group_id = %s ORDER BY name",
                  (user.group_id,)):
        open_by_severity = {"critical": 0, "warning": 0, "info": 0}
        for row in mongo.findings.aggregate([
            {"$match": {"company_id": c["id"], "status": {"$nin": ["resolved", "rejected"]}}},
            {"$group": {"_id": "$severity", "n": {"$sum": 1}}}]):
            open_by_severity[row["_id"]] = row["n"]
        last = mongo.incidents.find_one({"company_id": c["id"]}, sort=[("timeline.first_alert_at", -1)])
        risks = yb.q1("SELECT count(*) AS n FROM risk_exposure WHERE company_id = %s "
                      "AND status <> 'resolved'", (c["id"],))["n"]
        cards.append({
            "company": {"id": c["id"], "name": c["name"]}, "tech_stack": c["tech_stack"],
            "open_findings": open_by_severity, "open_risks": risks,
            "last_incident": None if last is None else {
                "id": last["_id"], "status": last["status"],
                "at": last["timeline"].get("first_alert_at")},
        })
    return cards


@router.get("/group/risks")
def group_risks(user: User = Depends(group_admin)):
    names = company_names(user.group_id)
    board: dict[str, dict] = {}
    for r in yb.q("SELECT company_id, risk_type, status, finding_id, lesson_id FROM risk_exposure "
                  "WHERE group_id = %s ORDER BY risk_type", (user.group_id,)):
        row = board.setdefault(r["risk_type"], {"id": r["risk_type"], "risk_type": r["risk_type"],
                                                "companies": [], "proven_lesson": None})
        row["companies"].append({"id": r["company_id"], "name": names.get(r["company_id"]),
                                 "status": r["status"], "finding_id": r["finding_id"]})
    for row in board.values():
        cause = RISK_TO_CAUSE.get(row["risk_type"])
        if cause:
            row["proven_lesson"] = yb.q1(
                "SELECT id, cause_class, confirmations, confirmations - 2 * failures AS trust_score "
                "FROM lessons WHERE group_id = %s AND cause_class = %s AND status = 'proven' "
                "ORDER BY trust_score DESC LIMIT 1", (user.group_id, cause))
        row["affected"] = sum(1 for c in row["companies"] if c["status"] != "resolved")
    return list(board.values())


@router.post("/group/risks/{risk_type}/push")
def push_fix(risk_type: str, body: PushIn, user: User = Depends(group_admin)):
    target = yb.q1("SELECT id, group_id, name, shop FROM companies WHERE id = %s AND group_id = %s",
                   (body.company_id, user.group_id))
    if target is None:
        raise HTTPException(404, "Company not in your group")
    risk = yb.q1("SELECT status FROM risk_exposure WHERE company_id = %s AND risk_type = %s",
                 (body.company_id, risk_type))
    if risk is None or risk["status"] == "resolved":
        raise HTTPException(409, "That company has no open risk of this type")
    cause = RISK_TO_CAUSE.get(risk_type)
    lesson = cause and yb.q1(
        "SELECT id FROM lessons WHERE group_id = %s AND cause_class = %s AND status = 'proven' "
        "ORDER BY confirmations - 2 * failures DESC LIMIT 1", (user.group_id, cause))
    if not lesson:
        raise HTTPException(409, "No proven fix to push for this risk yet")

    # A finding in the target company's inbox, with the lesson attached.
    # Their agent proves it on their own data; their engineer decides.
    fid, _ = save_finding(Company(**target), source="group_push", test=risk_type,
                          severity="warning", summary=f"Group pushed a proven fix for {risk_type}",
                          raw={"pushed_by": user.email}, lesson_id=lesson["id"])
    yb.run("UPDATE risk_exposure SET status = 'pushed', lesson_id = %s, updated_at = now() "
           "WHERE company_id = %s AND risk_type = %s", (lesson["id"], body.company_id, risk_type))
    yb.audit(user.email, "push", body.company_id, fid, {"lesson_id": lesson["id"], "risk": risk_type})
    return {"finding_id": fid, "lesson_id": lesson["id"]}


@router.get("/settings/meko")
def get_meko(user: User = Depends(group_admin)):
    return {"mode": yb.get_setting("meko_mode", "on")}


@router.put("/settings/meko")
def set_meko(body: MekoModeIn, user: User = Depends(group_admin)):
    yb.run("INSERT INTO settings (key, value) VALUES ('meko_mode', %s) "
           "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (Jsonb(body.mode),))
    yb.audit(user.email, "meko_mode", None, None, {"mode": body.mode})
    return {"mode": body.mode}