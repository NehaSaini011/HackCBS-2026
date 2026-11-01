import httpx

from agent import config

client = httpx.Client(base_url=config.GROUP_API_URL, timeout=30,
                      headers={"Authorization": f"Bearer {config.COMPANY_API_KEY}"})


def _ok(r: httpx.Response):
    if r.status_code >= 400:
        raise RuntimeError(f"{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:300]}")
    return r.json()


def work() -> dict:
    return _ok(client.get("/agent/work"))


def create_incident(finding_ids: list[str], meko_mode: str) -> str:
    return _ok(client.post("/agent/incidents",
                           json={"finding_ids": finding_ids, "meko_mode": meko_mode}))["id"]


def update_incident(incident_id: str, **fields) -> dict:
    return _ok(client.put(f"/agent/incidents/{incident_id}", json=fields))


def match_lessons(cause_class: str, symptoms: list[str]) -> dict:
    return _ok(client.post("/lessons/match", json={"cause_class": cause_class, "symptoms": symptoms}))


def share_lesson(body: dict) -> dict:
    return _ok(client.post("/lessons", json=body))


def _result(lesson_id: str, action: str, incident_id: str, proof: dict) -> dict:
    return _ok(client.post(f"/lessons/{lesson_id}/{action}", json={
        "incident_id": incident_id, "before_p95_ms": proof.get("before_p95_ms"),
        "after_p95_ms": proof.get("after_p95_ms")}))


def confirm_lesson(lesson_id: str, incident_id: str, proof: dict) -> dict:
    return _result(lesson_id, "confirm", incident_id, proof)


def fail_lesson(lesson_id: str, incident_id: str, proof: dict) -> dict:
    return _result(lesson_id, "fail", incident_id, proof)
