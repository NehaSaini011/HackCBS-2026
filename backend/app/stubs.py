import json
import os
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter()
# contracts/ sits next to backend/ in the repo
CONTRACTS = Path(os.environ.get("CONTRACTS_DIR", Path(__file__).resolve().parents[2] / "contracts"))


def load(name: str):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


@router.post("/ingest/alertmanager", status_code=202)
async def stub_alert(request: Request):
    print("ALERT RECEIVED:", (await request.body())[:2000])
    return {"accepted": True}


@router.post("/ingest/finding", status_code=202)
async def stub_finding(request: Request):
    print("FINDING RECEIVED:", (await request.body())[:2000])
    return {"accepted": True}


@router.get("/findings")
def stub_findings():
    return load("findings_list.json")


@router.get("/incidents/{incident_id}")
def stub_incident(incident_id: str):
    return load("incident.json")


@router.get("/lessons")
def stub_lessons():
    return load("lessons.json")


@router.get("/group/overview")
def stub_overview():
    return load("group_overview.json")


@router.get("/group/risks")
def stub_risks():
    return load("group_risks.json")


@router.get("/settings/meko")
def stub_meko():
    return load("meko.json")