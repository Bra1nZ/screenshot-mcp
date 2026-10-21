"""Окно терминала Konsole — штатный для KDE Plasma."""

from __future__ import annotations

import shutil

from screenshot_mcp.backends.base import TerminalBackend


class KonsoleTerminal(TerminalBackend):
    name = "konsole"

    def available(self) -> bool:
        return shutil.which("konsole") is not None

    def spawn_argv(self, launcher: str, args: list[str], title: str | None = None) -> list[str]:
        cmd = ["konsole", "--separate"]
        if title:
            cmd += ["--title", title]
        return cmd + ["-e", "/bin/bash", launcher, *args]
