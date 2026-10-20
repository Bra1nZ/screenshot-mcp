#!/usr/bin/env python3
"""Проверка интерактивных инструментов: программа ждёт ввода."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

info = server.console_open(cwd=os.path.expanduser("~"))
cid = info["console_id"]
print("console:", cid, flush=True)
time.sleep(1.2)

print("\n1) запускаем программу, ждущую ввода", flush=True)
res = server.console_exec(cid, "python3 -c \"n = input('Введите число: '); print('получено', n * 2)\"", timeout=6)
print("   timed_out:", res["timed_out"], "| вывод:", repr(res["output"][-120:]), flush=True)

print("\n2) отправляем ввод", flush=True)
server.console_send(cid, "21", enter=True)
time.sleep(1.5)
cursor = server.console_state(cid)
out = server.console_read(cid, cursor=0)
print("   вывод:", repr(out["output"][-160:]), flush=True)

print("\n3) ctrl+c на запущенной программе", flush=True)
server.console_exec(cid, "sleep 120", timeout=4)
server.console_key(cid, "ctrl+c")
time.sleep(1.0)
out = server.console_read(cid, cursor=0)
print("   хвост:", repr(out["output"][-120:]), flush=True)

print("\n4) стрелка вверх (история команд)", flush=True)
server.console_key(cid, "up")
time.sleep(0.5)
out = server.console_read(cid, cursor=0)
print("   хвост:", repr(out["output"][-120:]), flush=True)

server.console_close(cid)
print("\nзакрыто", flush=True)
