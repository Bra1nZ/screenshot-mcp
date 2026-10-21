"""Заглушка: окружение не умеет поднимать окна (снимки при этом работают)."""

from __future__ import annotations

from screenshot_mcp.backends.base import FocusBackend, WindowTarget


class NoFocus(FocusBackend):
    name = "none"

    def available(self) -> bool:
        return True

    def activate(self, target: WindowTarget) -> dict:
        return {
            "activated": False,
            "error": "в этом окружении нечем поднять окно на передний план",
            "steps": [],
        }
