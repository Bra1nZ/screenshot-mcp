#!/usr/bin/env python3
"""Съёмка рабочего стола и управление окнами (KWin scripting + Spectacle)."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_SHOTS = os.path.join(HERE, "screenshots")
REPORTER = os.path.join(HERE, "dbus_reporter.py")
REPORT_FILE = os.path.join(
    tempfile.gettempdir(), f"screenshot-mcp-{os.getuid()}", "kwin_report.json"
)
DBUS_NAME = "io.github.bra1nz.screenshot_mcp"
DBUS_INTERFACE = "io.github.bra1nz.screenshot_mcp"
DBUS_PATH = "/io/github/bra1nz/screenshot_mcp"

_REPORTER_PROC = None
_REPORTER_NAME = ""
_SEQ = 0


def _sh(cmd: list[str], timeout: float = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)


def _xdg_dir(name: str, fallback: str) -> str:
    code, out, _ = _sh(["xdg-user-dir", name], timeout=5)
    if code == 0 and out.strip():
        return out.strip()
    return os.path.expanduser(fallback)


def pictures_dir() -> str:
    return _xdg_dir("PICTURES", "~/Pictures")


def kde_screenshots_dir() -> str:
    """Папка KDE для снимков: как настроена в Spectacle, иначе по локали системы."""
    name = _default_screenshots_folder()
    rc = os.path.expanduser("~/.config/spectaclerc")
    try:
        with open(rc, encoding="utf-8") as fh:
            for line in fh:
                if line.strip().startswith("translatedScreenshotsFolder="):
                    name = line.split("=", 1)[1].strip() or name
                    break
    except OSError:
        pass
    return os.path.join(pictures_dir(), name)


def _default_screenshots_folder() -> str:
    lang = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
            or os.environ.get("LANG") or "en_US")
    return "Снимки экрана" if lang.lower().startswith("ru") else "Screenshots"


def default_screenshot_path() -> str:
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H-%M-%S")
    return os.path.join(kde_screenshots_dir(), f"Screenshot from {stamp}.png")


def png_size(path: str) -> tuple[int, int] | None:
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", head[16:24])
    except (OSError, struct.error):
        return None


def session_locked() -> bool:
    """Заблокирован ли сейчас экран (KWin не отдаёт снимок при активном lock screen)."""
    for proc in (["pgrep", "-f", "kscreenlocker_greet"], ["pgrep", "-f", "kscreenlocker"]):
        try:
            res = subprocess.run(proc, capture_output=True, text=True, timeout=5, check=False)
            if res.returncode == 0 and res.stdout.strip():
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def capture_to(path: str, delay_ms: int = 0) -> dict:
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    attempts = [
        ["spectacle", "-b", "-n", "-o", path],
        ["spectacle", "--background", "--nonotify", "--output", path],
    ]
    last_err = ""
    for cmd in attempts:
        if not shutil.which(cmd[0]):
            continue
        code, _, err = _sh(cmd, timeout=40)
        if code == 0 and os.path.exists(path) and os.path.getsize(path) > 0:
            return {"ok": True, "path": path}
        last_err = err.strip()
    if session_locked():
        return {
            "ok": False,
            "path": path,
            "error": "экран заблокирован (активен lock screen) — KWin не отдаёт снимок. "
                     "Разблокируй сессию и повтори.",
        }
    return {"ok": False, "path": path, "error": last_err or "не удалось сохранить снимок"}


def take_screenshot(
    path: str | None = None,
    delay_ms: int = 0,
    copy_to_project: bool = True,
) -> dict:
    target = path or default_screenshot_path()
    result = capture_to(target, delay_ms=delay_ms)
    if not result["ok"]:
        return result
    size = png_size(target)
    copies = []
    if copy_to_project:
        os.makedirs(PROJECT_SHOTS, exist_ok=True)
        dest = os.path.join(PROJECT_SHOTS, os.path.basename(target))
        if os.path.abspath(dest) != os.path.abspath(target):
            try:
                shutil.copy2(target, dest)
                copies.append(dest)
            except OSError:
                pass
    return {
        "ok": True,
        "path": target,
        "copies": copies,
        "width": size[0] if size else None,
        "height": size[1] if size else None,
        "bytes": os.path.getsize(target) if os.path.exists(target) else None,
    }


# ------------------------------ окна (KWin) ------------------------------

def _name_is_owned(name: str) -> bool:
    gdbus = shutil.which("gdbus")
    if not gdbus:
        return True
    code, out, _ = _sh([
        gdbus, "call", "--session", "--dest", "org.freedesktop.DBus",
        "--object-path", "/org/freedesktop/DBus",
        "--method", "org.freedesktop.DBus.NameHasOwner", name,
    ], timeout=5)
    return code == 0 and "true" in out.lower()


def _ensure_reporter() -> bool:
    global _REPORTER_PROC, _REPORTER_NAME
    if _REPORTER_PROC is not None and _REPORTER_PROC.poll() is None:
        return True
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    _REPORTER_NAME = f"{DBUS_NAME}.p{os.getpid()}"
    try:
        _REPORTER_PROC = subprocess.Popen(
            [sys.executable, REPORTER, REPORT_FILE, _REPORTER_NAME],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    deadline = time.time() + 10
    while time.time() < deadline:
        if _REPORTER_PROC.poll() is not None:
            return False
        if _name_is_owned(_REPORTER_NAME):
            return True
        time.sleep(0.2)
    return False


def _qdbus() -> str | None:
    return shutil.which("qdbus6") or shutil.which("qdbus")


def kwin_run(script: str, wait: float = 3.0) -> dict:
    """Выполняет JS-скрипт в KWin и возвращает JSON-отчёт."""
    global _SEQ
    if not _ensure_reporter():
        return {"error": "не удалось запустить DBus-репортер"}
    qdbus = _qdbus()
    if not qdbus:
        return {"error": "qdbus недоступен"}
    _SEQ += 1
    name = f"mcpdesktop_{os.getpid()}_{_SEQ}"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(script.replace("__DBUS_NAME__", _REPORTER_NAME))
        path = fh.name
    try:
        last_error = "скрипт не вернул отчёт"
        for _attempt in range(2):
            with contextlib.suppress(OSError):
                os.unlink(REPORT_FILE)
            code, _, err = _sh([qdbus, "org.kde.KWin", "/Scripting", "loadScript", path, name], timeout=10)
            if code != 0:
                return {"error": f"loadScript: {err.strip()}"}
            _sh([qdbus, "org.kde.KWin", "/Scripting", "start"], timeout=10)
            deadline = time.time() + wait
            while time.time() < deadline:
                try:
                    with open(REPORT_FILE, encoding="utf-8") as fh:
                        data = fh.read().strip()
                    if data:
                        try:
                            return json.loads(data)
                        except ValueError:
                            return {"error": "некорректный отчёт", "raw": data}
                except OSError:
                    pass
                time.sleep(0.1)
            _sh([qdbus, "org.kde.KWin", "/Scripting", "unloadScript", name], timeout=10)
        return {"error": last_error}
    finally:
        _sh([qdbus, "org.kde.KWin", "/Scripting", "unloadScript", name], timeout=10)
        with contextlib.suppress(OSError):
            os.unlink(path)


REPORT_HEAD = """
var r = {windows: []};
var clients = workspace.windowList();
for (var i = 0; i < clients.length; i++) {
    var c = clients[i];
    var g = c.frameGeometry;
    r.windows.push({
        caption: c.caption || '',
        class: c.resourceClass || '',
        pid: c.pid,
        id: c.internalId,
        active: c.active,
        minimized: c.minimized,
        x: g.x, y: g.y, w: g.width, h: g.height
    });
}
var aw = workspace.activeWindow;
r.active = aw ? {
    caption: aw.caption || '',
    class: aw.resourceClass || '',
    pid: aw.pid,
    id: aw.internalId
} : null;
"""


def _report_tail() -> str:
    return f"""
