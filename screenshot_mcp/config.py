"""Определение окружения и пользовательские настройки."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_ENV_VAR = "SCREENSHOT_MCP_CONFIG"
CONFIG_PATHS = (
    Path.home() / ".config" / "screenshot-mcp" / "config.toml",
    Path.home() / ".config" / "screenshot-mcp.toml",
)


@dataclass
class Environment:
    """Что вокруг: тип сессии, рабочее окружение, дисплей."""

    session_type: str = ""
    desktop: str = ""
    wayland_display: str = ""
    display: str = ""

    @property
    def is_wayland(self) -> bool:
        return self.session_type == "wayland" or bool(self.wayland_display)

    @property
    def is_x11(self) -> bool:
        return self.session_type == "x11" or bool(self.display)

    @property
    def is_kde(self) -> bool:
        return self.desktop in ("kde", "plasma", "kde-plasma")

    @property
    def is_gnome(self) -> bool:
        return self.desktop == "gnome"

    @property
    def is_sway(self) -> bool:
        return self.desktop in ("sway", "wlroots")

    def summary(self) -> str:
        return f"{self.desktop or '?'}/{self.session_type or '?'}"


def _first_token(value: str) -> str:
    for part in value.replace(";", ",").split(","):
        part = part.strip().lower()
        if part:
            return part
    return ""


def detect_environment() -> Environment:
    session_type = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
    wayland_display = os.environ.get("WAYLAND_DISPLAY") or ""
    display = os.environ.get("DISPLAY") or ""

    desktop = _first_token(os.environ.get("XDG_CURRENT_DESKTOP") or "")
    if not desktop and os.environ.get("KDE_FULL_SESSION"):
        desktop = "kde"
    if not desktop and os.environ.get("GNOME_DESKTOP_SESSION_ID"):
        desktop = "gnome"
    if not desktop and os.environ.get("SWAYSOCK"):
        desktop = "sway"

    if not session_type:
        session_type = "wayland" if wayland_display else ("x11" if display else "")

    return Environment(
        session_type=session_type,
        desktop=desktop,
        wayland_display=wayland_display,
        display=display,
    )


@dataclass
class Settings:
    """Пользовательские настройки: явный выбор бэкендов или автоопределение."""

    terminal: str = "auto"
    screenshot: str = "auto"
    focus: str = "auto"
    options: dict = field(default_factory=dict)

    def option(self, section: str, key: str, default=None):
        return self.options.get(section, {}).get(key, default)


def load_settings() -> Settings:
    path = None
    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path:
        path = Path(env_path).expanduser()
    else:
        for candidate in CONFIG_PATHS:
            if candidate.exists():
                path = candidate
                break
    if path is None or not path.exists():
        return Settings()

    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return Settings()

    settings = Settings()
    for name in ("terminal", "screenshot", "focus"):
        section = data.get(name)
        if isinstance(section, dict):
            settings.options[name] = {k: v for k, v in section.items() if k != "backend"}
            if isinstance(section.get("backend"), str):
                setattr(settings, name, section["backend"])
    return settings
