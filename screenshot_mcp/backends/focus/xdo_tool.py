"""Поднятие окна на X11: xdotool (активация) и wmctrl (список окон)."""

from __future__ import annotations

import shutil
import subprocess

from screenshot_mcp.backends.base import FocusBackend, WindowTarget


def _run(cmd: list[str], timeout: float = 10) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return proc.returncode, proc.stdout


class XdoToolFocus(FocusBackend):
    name = "xdo_tool"

    def available(self) -> bool:
        return shutil.which("xdotool") is not None

    def _find_window(self, target: WindowTarget) -> str | None:
        if target.pid:
            code, out = _run(["xdotool", "search", "--pid", str(target.pid)])
            ids = [line.strip() for line in out.splitlines() if line.strip()]
            if ids:
                return ids[-1]
        if target.title_hint:
            code, out = _run(["xdotool", "search", "--name", target.title_hint])
            ids = [line.strip() for line in out.splitlines() if line.strip()]
            if ids:
                return ids[-1]
        return None

    def activate(self, target: WindowTarget) -> dict:
        if not self.available():
            return {"activated": False, "error": "xdotool не установлен"}
        window = self._find_window(target)
        if window is None:
            return {"activated": False, "error": "окно не найдено", "steps": []}
        steps = []
        code, _ = _run(["xdotool", "windowraise", window])
        steps.append("raise" if code == 0 else "raise failed")
        code, _ = _run(["xdotool", "windowactivate", "--sync", window])
        steps.append("activate" if code == 0 else "activate failed")
        return {
            "activated": code == 0,
            "caption": None,
            "active_window": None,
            "steps": steps,
        }

    def windows(self) -> dict:
        if not shutil.which("wmctrl"):
            return {"windows": [], "active": None, "error": "wmctrl не установлен"}
        code, out = _run(["wmctrl", "-l", "-G"])
        if code != 0:
            return {"windows": [], "active": None, "error": "wmctrl не смог получить список окон"}
        windows = []
        active = None
        for line in out.splitlines():
            parts = line.split(None, 6)
            if len(parts) < 7:
                continue
            item = {
                "caption": parts[6],
                "class": "",
                "pid": None,
                "id": parts[0],
                "active": False,
                "minimized": False,
                "x": int(parts[2]) if parts[2].lstrip("-").isdigit() else 0,
                "y": int(parts[3]) if parts[3].lstrip("-").isdigit() else 0,
                "w": int(parts[4]) if parts[4].isdigit() else 0,
                "h": int(parts[5]) if parts[5].isdigit() else 0,
            }
            windows.append(item)
        code, out = _run(["xdotool", "getactivewindow"])
        if code == 0 and out.strip():
            current = out.strip()
            for item in windows:
                if item["id"] == current:
                    item["active"] = True
                    active = item
        return {"windows": windows, "active": active}
