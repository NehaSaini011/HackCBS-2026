"""Platform advisories: the service provider publishes a fix for a GLOBAL problem.

A company-specific problem enters the network when a sister company solves it.
A global one (a CVE in a language runtime, a database bug, a cloud outage pattern)
should not wait for that: the platform publishes it at once, every exposed company
gets it in its inbox, and the fund's risk board shows who is exposed and who has patched.

  POST /advisories                  provider only (X-Provider-Token header)
  GET  /advisories                  anyone logged in; the group view of each advisory
  POST /advisories/{id}/patched     a company engineer: "we have applied it"
"""
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app import meko, mongo, yb
from app.deps import Company, User, current_user, engineer
from app.routes_ingest import FINAL, mark_risk
from app.settings import settings

router = APIRouter()

PLATFORM = "platform"            # Meko agent id becomes "fixnet:platform"


class AdvisoryIn(BaseModel):
    title: str = Field(min_length=5, max_length=120)
    category: str = Field(default="security", min_length=2, max_length=40)
    severity: Literal["info", "warning", "critical"] = "critical"
    affects: list[str] = Field(min_length=1, max_length=10)   # stack keywords, or ["*"] for every company
    summary: str = Field(min_length=10, max_length=600)
    fix: str = Field(min_length=5, max_length=600)
    mitigation: str | None = Field(default=None, max_length=600)
    source_url: str | None = Field(default=None, max_length=300)


def provider(x_provider_token: str | None = Header(default=None)) -> None:
    """Only the platform operator (us) may publish. Not a fund admin, not a company."""
    if not settings.provider_token:
        raise HTTPException(503, "Provider publishing is not configured")
    if not x_provider_token or not secrets.compare_digest(x_provider_token, settings.provider_token):
        raise HTTPException(401, "Invalid provider token")


def now() -> datetime:
    return datetime.now(timezone.utc)


def risk_type(advisory_id: str) -> str:
    return f"advisory:{advisory_id}"


def matches(tech_stack: str | None, affects: list[str]) -> bool:
    """Is a company with this tech stack exposed? Keyword match, case-insensitive; '*' = all."""
    stack = (tech_stack or "").lower()
    for word in affects:
        word = word.strip().lower()
        if word == "*" or (word and word in stack):
            return True
    return False


@router.post("/advisories", status_code=201)
def publish(body: AdvisoryIn, _: None = Depends(provider)):
    adv_id = yb.new_id("adv")

    # 1. Into Meko's shared knowledge, so every agent's recall can find it
    text = (f"advisory_id: {adv_id}\nsource: platform advisory\ntitle: {body.title}\n"
            f"category: {body.category}\naffects: {', '.join(body.affects)}\n"
            f"summary: {body.summary}\nfix: {body.fix}"
            + (f"\nmitigation: {body.mitigation}" if body.mitigation else ""))
    meko_ref, meko_status = None, "not stored"
    try:
        meko_ref = meko.add(PLATFORM, text)
        meko.promote(meko_ref, PLATFORM)
        meko_status = "stored and shared"
    except Exception as e:
        meko_status = f"failed: {e}"[:200]

    yb.run("INSERT INTO advisories (id, title, category, severity, affects, summary, fix, "
           "mitigation, source_url, meko_ref) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
           (adv_id, body.title, body.category, body.severity, Jsonb(body.affects), body.summary,
            body.fix, body.mitigation, body.source_url, meko_ref))

    # 2. Into the inbox of every exposed company, in every fund
    exposed = []
    summary = f"Platform advisory: {body.title}. Fix: {body.fix}"
    for c in yb.q("SELECT id, group_id, name, shop, tech_stack FROM companies ORDER BY id"):
        if not matches(c["tech_stack"], body.affects):
            continue
        company = Company(id=c["id"], group_id=c["group_id"], name=c["name"], shop=c["shop"])
        fid, t = yb.new_id("f"), now()
        mongo.findings.insert_one({
            "_id": fid, "group_id": company.group_id, "company_id": company.id,
            "source": "platform_advisory", "test": body.category, "severity": body.severity,
            "summary": summary[:500], "advisory_id": adv_id,
            "raw": {"advisory_id": adv_id, "fix": body.fix, "mitigation": body.mitigation,
                    "source_url": body.source_url},
            "fingerprint": risk_type(adv_id), "embedding": None,
            "status": "open", "incident_id": None, "lesson_id": None,
            # claimed with no claimed_at: agents never pick it up; a person acts on an advisory
            "claimed": True,
            "duplicates": 0, "first_seen": t, "last_seen": t,
        })
        mark_risk(company, risk_type(adv_id), fid)
        yb.audit("platform", "advisory_push", company.id, fid, {"advisory_id": adv_id})
        exposed.append({"id": company.id, "name": company.name, "finding_id": fid})

    yb.audit("platform", "advisory_publish", None, adv_id,
             {"title": body.title, "exposed": len(exposed), "meko": meko_status})
    return {"id": adv_id, "exposed": exposed, "meko": meko_status}


@router.get("/advisories")
def list_advisories(user: User = Depends(current_user)):
    names = {r["id"]: r["name"] for r in
             yb.q("SELECT id, name FROM companies WHERE group_id = %s", (user.group_id,))}
    out = []
    for a in yb.q("SELECT id, title, category, severity, affects, summary, fix, mitigation, "
                  "source_url, published_at FROM advisories ORDER BY published_at DESC"):
        rows = yb.q("SELECT company_id, status FROM risk_exposure WHERE risk_type = %s "
                    "AND group_id = %s", (risk_type(a["id"]), user.group_id))
        a["exposed"] = len(rows)
        a["patched"] = sum(1 for r in rows if r["status"] == "resolved")
        if user.role == "group_admin":
            a["companies"] = [{"id": r["company_id"], "name": names.get(r["company_id"]),
                               "status": "patched" if r["status"] == "resolved" else "exposed"}
                              for r in rows]
        else:
            mine = next((r for r in rows if r["company_id"] == user.company_id), None)
            a["my_status"] = (None if mine is None else
                              "patched" if mine["status"] == "resolved" else "exposed")
        out.append(a)
    return out


@router.post("/advisories/{advisory_id}/patched")
def mark_patched(advisory_id: str, user: User = Depends(engineer)):
    risk = yb.q1("SELECT status FROM risk_exposure WHERE company_id = %s AND risk_type = %s",
                 (user.company_id, risk_type(advisory_id)))
    if risk is None:
        raise HTTPException(404, "Your company is not exposed to this advisory")
    if risk["status"] == "resolved":
        raise HTTPException(409, "Already marked as patched")
    yb.run("UPDATE risk_exposure SET status = 'resolved', updated_at = now() "
           "WHERE company_id = %s AND risk_type = %s", (user.company_id, risk_type(advisory_id)))
    mongo.findings.update_many(
        {"company_id": user.company_id, "advisory_id": advisory_id, "status": {"$nin": FINAL}},
        {"$set": {"status": "resolved", "resolved_at": now()}})
    yb.audit(user.email, "advisory_patched", user.company_id, advisory_id, None)
    return {"advisory_id": advisory_id, "status": "patched"}
