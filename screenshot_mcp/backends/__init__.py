"""Реестр бэкендов: выбор реализации по окружению и настройкам пользователя."""

from __future__ import annotations

from screenshot_mcp.backends.base import (
    Backend,
    FocusBackend,
    ScreenshotBackend,
    TerminalBackend,
    WindowTarget,
)
from screenshot_mcp.backends.focus import AtspiFocus, KwinFocus, NoFocus, XdoToolFocus
from screenshot_mcp.backends.screenshot import GnomeScreenshot, SpectacleScreenshot, X11Screenshot
from screenshot_mcp.backends.terminal import GnomeTerminal, KonsoleTerminal, XTermTerminal
from screenshot_mcp.config import Environment, Settings

__all__ = [
    "Backend",
    "FocusBackend",
    "ScreenshotBackend",
    "TerminalBackend",
    "WindowTarget",
    "select_focus",
    "select_screenshot",
    "select_terminal",
]

TERMINALS = {
    "konsole": KonsoleTerminal,
    "xterm": XTermTerminal,
    "gnome-terminal": GnomeTerminal,
}
SCREENSHOTS = {
    "spectacle": SpectacleScreenshot,
    "x11": X11Screenshot,
    "gnome": GnomeScreenshot,
}
FOCUSES = {
    "kwin": KwinFocus,
    "xdo_tool": XdoToolFocus,
    "atspi": AtspiFocus,
    "none": NoFocus,
}


class MissingTerminal(TerminalBackend):
    name = "missing"

    def available(self) -> bool:
        return False

    def spawn_argv(self, launcher: str, args: list[str], title: str | None = None) -> list[str]:
        raise RuntimeError("не найден ни один подходящий терминал (konsole, xterm, gnome-terminal)")


def _pick(requested: str, registry: dict, fallback):
    if requested and requested != "auto":
        factory = registry.get(requested)
        if factory is not None:
            return factory()
    return fallback()


def select_terminal(env: Environment, settings: Settings) -> TerminalBackend:
    def autodetect() -> TerminalBackend:
        if env.is_kde and KonsoleTerminal().available():
            return KonsoleTerminal()
        for candidate in (GnomeTerminal(), XTermTerminal(), KonsoleTerminal()):
            if candidate.available():
                return candidate
        return MissingTerminal()

    return _pick(settings.terminal, TERMINALS, autodetect)


def select_screenshot(env: Environment, settings: Settings) -> ScreenshotBackend:
    def autodetect() -> ScreenshotBackend:
        if env.is_wayland and env.is_kde and SpectacleScreenshot().available():
            return SpectacleScreenshot()
        if env.is_wayland and env.is_gnome and GnomeScreenshot().available():
            return GnomeScreenshot()
        if env.is_x11 and X11Screenshot().available():
            return X11Screenshot()
        for candidate in (SpectacleScreenshot(), GnomeScreenshot(), X11Screenshot()):
            if candidate.available():
                return candidate
        return SpectacleScreenshot()

    return _pick(settings.screenshot, SCREENSHOTS, autodetect)


def select_focus(env: Environment, settings: Settings) -> FocusBackend:
    def autodetect() -> FocusBackend:
        if env.is_wayland and env.is_kde and KwinFocus().available():
            return KwinFocus()
        if env.is_x11 and XdoToolFocus().available():
            return XdoToolFocus()
        if env.is_wayland and env.is_gnome and AtspiFocus().available():
            return AtspiFocus()
        return NoFocus()

    return _pick(settings.focus, FOCUSES, autodetect)
