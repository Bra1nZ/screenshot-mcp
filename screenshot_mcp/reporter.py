"""Приём отчётов от KWin-скриптов через DBus.

KWin не умеет отдавать данные наружу сам, поэтому скрипт вызывает метод Report
этого сервиса, а тот складывает payload в файл, который читает вызывающий.
"""

from __future__ import annotations

import contextlib
import sys

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBUS_REQUEST_OK = 1
FILE_ARG_INDEX = 1
SERVICE_ARG_INDEX = 2
INTERFACE_ARG_INDEX = 3
PATH_ARG_INDEX = 4


def main() -> int:
    target = sys.argv[FILE_ARG_INDEX]
    service = sys.argv[SERVICE_ARG_INDEX] if len(sys.argv) > SERVICE_ARG_INDEX else ""
    interface = sys.argv[INTERFACE_ARG_INDEX] if len(sys.argv) > INTERFACE_ARG_INDEX else ""
    path = sys.argv[PATH_ARG_INDEX] if len(sys.argv) > PATH_ARG_INDEX else "/"

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
        @dbus.service.method(interface, in_signature="s", out_signature="")
        def Report(self, payload: str) -> None:
            with contextlib.suppress(OSError), open(target, "w", encoding="utf-8") as fh:
                fh.write(payload)

    Reporter(bus, path)
    loop = GLib.MainLoop()
    with contextlib.suppress(KeyboardInterrupt):
        loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
