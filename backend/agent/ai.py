from google import genai
from google.genai import types
from pydantic import BaseModel

from agent import config

client = genai.Client(api_key=config.GEMINI_API_KEY) if config.GEMINI_API_KEY else None


def explain(cause_class: str, evidence: list[dict]) -> str:
    """Two or three plain sentences for the engineer. Falls back to a plain summary."""
    facts = "\n".join(f"- {e['check']}: {e['result']}" for e in evidence)
    fallback = f"Rules matched {cause_class}. Evidence: " + "; ".join(
        f"{e['check']} = {e['result']}" for e in evidence)
    if client is None:
        return fallback
    prompt = (
        "You help an on-call engineer understand a database incident.\n"
        f"The cause class, decided by rules, is {cause_class}. Do not change it.\n"
        f"Evidence collected from the database:\n{facts}\n\n"
        "Write 2 or 3 short, plain sentences: what is wrong, and which evidence shows it. "
        "Use only numbers that appear in the evidence. Do not write SQL. Do not suggest a fix."
    )
    try:
        r = client.models.generate_content(
            model=config.GEMINI_TEXT_MODEL, contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=300))
        return (r.text or "").strip() or fallback
    except Exception as e:
        print("gemini explain failed:", e)
        return fallback


class LessonDraft(BaseModel):
    symptoms: list[str]          # 3 to 5 short generic phrases
    fix_description: str         # one sentence, generic


def write_lesson(cause_class: str, fix_shape: str, symptoms: list[str],
                 forbidden: list[str]) -> LessonDraft | None:
    """A redacted, reusable lesson. Returns None if Gemini is unavailable."""
    if client is None:
        return None
    prompt = (
        "Write a reusable lesson about a database incident, to share with other companies.\n"
        f"Cause class: {cause_class}. Fix that worked: create an index, shape '{fix_shape}' "
        "(filter_then_sort_desc = an index on the filtered column, then the sort column, newest first).\n"
        f"Symptoms observed: {symptoms}\n\n"
        "Rules: describe things generically ('a large table', 'the filtered column'). "
        "Never include table names, column names, hostnames, numbers of rows, query text or company names. "
        f"These exact words are forbidden: {forbidden}"
    )
    try:
        r = client.models.generate_content(
            model=config.GEMINI_TEXT_MODEL, contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",   # answer as JSON...
                response_schema=LessonDraft,             # ...in exactly this shape
            ))
        return r.parsed if isinstance(r.parsed, LessonDraft) else LessonDraft.model_validate_json(r.text)
    except Exception as e:
        print("gemini lesson failed:", e)
        return None