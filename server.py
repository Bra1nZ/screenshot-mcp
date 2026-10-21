#!/usr/bin/env python3
"""screenshot-mcp — MCP-сервер: окна консоли, ввод/вывод, снимки рабочего стола.

Точка входа. Вся логика — в пакете screenshot_mcp: ядро (core) и бэкенды.
"""

from __future__ import annotations

import atexit
import contextlib
import io
import os
import re
import sys
import time
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screenshot_mcp.backends.base import WindowTarget  # noqa: E402
from screenshot_mcp.backends.screenshot import (  # noqa: E402
    default_screenshot_path,
    png_size,
)
from screenshot_mcp.core.session import ConsoleSession  # noqa: E402
from screenshot_mcp.runtime import get_runtime  # noqa: E402

mcp = FastMCP("screenshot-mcp", log_level="WARNING")
SESSIONS: dict[str, ConsoleSession] = {}
PROJECT_SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")

KEYS = {
    "enter": b"\r", "return": b"\r", "tab": b"\t", "esc": b"\x1b", "escape": b"\x1b",
    "backspace": b"\x7f", "space": b" ", "delete": b"\x1b[3~",
    "up": b"\x1b[A", "down": b"\x1b[B", "right": b"\x1b[C", "left": b"\x1b[D",
    "home": b"\x1b[H", "end": b"\x1b[F", "pageup": b"\x1b[5~", "pagedown": b"\x1b[6~",
    "insert": b"\x1b[2~",
}
for _i in range(1, 13):
    KEYS[f"f{_i}"] = b"\x1bOP" if _i <= 4 else b"\x1b[" + str(_i + 10).encode() + b"~"


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


def truncate(text: str, limit: int = 20000) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n... [обрезано, всего {len(text)} символов]", True


def get_session(console_id: str) -> ConsoleSession:
    session = SESSIONS.get(console_id)
    if session is None:
        raise ValueError(
            f"консоль {console_id} не найдена. Открой новую через console_open "
            f"(активные: {', '.join(SESSIONS) or 'нет'})."
        )
    return session


def encode_key(key: str) -> bytes:
    name = key.strip().lower()
    if name in KEYS:
        return KEYS[name]
    if name.startswith("ctrl+") and len(name) == 6 and name[5].isalpha():
        return bytes([ord(name[5]) - 96])
    if name.startswith("alt+"):
        return b"\x1b" + encode_key(name[4:])
    if name.startswith("shift+"):
        return encode_key(name[6:])
    if len(name) == 1:
        return name.encode("utf-8")
    raise ValueError(f"неизвестная клавиша: {key}")


def window_target(session: ConsoleSession) -> WindowTarget:
    return WindowTarget(
        pid=session.terminal_pid,
        title_hint=os.path.basename(session.cwd),
        app_hint="konsole",
    )


def preview_image(path: str, max_width: int = 1280) -> Image | None:
    try:
        from PIL import Image as PILImage

        with PILImage.open(path) as source:
            image = source.convert("RGB")
            if image.width > max_width:
                ratio = max_width / image.width
                image = image.resize((max_width, int(image.height * ratio)), PILImage.LANCZOS)
            buf = io.BytesIO()
            image.save(buf, format="PNG", optimize=True)
            return Image(data=buf.getvalue(), format="png")
    except Exception:
        return None


@atexit.register
def _cleanup() -> None:
    for session in list(SESSIONS.values()):
        with contextlib.suppress(Exception):
            session.close(grace=0.2)


@mcp.tool()
def console_open(
    cwd: str | None = None,
    cols: int = 100,
    rows: int = 30,
    title: str | None = None,
    terminal: str | None = None,
) -> dict:
    """Открыть НОВОЕ отдельное окно консоли и вернуть его console_id.

    В окне запускается интерактивный bash с твоим ~/.bashrc — тот же промпт,
    цвета и алиасы, что и в обычной консоли. Команды, введённые агентом, выглядят
    на экране абсолютно обычно, как будто их набирал человек.

    cwd — рабочий каталог консоли (по умолчанию текущий каталог сервера).
    title — заголовок окна (необязательно).
    terminal — терминал: konsole, xterm или gnome-terminal (по умолчанию — по окружению).
    """
    runtime = get_runtime()
    backend = runtime.terminal
    if terminal:
        from screenshot_mcp.backends import TERMINALS

        factory = TERMINALS.get(terminal)
        if factory is None:
            raise ValueError(f"неизвестный терминал: {terminal}")
        backend = factory()
    session = ConsoleSession(cwd=cwd, cols=cols, rows=rows, title=title, terminal=backend)
    try:
        session.start()
    except Exception as exc:
        session.close(grace=0.1)
        raise RuntimeError(f"не удалось открыть окно консоли: {exc}") from exc
    SESSIONS[session.id] = session
    return {
        "console_id": session.id,
        "pid": session.shell_pid,
        "terminal_pid": session.terminal_pid,
        "terminal_backend": session.terminal_backend,
        "cwd": session.cwd,
        "cols": session.cols_actual,
        "rows": session.rows_actual,
    }


@mcp.tool()
def console_exec(
    console_id: str,
    command: str,
    timeout: float = 30.0,
    typing_delay_ms: int = 15,
) -> dict:
    """Выполнить команду в консоли и дождаться результата.

    Текст набирается в консоль посимвольно (как живой ввод), затем выполняется.
    Возвращает: output — что появилось в консоли (включая саму команду),
    exit_code — код возврата последней команды, timed_out — True, если команда
    не завершилась за timeout (например, ждёт ввода).

    Для интерактивных программ сначала используй console_send/console_key,
    затем снова console_exec либо console_read.
    """
    session = get_session(console_id)
    result = session.exec_command(command, timeout=timeout, typing_delay_ms=typing_delay_ms)
    out, cut = truncate(result["output"])
    return {
        "output": strip_ansi(out),
        "output_truncated": cut,
        "exit_code": result["exit_code"],
        "timed_out": result["timed_out"],
        "console_closed": result["closed"],
    }


