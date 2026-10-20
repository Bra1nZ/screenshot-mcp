#!/usr/bin/env python3
"""Проверка MCP-сервера по stdio: список тулов и реальный вызов."""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(REPO_ROOT, "server.py")


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=[SERVER], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print("server:", init.serverInfo.name, init.serverInfo.version, flush=True)

            tools = await session.list_tools()
            print(f"\nтулов: {len(tools.tools)}")
            for tool in tools.tools:
                params_list = ", ".join((tool.inputSchema.get("properties") or {}).keys())
                print(f"  - {tool.name}({params_list})")

            print("\n=== вызов console_open ===", flush=True)
            res = await session.call_tool("console_open", {"cwd": str(REPO_ROOT)})
            data = json.loads(res.content[0].text)
            print(data, flush=True)
            cid = data["console_id"]

            print("\n=== вызов console_exec ===", flush=True)
            res = await session.call_tool("console_exec", {"console_id": cid, "command": "echo 'привет из MCP'"})
            data = json.loads(res.content[0].text)
            print(json.dumps(data, ensure_ascii=False)[:300], flush=True)

            print("\n=== вызов console_state ===", flush=True)
            res = await session.call_tool("console_state", {"console_id": cid})
            print(res.content[0].text[:300], flush=True)

            print("\n=== вызов desktop_active_window ===", flush=True)
            res = await session.call_tool("desktop_active_window", {})
            print(res.content[0].text[:300], flush=True)

            print("\n=== вызов desktop_screenshot ===", flush=True)
            res = await session.call_tool("desktop_screenshot", {"console_id": cid, "preview": True})
            for item in res.content:
                print("  content:", item.type, str(getattr(item, "text", ""))[:220])

            print("\n=== вызов console_close ===", flush=True)
            res = await session.call_tool("console_close", {"console_id": cid})
            print(res.content[0].text, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
