#!/usr/bin/env python3
"""Сценарий агента через настоящий MCP-протокол: окно → команды → фокус → снимок."""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "server.py")


async def call(session, name, args):
    res = await session.call_tool(name, args)
    text = res.content[0].text
    images = [c for c in res.content if c.type == "image"]
    try:
        data = json.loads(text)
    except ValueError:
        data = text
    return data, images


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=[SERVER], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"сервер: {init.serverInfo.name} {init.serverInfo.version}\n", flush=True)

            print("1) console_open", flush=True)
            info, _ = await call(session, "console_open", {"cwd": ROOT})
            print("   ", info, flush=True)
            cid = info["console_id"]

            print("\n2) console_exec — команда, её вывод и код возврата", flush=True)
            out, _ = await call(session, "console_exec", {
                "console_id": cid, "command": "echo '--- агент работает ---' && date && python3 -c 'print(2**16)'",
            })
            print("   exit_code:", out["exit_code"], "| timed_out:", out["timed_out"], flush=True)
            print("   вывод:", out["output"].strip().replace("\r\n", " | ")[:180], flush=True)

            print("\n3) console_state", flush=True)
            state, _ = await call(session, "console_state", {"console_id": cid})
            print("   ", state, flush=True)

            print("\n4) desktop_active_window", flush=True)
            act, _ = await call(session, "desktop_active_window", {})
            print("   ", act, flush=True)

            print("\n5) desktop_screenshot (с поднятием окна консоли)", flush=True)
            meta, images = await call(session, "desktop_screenshot", {"console_id": cid})
            print("   ok:", meta.get("ok"), "| путь:", meta.get("path"))
            print("   копия:", meta.get("copies"))
            print("   размер:", meta.get("width"), "x", meta.get("height"), "| байт:", meta.get("bytes"))
            print("   активное окно в момент снимка:", meta.get("active_window"))
            print("   картинок в ответе:", len(images))

            print("\n6) коды возврата (true / false)", flush=True)
            for cmd in ("true", "false"):
                out, _ = await call(session, "console_exec", {"console_id": cid, "command": cmd})
                print(f"   $ {cmd:8s} -> exit_code={out['exit_code']}", flush=True)

            print("\n7) console_close", flush=True)
            closed, _ = await call(session, "console_close", {"console_id": cid})
            print("   ", closed, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
