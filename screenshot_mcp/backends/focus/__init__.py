"""Бэкенды поднятия окна на передний план."""

from __future__ import annotations

from screenshot_mcp.backends.focus.atspi import AtspiFocus
from screenshot_mcp.backends.focus.kwin import KwinFocus
from screenshot_mcp.backends.focus.none import NoFocus
from screenshot_mcp.backends.focus.xdo_tool import XdoToolFocus

__all__ = ["AtspiFocus", "KwinFocus", "NoFocus", "XdoToolFocus"]
