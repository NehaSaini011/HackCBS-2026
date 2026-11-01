"""One-off test: does a lesson survive Meko's add -> promote -> knowledgebase_search?"""
import asyncio
import json
import re

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.settings import settings

HEADERS = {"Authorization": f"Bearer {settings.meko_api_key}", "User-Agent": "fixnet-group-api/1.0"}
DP = settings.meko_datapack
AGENT = "fixnet:c_pinecart"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
LESSON_TEXT = ("lesson_id: les_00000001\n"
               "cause_class: MISSING_INDEX\n"
               "symptoms: p95 latency spike; full table scan on a large table\n"
               "fix: create_index (filter_then_sort_desc). Recreate an index on the filtered column, "
               "then the sort column.")


def find_key(obj, key):
    """First value stored under `key` anywhere in nested JSON."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        obj = list(obj.values())
    if isinstance(obj, list):
        for item in obj:
            found = find_key(item, key)
            if found is not None:
                return found
    return None


async def call(session, tool, args):
    result = await asyncio.wait_for(session.call_tool(tool, args), timeout=60)
    text = "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    print(f"\n--- {tool} ({'ERROR' if result.isError else 'ok'}) ---\n{text[:1200]}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def main():
    async with streamablehttp_client(settings.meko_mcp_url, headers=HEADERS) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            conv = await call(session, "conversation_create", {
                "agent_id": AGENT, "title": "fixnet round-trip test",
                "session_id": "fixnet-roundtrip-c_pinecart", "datapack_id": DP})
            cid = find_key(conv, "conversation_id") or find_key(conv, "id")
            print("\n>>> conversation id:", cid)

            added = await call(session, "memory_add", {
                "text": LESSON_TEXT, "conversation_id": cid, "agent_id": AGENT,
                "datapack_id": DP, "metadata": json.dumps({"lesson_id": "les_00000001"})})
            ids = [u for u in UUID.findall(json.dumps(added)) if u not in (DP, cid)]
            if not ids:
                print("\n>>> memory_add returned no id; looking it up with memory_search")
                await asyncio.sleep(5)
                found = await call(session, "memory_search", {
                    "query": "MISSING_INDEX p95 latency spike full table scan",
                    "conversation_id": cid, "agent_id": AGENT, "datapack_id": DP, "limit": 3})
                ids = [u for u in UUID.findall(json.dumps(found)) if u not in (DP, cid)][:1]
            print("\n>>> memory ids:", ids)

            if ids:
                await call(session, "memory_promote", {
                    "conversation_id": cid, "memory_ids": ids, "agent_id": AGENT, "datapack_id": DP})

            print("\n>>> waiting 15 s for the knowledge base to index...")
            await asyncio.sleep(15)
            hits = await call(session, "knowledgebase_search", {
                "query": "MISSING_INDEX p95 latency spike full table scan",
                "conversation_id": cid, "datapack_id": DP, "limit": 5})
            survived = "les_00000001" in json.dumps(hits)
            print(f"\n>>> RESULT: lesson_id {'SURVIVED' if survived else 'NOT FOUND'} in knowledgebase_search")

asyncio.run(main())
