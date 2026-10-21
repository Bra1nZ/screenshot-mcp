"""Снимок экрана через Spectacle — штатное средство KDE Plasma."""

from __future__ import annotations

import shutil

from screenshot_mcp.backends.base import ScreenshotBackend
from screenshot_mcp.backends.screenshot.common import run_capture, session_locked


class SpectacleScreenshot(ScreenshotBackend):
    name = "spectacle"

    def available(self) -> bool:
        return shutil.which("spectacle") is not None

    def capture(self, path: str, delay_ms: int = 0) -> dict:
        attempts = [
            ["spectacle", "-b", "-n", "-o", path],
            ["spectacle", "--background", "--nonotify", "--output", path],
        ]
        result = {"ok": False, "path": path}
        for cmd in attempts:
            if not shutil.which(cmd[0]):
                continue
            result = run_capture(cmd, path, delay_ms)
            if result.get("ok"):
                return result
        if session_locked():
            result["error"] = (
                "экран заблокирован (активен lock screen) — композитор не отдаёт снимок. "
                "Разблокируй сессию и повтори."
            )
        return result
