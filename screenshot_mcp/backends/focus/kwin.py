"""Поднятие окна на передний план в KDE Plasma — через скриптинг KWin.

KWin не отдаёт наружу данные сам, поэтому скрипт зовёт DBus-сервис репортера,
а тот пишет JSON в файл; вызывающий его читает.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from screenshot_mcp.backends.base import FocusBackend, WindowTarget

DBUS_NAME = "io.github.bra1nz.screenshot_mcp"
DBUS_INTERFACE = "io.github.bra1nz.screenshot_mcp"
DBUS_PATH = "/io/github/bra1nz/screenshot_mcp"
REPORT_FILE = os.path.join(
    tempfile.gettempdir(), f"screenshot-mcp-{os.getuid()}", "kwin_report.json"
)
REPORTER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "reporter.py",
)

_REPORTER_PROC: subprocess.Popen | None = None
_REPORTER_NAME = ""
_SEQ = 0


def _sh(cmd: list[str], timeout: float = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)


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
            [sys.executable, REPORTER, REPORT_FILE, _REPORTER_NAME, DBUS_INTERFACE, DBUS_PATH],
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
    """Выполнить JS-скрипт в KWin и вернуть JSON-отчёт."""
    global _SEQ
    if not _ensure_reporter():
        return {"error": "не удалось запустить DBus-репортер"}
    qdbus = _qdbus()
    if not qdbus:
        return {"error": "qdbus недоступен"}
    _SEQ += 1
    name = f"screenshotmcp_{os.getpid()}_{_SEQ}"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(script.replace("__DBUS_NAME__", _REPORTER_NAME))
        path = fh.name
    try:
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
        return {"error": "скрипт не вернул отчёт"}
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


class KwinFocus(FocusBackend):
    name = "kwin"

    def available(self) -> bool:
        return _qdbus() is not None

    def windows(self) -> dict:
        data = kwin_run(REPORT_HEAD + _report_tail())
        if "error" in data:
            return {"error": data["error"], "windows": [], "active": None}
        return {"windows": data.get("windows", []), "active": data.get("active")}

    def activate(self, target: WindowTarget) -> dict:
        script = f"""
var r = {{steps: [], found: false}};
var want = '{int(target.pid or 0)}';
var cls_hint = '{target.app_hint.lower()}';
var title_hint = '{target.title_hint}';
var target_window = null;
var clients = workspace.windowList();
for (var i = 0; i < clients.length; i++) {{
    var c = clients[i];
    var rc = (c.resourceClass || '') + ' ' + (c.resourceName || '');
    if (cls_hint && rc.toLowerCase().indexOf(cls_hint) < 0) {{ continue; }}
    if (want && String(c.pid) === want) {{ target_window = c; }}
}}
if (target_window === null) {{
    r.steps.push('окно не найдено');
}} else {{
    r.found = true;
    r.caption = target_window.caption;
    try {{
        if (target_window.minimized) {{ target_window.minimized = false; }}
        workspace.activeWindow = target_window;
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
        return {
            "activated": bool(data.get("found")) and data.get("activePid") == target.pid,
            "caption": data.get("caption"),
            "active_window": data.get("active"),
            "steps": data.get("steps", []),
        }