@mcp.tool()
def console_send(console_id: str, text: str, enter: bool = False) -> dict:
    """Напечатать текст в консоль БЕЗ выполнения (enter=False) или с переводом строки.

    Нужно для программ, которые ждут ввода (yes/no, sudo, REPL).
    """
    session = get_session(console_id)
    session.type_text(text, delay_ms=15)
    if enter:
        session.press_enter()
    return {"ok": True, "console_id": console_id}


@mcp.tool()
def console_key(console_id: str, key: str) -> dict:
    """Отправить специальную клавишу в консоль.

    Поддерживаются: enter, tab, esc, backspace, space, up, down, left, right,
    home, end, pageup, pagedown, delete, insert, f1..f12, ctrl+c, ctrl+d,
    ctrl+l, ctrl+z, alt+<key>, а также одиночные символы.
    """
    session = get_session(console_id)
    session.send_bytes(encode_key(key))
    time.sleep(0.05)
    return {"ok": True, "key": key}


@mcp.tool()
def console_read(console_id: str, cursor: int | None = None, max_bytes: int = 20000) -> dict:
    """Прочитать новый вывод консоли начиная с cursor (None — с начала буфера).

    Возвращает текст и новый cursor, который можно передать в следующий вызов.
    """
    session = get_session(console_id)
    start = 0 if cursor is None else int(cursor)
    data = session.read_since(start)
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    text, cut = truncate(data.decode("utf-8", "replace"))
    return {
        "output": strip_ansi(text),
        "output_truncated": cut,
        "cursor": session.cursor,
        "alive": not session.closed,
    }


@mcp.tool()
def console_state(console_id: str) -> dict:
    """Состояние консоли: pid, рабочий каталог, размер, жив ли процесс, последний код возврата."""
    session = get_session(console_id)
    return session.state()


@mcp.tool()
def console_list() -> dict:
    """Список открытых консолей с их состоянием."""
    return {"consoles": [s.state() for s in SESSIONS.values()]}


@mcp.tool()
def console_close(console_id: str) -> dict:
    """Закрыть окно консоли."""
    session = get_session(console_id)
    session.close()
    SESSIONS.pop(console_id, None)
    return {"ok": True, "console_id": console_id}


@mcp.tool()
def desktop_active_window() -> dict:
    """Какое окно сейчас на переднем плане.

    Нужно, чтобы убедиться, что на снимке экрана будет видна именно консоль.
    """
    runtime = get_runtime()
    return {"active_window": runtime.focus.windows().get("active")}


@mcp.tool()
def desktop_list_windows() -> dict:
    """Список окон рабочего стола: заголовок, класс, pid, активное ли, координаты."""
    runtime = get_runtime()
    return runtime.focus.windows()


@mcp.tool()
def desktop_focus(console_id: str | None = None, app: str = "konsole") -> dict:
    """Поднять окно на передний план: консоль по console_id либо любое окно приложения app.

    Возвращает, удалось ли активировать окно и какое окно активно теперь.
    """
    runtime = get_runtime()
    if console_id:
        session = get_session(console_id)
        target = window_target(session)
        target.app_hint = app
        return runtime.focus.activate(target)
    return {"error": "нужен console_id"}


@mcp.tool()
def desktop_screenshot(
    path: str | None = None,
    console_id: str | None = None,
    delay_ms: int = 0,
    copy_to_project: bool = True,
    preview: bool = True,
) -> Any:
    """Сделать снимок ВСЕГО рабочего стола штатным средством системы.

    path — куда сохранить PNG (по умолчанию — стандартная папка для снимков
    с именем вида 'Screenshot from 2026-10-20 23-15-42.png'). Копия также
    складывается в screenshots/ рядом с сервером.
    console_id — если задан, окно этой консоли сначала поднимается на передний
    план, чтобы в кадре была видна консоль.
    delay_ms — пауза перед снимком.
    Возвращает метаданные снимка и уменьшенную копию картинки, чтобы увидеть,
    что именно попало в кадр.
    """
    runtime = get_runtime()
    focus = None
    if console_id:
        session = get_session(console_id)
        focus = runtime.focus.activate(window_target(session))
        time.sleep(0.4)

    target = path or default_screenshot_path()
    result = runtime.screenshot.capture(target, delay_ms=delay_ms)
    if not result.get("ok"):
        return result, None

    size = png_size(target)
    copies = []
    if copy_to_project:
        os.makedirs(PROJECT_SHOTS, exist_ok=True)
        dest = os.path.join(PROJECT_SHOTS, os.path.basename(target))
        if os.path.abspath(dest) != os.path.abspath(target):
            try:
                import shutil

                shutil.copy2(target, dest)
                copies.append(dest)
            except OSError:
                pass
    result.update({
        "ok": True,
        "path": target,
        "copies": copies,
        "width": size[0] if size else None,
        "height": size[1] if size else None,
        "bytes": os.path.getsize(target) if os.path.exists(target) else None,
        "focus": focus,
        "active_window": runtime.focus.windows().get("active"),
        "screenshot_backend": runtime.screenshot.name,
    })
    img = preview_image(target) if preview else None
    return result, img


if __name__ == "__main__":
    mcp.run()
