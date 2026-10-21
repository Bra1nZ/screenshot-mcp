#!/usr/bin/env python3
"""Проверка: репортер умирает вместе с сервером."""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from screenshot_mcp.backends.base import WindowTarget
from screenshot_mcp.runtime import get_runtime

PATTERN = "screenshot_mcp/reporter[.]py"


def count() -> int:
    proc = subprocess.run(["pgrep", "-c", "-f", PATTERN], capture_output=True, text=True, check=False)
    return int(proc.stdout.strip() or 0)


def main() -> int:
    runtime = get_runtime()
    runtime.focus.activate(WindowTarget(pid=None, title_hint="", app_hint="konsole"))
    time.sleep(1.5)
    print("репортеров при работающем сервере:", count())
    return 0


if __name__ == "__main__":
    sys.exit(main())
