# Cross-SDK check: call the TypeScript spike server with the official Python SDK v2 client.
# Run: uv run --with mcp==2.3.0 python py_client.py   (server must be running: node serve.mjs)
import os

import anyio
from mcp import Client

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8787/mcp")
ARGS = {"need": "run an LLM offline on my laptop", "os": "macos", "offline_required": True}


async def main() -> None:
    for mode in ("legacy", "auto"):
        async with Client(URL, mode=mode) as client:
            tools = await client.list_tools()
            result = await client.call_tool("find_software", ARGS)
            sc = result.structured_content or {}
            print(
                {
                    "mode": mode,
                    "protocol_version": client.protocol_version,
                    "tools": [t.name for t in tools.tools],
                    "is_error": result.is_error,
                    "picks": [p["slug"] for p in sc.get("picks", [])],
                    "server_saw_era": sc.get("era"),
                }
            )


if __name__ == "__main__":
    anyio.run(main)
