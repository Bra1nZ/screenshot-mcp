"""Базовые классы бэкендов и общие структуры данных."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WindowTarget:
    """Что именно нужно активировать."""

    pid: int | None = None
    title_hint: str = ""
    app_hint: str = ""


class Backend:
    """Общий интерфейс бэкенда."""

    name = "base"

    def available(self) -> bool:
        """Есть ли всё необходимое в системе (бинарники, окружение)."""
        return False

    def describe(self) -> str:
        return self.name


class TerminalBackend(Backend):
    """Умеет открыть окно терминала с заданной командой."""

    name = "terminal"

    def spawn_argv(self, launcher: str, args: list[str], title: str | None = None) -> list[str]:
        """argv для запуска окна терминала; launcher — путь к скрипту-лаунчеру."""
        raise NotImplementedError

    def owns_window(self) -> bool:
        """True, если процесс терминала сам владеет своим окном.

        Некоторые терминалы (gnome-terminal) форкаются и сразу выходят:
        тогда идентифицировать окно придётся по заголовку, а не по PID.
        """
        return True


class ScreenshotBackend(Backend):
    """Умеет снимать рабочий стол."""

    name = "screenshot"

    def capture(self, path: str, delay_ms: int = 0) -> dict:
        """Сделать снимок и сохранить в path. Возвращает {"ok": bool, ...}."""
        raise NotImplementedError


class FocusBackend(Backend):
    """Умеет поднимать окно на передний план."""

    name = "focus"

    def activate(self, target: WindowTarget) -> dict:
        """Активировать окно. Возвращает {"activated": bool, ...}."""
        raise NotImplementedError

    def windows(self) -> dict:
        """Список окон и активное. Возвращает {"windows": [...], "active": {...}}."""
        return {"windows": [], "active": None, "error": f"{self.name}: список окон недоступен"}
