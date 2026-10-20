#!/usr/bin/env python3
"""Слушатель DBus: KWin-скрипты сообщают сюда состояние окон.

Имя сервиса и путь к файлу отчёта задаются аргументами, чтобы несколько
экземпляров не конфликтовали за одно DBus-имя.
"""

from __future__ import annotations

import contextlib
import sys

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

SERVICE = "io.github.bra1nz.screenshot_mcp"
INTERFACE = "io.github.bra1nz.screenshot_mcp"
DBUS_REQUEST_OK = 1
SERVICE_ARG_INDEX = 2
PATH = "/io/github/bra1nz/screenshot_mcp"


def main() -> int:
    target = sys.argv[1]
    service = sys.argv[SERVICE_ARG_INDEX] if len(sys.argv) > SERVICE_ARG_INDEX else SERVICE
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    try:
        result = bus.request_name(service)
    except dbus.DBusException as exc:
        print(f"не удалось запросить имя {service}: {exc}", file=sys.stderr, flush=True)
        return 1
    if result != DBUS_REQUEST_OK:
        print(f"имя {service} уже занято (код {result})", file=sys.stderr, flush=True)
        return 1

    class Reporter(dbus.service.Object):
        @dbus.service.method(INTERFACE, in_signature="s", out_signature="")
        def Report(self, payload: str) -> None:
            try:
                with open(target, "w", encoding="utf-8") as fh:
                    fh.write(payload)
            except OSError:
                pass

    Reporter(bus, PATH)
    loop = GLib.MainLoop()
    with contextlib.suppress(KeyboardInterrupt):
        loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
