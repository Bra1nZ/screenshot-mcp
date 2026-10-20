#!/usr/bin/env python3
"""Полный E2E: окно -> команды -> фокус -> снимок (с проверкой, что консоль впереди)."""

import os
import subprocess
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
import server  # noqa: E402 - путь до модуля задаётся выше

print("=== 1. открываем консоль ===", flush=True)
info = server.console_open(cwd=str(REPO_ROOT))
cid = info["console_id"]
print(info, flush=True)
time.sleep(1.5)

print("\n=== 2. выполняем команды ===", flush=True)
for cmd in ["pwd", "ls -la | head -4", "echo 'готово: сборка прошла успешно'", "false"]:
    res = server.console_exec(cid, cmd, timeout=20)
    print(f"$ {cmd}\n  exit={res['exit_code']} timeout={res['timed_out']}\n  {res['output'].strip()[:200]!r}", flush=True)

print("\n=== 3. перекрываем окно другим терминалом ===", flush=True)
other = subprocess.Popen(["konsole", "--separate", "-e", "bash", "-c", "sleep 120"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.5)
print("активное окно сейчас:", server.desktop_active_window(), flush=True)

print("\n=== 4. поднимаем консоль ===", flush=True)
print(server.desktop_focus(cid), flush=True)
time.sleep(0.8)
print("активное окно после:", server.desktop_active_window(), flush=True)

print("\n=== 5. снимок экрана ===", flush=True)
shot_path = os.path.join(tempfile.gettempdir(), "screenshot-mcp-e2e.png")
meta, img = server.desktop_screenshot(console_id=cid, path=shot_path, copy_to_project=True)
print(meta, flush=True)
print("превью:", type(img).__name__ if img else None, flush=True)

print("\n=== 6. список окон ===", flush=True)
wins = server.desktop_list_windows()
for w in wins.get("windows", []):
    print("  ", w.get("class"), "|", (w.get("caption") or "")[:50], "| active:", w.get("active"), "| pid:", w.get("pid"))

print("\n=== 7. закрываем ===", flush=True)
print(server.console_close(cid), flush=True)
other.terminate()
