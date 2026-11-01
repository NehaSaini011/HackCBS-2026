import time
import traceback
from datetime import datetime, timezone

from agent import ai, config, evidence, fixes, learner, rules
from agent import group_client as group

# Remembered between "proven" and "approved". Lost on restart; sensible defaults are used then.
pending: dict[str, dict] = {}
LESSON_FIELDS = ("id", "cause_class", "confirmations", "status", "fix_shape")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def event(op: str, text: str) -> dict:
    return {"op": op, "text": text[:300], "at": now()}


def handle_finding(f: dict, meko_mode: str) -> None:
    iid = group.create_incident([f["id"]], meko_mode)
    print(f"[{iid}] finding {f['id']} ({f['test']}): {f['summary']}")

    if f["test"] not in ("latency", "missing_index"):
        group.update_incident(iid, status="unknown", diagnosis={
            "cause_class": "UNKNOWN", "evidence": [],
            "explanation": "Shown for review. The agent does not fix this test type automatically yet."})
        return

    # 1. Evidence and diagnosis
    ev = evidence.collect()
    cause, symptoms = rules.decide(ev.facts)
    group.update_incident(iid, status="diagnosed", timeline={"diagnosed_at": now()}, diagnosis={
        "cause_class": cause, "explanation": ai.explain(cause, ev.items), "evidence": ev.items})
    if cause != "MISSING_INDEX":
        group.update_incident(iid, status="unknown")   # explained, nothing offered
        return
    target = ev.facts["target"]

    # 2. Recall
    lesson = f.get("lesson")
    if lesson:
        group.update_incident(iid, meko_activity_add=[event("recall", f"Pushed by the group: {lesson['id']}")])
    elif meko_mode == "on":
        m = group.match_lessons(cause, symptoms)
        lesson = m["lessons"][0] if m["lessons"] else None
        group.update_incident(iid, meko_activity_add=m["meko_activity"])
    else:
        group.update_incident(iid, meko_activity_add=[event("skipped", "Meko is OFF: no recall")])

    # 3. Prove on a fork: the lesson's fix only, or every candidate
    group.update_incident(iid, status="proving")
    shapes = [lesson["fix_shape"]] if lesson else fixes.candidate_shapes(target)
    passing, last = fixes.prove_shapes(shapes, target)
    if lesson and not passing:
        group.fail_lesson(lesson["id"], iid, last[1])          # the group learns it did not work here
        group.update_incident(iid, meko_activity_add=[
            event("skipped", f"{lesson['id']} did not pass its proof here; trying the other fixes")])
        others = [s for s in fixes.candidate_shapes(target) if s != lesson["fix_shape"]]
        passing, last = fixes.prove_shapes(others, target)
        lesson = None
    # Improvement 2: a lesson counts as "used" only after its own fix passed its proof here.
    # Setting it earlier would make handle_approved confirm a lesson whose fix was not the one applied.
    if lesson and passing:
        group.update_incident(iid, recalled_lesson={k: lesson.get(k) for k in LESSON_FIELDS})
    if not passing:
        group.update_incident(iid, status="proof_failed",
                              **({"fix": last[0], "proof": last[1]} if last else {}))
        return

    fix, proof = min(passing, key=lambda fp: fp[1].get("after_p95_ms") or 1e9)
    group.update_incident(iid, status="awaiting_approval", fix=fix, proof=proof,
                          timeline={"proven_at": now()})
    pending[iid] = {"symptoms": symptoms, "endpoint": ev.facts.get("endpoint")}
    print(f"[{iid}] proven {proof.get('before_p95_ms')} -> {proof.get('after_p95_ms')} ms; waiting for approval")


def handle_approved(inc: dict) -> None:
    iid, sql = inc["id"], inc["fix"]["sql"]
    group.update_incident(iid, applied=True)      # mark first, so it is never applied twice
    print(f"[{iid}] approved, applying: {sql}")
    try:
        fixes.apply(sql)
    except Exception as e:
        print(f"[{iid}] APPLY FAILED: {e}")
        group.update_incident(iid, meko_activity_add=[event("error", f"Applying the fix failed: {e}")])
        return

    ctx = pending.pop(iid, {})
    recovered, p95 = fixes.verify(ctx.get("endpoint") or evidence.slowest_endpoint())
    if not recovered:
        group.update_incident(iid, meko_activity_add=[event("error", f"Applied, but p95 is still {p95} ms")])
        return
    group.update_incident(iid, status="resolved", timeline={"resolved_at": now()})
    print(f"[{iid}] resolved, p95 now {p95} ms")

    # 4. Learn
    if inc.get("meko_mode") == "off":
        group.update_incident(iid, meko_activity_add=[event("skipped", "Meko is OFF: nothing stored")])
    elif inc.get("recalled_lesson"):
        lid = inc["recalled_lesson"]["id"]
        r = group.confirm_lesson(lid, iid, inc["proof"])
        group.update_incident(iid, meko_activity_add=[
            event("share", f"{lid} confirmed here (confirmations {r.get('confirmations', '?')})")])
    else:
        activity = learner.share_new_lesson(iid, "MISSING_INDEX",
                                            ctx.get("symptoms") or rules.DEFAULT_SYMPTOMS,
                                            fixes.shape_of(sql), inc["proof"])
        group.update_incident(iid, meko_activity_add=activity)


def main() -> None:
    print(f"Agent for {config.COMPANY} (shop {config.SHOP}) polling {config.GROUP_API_URL}"
          f"{'  [FAKE PROVER]' if config.FAKE_PROVER else ''}")
    while True:
        try:
            work = group.work()
            for inc in work["approved_incidents"]:
                handle_approved(inc)
            for f in work["new_findings"]:
                handle_finding(f, work["meko_mode"])
        except Exception as e:
            print("loop error:", repr(e))
            traceback.print_exc()
        time.sleep(config.POLL_SECONDS)


if __name__ == "__main__":
    main()
