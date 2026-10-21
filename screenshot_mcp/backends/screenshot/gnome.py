"""Снимок экрана в GNOME: gnome-screenshot (через xdg-desktop-portal)."""

from __future__ import annotations

import shutil

from screenshot_mcp.backends.base import ScreenshotBackend
from screenshot_mcp.backends.screenshot.common import run_capture


class GnomeScreenshot(ScreenshotBackend):
    name = "gnome-screenshot"

    def available(self) -> bool:
        return shutil.which("gnome-screenshot") is not None

    def capture(self, path: str, delay_ms: int = 0) -> dict:
        return run_capture(["gnome-screenshot", "-f", path], path, delay_ms)
