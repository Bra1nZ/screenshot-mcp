#!/usr/bin/env python3
"""Юнит-тесты конфигурации и бэкендов. GUI не требуется — можно гонять в CI."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from screenshot_mcp.backends import (  # noqa: E402
    select_focus,
    select_screenshot,
    select_terminal,
)
from screenshot_mcp.backends.terminal import GnomeTerminal, KonsoleTerminal, XTermTerminal  # noqa: E402
from screenshot_mcp.config import Environment, Settings, detect_environment, load_settings  # noqa: E402


def test_detect_environment():
    env = detect_environment()
    assert isinstance(env, Environment)
    assert env.session_type in ("", "wayland", "x11")
    print("ок: окружение определено:", env.summary())


def test_settings_defaults():
    settings = load_settings()
    assert settings.terminal == "auto"
    assert settings.screenshot == "auto"
    assert settings.focus == "auto"
    print("ок: настройки по умолчанию — auto")


def test_settings_from_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "config.toml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('[terminal]\nbackend = "xterm"\n\n[screenshot]\nbackend = "x11"\n')
        os.environ["SCREENSHOT_MCP_CONFIG"] = path
        try:
            settings = load_settings()
            assert settings.terminal == "xterm"
            assert settings.screenshot == "x11"
        finally:
            del os.environ["SCREENSHOT_MCP_CONFIG"]
    print("ок: настройки читаются из TOML")


def test_backend_selection_follows_settings():
    env = Environment(session_type="x11", desktop="kde")
    settings = Settings(terminal="xterm", screenshot="x11", focus="none")
    assert isinstance(select_terminal(env, settings), XTermTerminal)
    assert select_screenshot(env, settings).name == "x11"
    assert select_focus(env, settings).name == "none"
    print("ок: явный выбор бэкендов работает")


def test_backend_selection_autodetect():
    env = Environment(session_type="wayland", desktop="kde")
    terminal = select_terminal(env, Settings())
    assert terminal.name in ("konsole", "gnome-terminal", "xterm", "missing")
    focus = select_focus(env, Settings())
    assert focus.name in ("kwin", "xdo_tool", "atspi", "none")
    print("ок: автоопределение:", terminal.name, "/", focus.name)


def test_terminal_argv():
    launcher = "/tmp/launcher.sh"
    args = ["--sock", "/tmp/sock"]
    for backend in (KonsoleTerminal(), XTermTerminal(), GnomeTerminal()):
        argv = backend.spawn_argv(launcher, args, title="Заголовок")
        assert argv[0].endswith(backend.name if backend.name != "gnome-terminal" else "gnome-terminal")
        assert launcher in argv
        assert "Заголовок" in argv
        assert argv[-2:] == args[-2:]
    print("ок: терминалы собирают корректный argv")


def test_title_optional():
    argv = KonsoleTerminal().spawn_argv("/tmp/l.sh", ["--sock", "/tmp/s"])
    assert "Заголовок" not in argv
    assert "/tmp/l.sh" in argv
    print("ок: заголовок необязателен")


if __name__ == "__main__":
    failures = 0
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
            except AssertionError as exc:
                failures += 1
                print(f"ПРОВАЛ {name}: {exc}")
    if failures:
        print(f"\n{failures} тестов упало")
        sys.exit(1)
    print("\nвсе тесты прошли")
