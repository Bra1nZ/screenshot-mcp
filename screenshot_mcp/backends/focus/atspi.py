"""Поднятие окна через AT-SPI — для окружений без скриптинга композитора (GNOME).

Работает через шину доступности: приложение, отдающее accessibility-интерфейс,
может активировать своё окно. Qt-приложения под Plasma AT-SPI обычно не
экспортируют, поэтому на KDE используется KWin-бэкенд.
"""

from __future__ import annotations

import contextlib

from screenshot_mcp.backends.base import FocusBackend, WindowTarget

_ATSPI_READY = False


def _atspi():
    global _ATSPI_READY
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except Exception:
        return None
    if not _ATSPI_READY:
        with contextlib.suppress(Exception):
            Atspi.init()
        _ATSPI_READY = True
    return Atspi


class AtspiFocus(FocusBackend):
    name = "atspi"

    def available(self) -> bool:
        return _atspi() is not None

    def _accessible(self) -> list[tuple[dict, object]]:
        Atspi = _atspi()
        if Atspi is None:
            return []
        result = []
        try:
            desktop = Atspi.get_desktop(0)
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i)
                if app is None:
                    continue
                app_name = app.get_name() or ""
                for j in range(app.get_child_count()):
                    win = app.get_child_at_index(j)
                    if win is None:
                        continue
                    states = win.get_state_set()
                    info = {
                        "app": app_name,
                        "caption": win.get_name() or "",
                        "class": app_name,
                        "active": bool(states.contains(Atspi.StateType.ACTIVE)),
                        "focused": bool(states.contains(Atspi.StateType.FOCUSED)),
                        "role": win.get_role_name(),
                    }
                    result.append((info, win))
        except Exception:
            return []
        return result

    def windows(self) -> dict:
        entries = self._accessible()
        windows = [info for info, _ in entries]
        active = next((info for info in windows if info.get("active")), None)
        return {"windows": windows, "active": active}

    def _activate_object(self, obj) -> bool:
        try:
            action = obj.get_action_iface()
            if action is not None and action.get_n_actions() > 0:
                for index in range(action.get_n_actions()):
                    item = action.get_action_at_index(index)
                    if item.get_name().lower() in ("activate", "raise", "активировать"):
                        item.do_action()
                        return True
                action.do_action(0)
                return True
        except Exception:  # noqa: S110 - переходим к следующему способу активации
            pass
        try:
            from gi.repository import Atspi as _A

            _A.generate_window_event(obj, _A.EventType.WINDOW_ACTIVATE)
            return True
        except Exception:
            return False

    def activate(self, target: WindowTarget) -> dict:
        if _atspi() is None:
            return {"activated": False, "error": "AT-SPI недоступен (нужен PyGObject)"}
        candidates = []
        for info, obj in self._accessible():
            if target.app_hint and target.app_hint.lower() not in (info.get("app") or "").lower():
                continue
            if target.title_hint and target.title_hint.lower() not in info["caption"].lower():
                continue
            candidates.append((info, obj))
        if not candidates:
            return {"activated": False, "error": "подходящее окно не найдено"}
        for info, _ in candidates:
            if info.get("active"):
                return {
                    "activated": True,
                    "caption": info["caption"],
                    "active_window": info["caption"],
                    "steps": ["уже активно"],
                }
        for info, obj in candidates:
            if self._activate_object(obj):
                return {
                    "activated": True,
                    "caption": info["caption"],
                    "active_window": info["caption"],
                    "steps": ["activate"],
                }
        return {"activated": False, "error": "не удалось активировать окно через AT-SPI"}
