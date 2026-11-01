import re
from datetime import datetime, timezone

from agent import ai, evidence
from agent import group_client as group

# Plain English words that may also be column names; allowed in lessons
GENERIC_WORDS = {"name", "email", "city", "status", "time", "endpoint", "version",
                 "description", "category", "stock", "notes", "price"}
# Our own wording, used if Gemini's keeps leaking names. Contains no names by construction.
SAFE_DESCRIPTION = {
    "filter_then_sort_desc": "Recreate an index on the filtered column followed by the sort "
                             "column, newest first, built without blocking writes.",
    "filter_only": "Create an index on the filtered column, built without blocking writes.",
}


def event(op: str, text: str) -> dict:
    return {"op": op, "text": text[:300], "at": datetime.now(timezone.utc).isoformat()}


def leaks(texts: list[str], private: list[str]) -> list[str]:
    joined = " ".join(texts).lower()
    return [w for w in private
            if w not in GENERIC_WORDS and re.search(rf"\b{re.escape(w)}\b", joined)]


def share_new_lesson(incident_id: str, cause_class: str, symptoms: list[str],
                     shape: str, proof: dict) -> list[dict]:
    activity = []
    private = evidence.private_names()
    draft = None
    for _ in range(2):                                  # Gemini gets two tries
        d = ai.write_lesson(cause_class, shape, symptoms, private)
        if d is not None and not leaks([d.fix_description, *d.symptoms], private):
            draft = d
            break
        if d is not None:
            activity.append(event("skipped", "Redaction check blocked Gemini's wording"))
    if draft is None:
        draft = ai.LessonDraft(symptoms=symptoms, fix_description=SAFE_DESCRIPTION[shape])
        activity.append(event("skipped", "Used the built-in safe wording for this lesson"))

    resp = group.share_lesson({
        "cause_class": cause_class, "symptoms": draft.symptoms[:5],
        "fix_template": "create_index", "fix_shape": shape,
        "fix_description": draft.fix_description[:300], "incident_id": incident_id,
        "before_p95_ms": proof.get("before_p95_ms") or 0, "after_p95_ms": proof.get("after_p95_ms") or 0,
    })
    return activity + resp["meko_activity"]
