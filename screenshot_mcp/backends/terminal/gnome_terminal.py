"""Окно терминала GNOME Terminal.

gnome-terminal форкается и сразу отдаёт управление уже running-инстансу,
поэтому его окно приходится искать по заголовку, а не по PID.
"""

from __future__ import annotations

import shutil

from screenshot_mcp.backends.base import TerminalBackend


class GnomeTerminal(TerminalBackend):
    name = "gnome-terminal"

    def available(self) -> bool:
        return shutil.which("gnome-terminal") is not None

    def spawn_argv(self, launcher: str, args: list[str], title: str | None = None) -> list[str]:
        cmd = ["gnome-terminal", "--window"]
        if title:
            cmd += ["--title", title]
        return cmd + ["--", "/bin/bash", launcher, *args]

    def owns_window(self) -> bool:
        return False
