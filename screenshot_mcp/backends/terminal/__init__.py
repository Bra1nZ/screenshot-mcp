"""Бэкенды окна терминала."""

from __future__ import annotations

from screenshot_mcp.backends.terminal.gnome_terminal import GnomeTerminal
from screenshot_mcp.backends.terminal.konsole import KonsoleTerminal
from screenshot_mcp.backends.terminal.xterm import XTermTerminal

__all__ = ["GnomeTerminal", "KonsoleTerminal", "XTermTerminal"]
