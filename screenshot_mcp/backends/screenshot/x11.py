"""Снимок экрана на X11: ImageMagick, scrot или maim."""

from __future__ import annotations

import shutil

from screenshot_mcp.backends.base import ScreenshotBackend
from screenshot_mcp.backends.screenshot.common import run_capture


class X11Screenshot(ScreenshotBackend):
    name = "x11"

    def _command(self) -> list[str] | None:
        if shutil.which("scrot"):
            return ["scrot", "-o", "{}"]
        if shutil.which("maim"):
            return ["maim", "{}"]
        if shutil.which("import"):
            return ["import", "-window", "root", "{}"]
        if shutil.which("xwd"):
            return ["xwd", "-root", "-out", "{}"]
        return None

    def available(self) -> bool:
        return self._command() is not None

    def capture(self, path: str, delay_ms: int = 0) -> dict:
        template = self._command()
        if template is None:
            return {"ok": False, "path": path, "error": "нет ни scrot, ни maim, ни import, ни xwd"}
        cmd = [part.format(path) if "{}" in part else part for part in template]
        return run_capture(cmd, path, delay_ms)