try {{
    callDBus('__DBUS_NAME__', '{DBUS_PATH}', '{DBUS_INTERFACE}', 'Report', JSON.stringify(r));
}} catch (e) {{ r.dbusError = '' + e; }}
"""


def list_windows() -> dict:
    data = kwin_run(REPORT_HEAD + _report_tail())
    if "error" in data:
        return {"error": data["error"], "windows": []}
    return {"windows": data.get("windows", []), "active": data.get("active")}


def active_window() -> dict | None:
    data = kwin_run(REPORT_HEAD + _report_tail())
    if "error" in data:
        return {"error": data["error"]}
    return data.get("active")


def focus_pid(pid: int, app_hint: str = "konsole") -> dict:
    """Поднимает окно приложения с указанным PID на передний план."""
    script = f"""
var r = {{steps: [], found: false}};
var want = '{int(pid)}';
var target = null;
var clients = workspace.windowList();
for (var i = 0; i < clients.length; i++) {{
    var c = clients[i];
    var cls = (c.resourceClass || '') + ' ' + (c.resourceName || '');
    if (cls.toLowerCase().indexOf('{app_hint.lower()}') < 0) {{ continue; }}
    if (String(c.pid) === want) {{ target = c; }}
}}
if (target === null) {{
    r.steps.push('окно с pid=' + want + ' не найдено');
}} else {{
    r.found = true;
    r.caption = target.caption;
    try {{
        if (target.minimized) {{ target.minimized = false; }}
        workspace.activeWindow = target;
        r.steps.push('activated');
    }} catch (e) {{
        r.steps.push('error: ' + e);
    }}
}}
var aw = workspace.activeWindow;
r.active = aw ? (aw.caption || '') : 'none';
r.activePid = aw ? aw.pid : null;
""" + _report_tail()
    data = kwin_run(script)
    if "error" in data:
        return {"activated": False, "error": data["error"]}
    active = data.get("active")
    return {
        "activated": bool(data.get("found")) and data.get("activePid") == int(pid),
        "caption": data.get("caption"),
        "active_window": active,
        "steps": data.get("steps", []),
    }
