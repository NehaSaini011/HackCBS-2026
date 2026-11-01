import asyncio
import json
import re

from app import yb
from app.settings import settings

# Verified against the live Meko server with scripts/meko_roundtrip.py:
#  - every call except conversation_create needs a conversation_id
#  - memory_add takes `text` and returns {"results": [{"id": ...}]}
#  - memory_promote takes a LIST `memory_ids`
#  - knowledgebase_search returns {"results": [{"chunk_text": ...}]}, text kept word for word
#  - a refusal can come back inside an "ok" reply as {"error": ...}, so we check for it
HEADERS = {"Authorization": f"Bearer {settings.meko_api_key}", "User-Agent": "fixnet-group-api/1.0"}
_conversations: dict[str, str] = {}      # company_id -> Meko conversation id (cached per process)


def _agent_id(company_id: str) -> str:
    # Each company gets its own private Meko memory store
    return f"fixnet:{company_id}"


async def _call(tool: str, args: dict):
    """Call one Meko tool over MCP. Returns the parsed JSON reply, or raises on any error."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(settings.meko_mcp_url, headers=HEADERS) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await asyncio.wait_for(session.call_tool(tool, args), timeout=30)
    text = "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    if result.isError:
        raise RuntimeError(f"Meko {tool} failed: {text[:300]}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"Meko {tool}: {data['error']} {data.get('detail', '')}"[:300])
    return data


def _run(tool: str, args: dict):
    # Our endpoints are plain (sync) functions running in worker threads, so we can
    # start a small event loop here for the async MCP client.
    return asyncio.run(_call(tool, args))


def _conversation(company_id: str) -> str:
    """One Meko conversation per company. session_id makes Meko reuse it across restarts."""
    if company_id not in _conversations:
        conv = _run("conversation_create", {
            "agent_id": _agent_id(company_id), "title": f"Fix network agent: {company_id}",
            "session_id": f"fixnet-{company_id}", "datapack_id": settings.meko_datapack})
        _conversations[company_id] = conv["id"]
    return _conversations[company_id]


def add(company_id: str, content: str) -> str:
    """Save a private memory for this company. Returns Meko's memory id."""
    if settings.meko_backend == "mock":
        ref = yb.new_id("mem")
        yb.run("INSERT INTO meko_mock (id, company_id, content) VALUES (%s, %s, %s)",
               (ref, company_id, content))
        return ref
    lesson = re.search(r"lesson_id:\s*(les_[0-9a-f]+)", content)
    data = _run("memory_add", {
        "text": content, "conversation_id": _conversation(company_id),
        "agent_id": _agent_id(company_id), "datapack_id": settings.meko_datapack,
        "metadata": json.dumps({"lesson_id": lesson.group(1) if lesson else None})})
    return data["results"][0]["id"]


def promote(ref: str, company_id: str) -> None:
    """Make a private memory shared knowledge for the whole group (one-way)."""
    if settings.meko_backend == "mock":
        yb.run("UPDATE meko_mock SET shared = true WHERE id = %s", (ref,))
        return
    data = _run("memory_promote", {
        "conversation_id": _conversation(company_id), "memory_ids": [ref],
        "agent_id": _agent_id(company_id), "datapack_id": settings.meko_datapack})
    if ref not in data.get("inserted_ids", []) + data.get("updated_ids", []):
        raise RuntimeError(f"Meko did not promote {ref}: {data}")


def search(query: str, company_id: str, limit: int = 5) -> list[str]:
    """Shared (promoted) knowledge that matches the query, as texts. Never private memories."""
    if settings.meko_backend == "mock":
        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 3]
        rows = yb.q("SELECT content FROM meko_mock WHERE shared ORDER BY created_at DESC")
        scored = sorted(rows, key=lambda r: -sum(w in r["content"].lower() for w in words))
        return [r["content"] for r in scored[:limit]
                if any(w in r["content"].lower() for w in words)]
    data = _run("knowledgebase_search", {
        "query": query, "conversation_id": _conversation(company_id),
        "datapack_id": settings.meko_datapack, "limit": limit})
    return [r.get("chunk_text", "") for r in data.get("results", [])]


def lesson_ids(texts: list[str]) -> list[str]:
    """Pull our lesson ids out of Meko's answers, in the order Meko ranked them."""
    seen: list[str] = []
    for t in texts:
        for lid in re.findall(r"lesson_id:\s*(les_[0-9a-f]+)", t):
            if lid not in seen:
                seen.append(lid)
    return seen


def memory_text(lesson_id: str, cause_class: str, symptoms: list[str],
                fix_template: str, fix_shape: str, fix_description: str) -> str:
    """The text stored in Meko. Redacted content only; checked before this is called."""
    return (f"lesson_id: {lesson_id}\n"
            f"cause_class: {cause_class}\n"
            f"symptoms: {'; '.join(symptoms)}\n"
            f"fix: {fix_template} ({fix_shape}). {fix_description}")
