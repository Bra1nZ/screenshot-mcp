#!/usr/bin/env python3
"""Проверка pty-моста: окно, ввод команды, вывод, код возврата."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from session import ConsoleSession

session = ConsoleSession(cwd=os.path.expanduser("~"), cols=100, rows=30)
print("starting...", flush=True)
session.start()
print("console_id:", session.id, "shell pid:", session._shell_pid, flush=True)

time.sleep(1.0)
print("--- initial buffer ---")
print(repr(session.read_since(0)[:400]), flush=True)

for cmd in ["echo привет из-под-агента", "pwd", "whoami", "ls -la | head -3", "exit 42"]:
    print(f"\n=== $ {cmd}", flush=True)
    res = session.exec_command(cmd, timeout=15)
    print("exit_code:", res["exit_code"], "timed_out:", res["timed_out"], flush=True)
    print("output:", repr(res["output"][:500]), flush=True)

print("\nstate:", session.state(), flush=True)
session.close()
print("closed", flush=True)
