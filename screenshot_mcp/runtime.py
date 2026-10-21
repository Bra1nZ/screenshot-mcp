"""Единая точка, где собираются окружение, настройки и бэкенды."""

from __future__ import annotations

from dataclasses import dataclass

from screenshot_mcp.backends import select_focus, select_screenshot, select_terminal
from screenshot_mcp.config import Environment, Settings, detect_environment, load_settings


@dataclass
class Runtime:
    env: Environment
    settings: Settings
    terminal: object
    screenshot: object
    focus: object

    def describe(self) -> dict:
        return {
            "environment": self.env.summary(),
            "session_type": self.env.session_type,
            "desktop": self.env.desktop,
            "terminal_backend": self.terminal.name,
            "screenshot_backend": self.screenshot.name,
            "focus_backend": self.focus.name,
        }


_RUNTIME: Runtime | None = None


def get_runtime() -> Runtime:
    global _RUNTIME
    if _RUNTIME is None:
        env = detect_environment()
        settings = load_settings()
        _RUNTIME = Runtime(
            env=env,
            settings=settings,
            terminal=select_terminal(env, settings),
            screenshot=select_screenshot(env, settings),
            focus=select_focus(env, settings),
        )
    return _RUNTIME
