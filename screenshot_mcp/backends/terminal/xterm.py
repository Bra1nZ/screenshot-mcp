"""Окно терминала xterm — работает под любым X11."""

from __future__ import annotations

import shutil

from screenshot_mcp.backends.base import TerminalBackend


class XTermTerminal(TerminalBackend):
    name = "xterm"

    def available(self) -> bool:
        return shutil.which("xterm") is not None

    def spawn_argv(self, launcher: str, args: list[str], title: str | None = None) -> list[str]:
        cmd = ["xterm"]
        if title:
            cmd += ["-T", title]
        return cmd + ["-e", "/bin/bash", launcher, *args]
