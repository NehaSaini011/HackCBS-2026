from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["info", "warning", "critical"]
TestName = Literal["missing_index", "long_transactions", "connections",
                   "security", "latency", "certificate"]
Status = Literal["open", "diagnosed", "proving", "awaiting_approval", "applying",
                 "resolved", "rejected", "unknown", "proof_failed"]
CauseClass = Literal["MISSING_INDEX", "LOCK_CONTENTION", "UNKNOWN"]


# ---------- C1: what Alertmanager sends ----------
class AMAlert(BaseModel):
    status: Literal["firing", "resolved"]
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}
    startsAt: Optional[datetime] = None
    fingerprint: str                      # same value every time the same alert repeats


class AMWebhook(BaseModel):
    status: str
    alerts: list[AMAlert]
    # Alertmanager sends more fields (receiver, groupKey...). Pydantic ignores extras.


# ---------- C2: what Person 1's test adapters send ----------
class FindingIn(BaseModel):
    shop: Literal["a", "b", "c"]
    source: str = Field(max_length=50)
    test: TestName
    severity: Severity
    summary: str = Field(max_length=500)
    raw: dict[str, Any] = {}
    observed_at: Optional[datetime] = None


# ---------- C7: login ----------
class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


# ---------- what the web app sends ----------
class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class MekoModeIn(BaseModel):
    mode: Literal["on", "off"]


class PushIn(BaseModel):
    company_id: str


# ---------- C4 pieces: what the agent writes into an incident ----------
class Evidence(BaseModel):
    check: str                 # e.g. "slow_queries"
    query: str                 # the SQL the agent ran (stays inside this company)
    result: str                # e.g. "max 1,900 ms over 412 calls"


class Diagnosis(BaseModel):
    cause_class: CauseClass
    explanation: str
    evidence: list[Evidence] = []


class Fix(BaseModel):
    template: Literal["create_index"]   # the approved list; add types here, never free SQL
    sql: str
    test_sql: str = ""
    params: list = []


class Proof(BaseModel):
    method: Literal["fork", "fake", "none"]
    fix_sql: str                         # the exact SQL that was proven (Approve checks it)
    before_p95_ms: Optional[float] = None
    after_p95_ms: Optional[float] = None
    passed: bool
    error: Optional[str] = None
    fork_id: Optional[str] = None


class MekoEvent(BaseModel):
    op: Literal["recall", "store", "share", "skipped", "error"]
    text: str
    at: datetime


class IncidentCreate(BaseModel):
    finding_ids: list[str]
    meko_mode: Literal["on", "off"]


class IncidentUpdate(BaseModel):
    # Every field is optional: the agent sends only what changed.
    status: Optional[Status] = None
    diagnosis: Optional[Diagnosis] = None
    recalled_lesson: Optional[dict[str, Any]] = None
    fix: Optional[Fix] = None
    proof: Optional[Proof] = None
    applied: Optional[bool] = None
    meko_activity_add: list[MekoEvent] = []           # appended, never replaced
    timeline: dict[str, datetime] = {}                # e.g. {"diagnosed_at": ...}


# ---------- C5: lessons (agent -> Group API) ----------
class LessonMatchIn(BaseModel):
    cause_class: CauseClass
    symptoms: list[str]


class LessonIn(BaseModel):
    cause_class: CauseClass
    symptoms: list[str]
    fix_template: Literal["create_index"]
    fix_shape: Literal["filter_only", "filter_then_sort_desc"]
    fix_description: str = Field(max_length=300)
    incident_id: str
    before_p95_ms: float
    after_p95_ms: float


class LessonResultIn(BaseModel):
    incident_id: str
    before_p95_ms: Optional[float] = None
    after_p95_ms: Optional[float] = None