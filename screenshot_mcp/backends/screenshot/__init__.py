"""Бэкенды снимка экрана."""

from __future__ import annotations

from screenshot_mcp.backends.screenshot.common import (
    default_screenshot_dir,
    default_screenshot_path,
    png_size,
    session_locked,
)
from screenshot_mcp.backends.screenshot.gnome import GnomeScreenshot
from screenshot_mcp.backends.screenshot.spectacle import SpectacleScreenshot
from screenshot_mcp.backends.screenshot.x11 import X11Screenshot

__all__ = [
    "GnomeScreenshot",
    "SpectacleScreenshot",
    "X11Screenshot",
    "default_screenshot_dir",
    "default_screenshot_path",
    "png_size",
    "session_locked",
]
