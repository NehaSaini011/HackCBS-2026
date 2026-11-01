import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.settings import settings

HEADERS = {"Authorization": f"Bearer {settings.meko_api_key}", "User-Agent": "fixnet-group-api/1.0"}
WANTED = {"memory_add", "conversation_create"}


async def main():
    async with streamablehttp_client(settings.meko_mcp_url, headers=HEADERS) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for t in tools.tools:
                if t.name in WANTED:
                    schema = t.inputSchema
                    print(f"\n=== {t.name} ===")
                    print("required:", schema.get("required"))
                    for name, spec in schema.get("properties", {}).items():
                        print(f"  {name}: {str(spec.get('description', ''))[:160]!r}")

asyncio.run(main())