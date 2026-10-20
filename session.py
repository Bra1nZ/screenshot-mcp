#!/usr/bin/env python3
"""Сессия консоли: pty с интерактивным bash, окно Konsole, обмен по UNIX-сокету."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(HERE, "bridge.py")
LAUNCHER = os.path.join(HERE, "console_launcher.sh")
MAX_BUFFER = 1 << 20


def ensure_session_env() -> None:
    uid = os.getuid()
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    os.environ.setdefault("XDG_RUNTIME_DIR", runtime)
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime}/bus"
    if not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"


class ConsoleSession:
    def __init__(
        self,
        cwd: str | None = None,
        cols: int = 100,
        rows: int = 30,
        title: str | None = None,
        shell: str | None = None,
        terminal: str = "konsole",
        runroot: str | None = None,
    ) -> None:
        ensure_session_env()
        self.id = uuid.uuid4().hex[:8]
        self.cwd = os.path.abspath(os.path.expanduser(cwd or os.getcwd()))
        self.cols = cols
        self.rows = rows
        self.title = title
        self.shell = shell or os.environ.get("SHELL", "/bin/bash")
        self.terminal = terminal
        root = runroot or os.path.join(tempfile.gettempdir(), f"screenshot-mcp-{os.getuid()}")
        self.workdir = os.path.join(root, self.id)
        os.makedirs(self.workdir, exist_ok=True)
        self.sock_path = os.path.join(self.workdir, "bridge.sock")

        self._buf = bytearray()
        self._base = 0
        self._lock = threading.Lock()
        self._mark_count = 0
        self._last_code: int | None = None
        self._closed = False
        self._close_reason = ""
        self._listener: socket.socket | None = None
        self._conn: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._konsole: subprocess.Popen | None = None
        self._shell_pid: int | None = None
        self._konsole_pid: int | None = None
        self._cols_actual = cols
        self._rows_actual = rows

    # ---------- свойства ----------
    @property
    def shell_pid(self) -> int | None:
        return self._shell_pid

    @property
    def konsole_pid(self) -> int | None:
        return self._konsole_pid

    @property
    def cols_actual(self) -> int:
        return self._cols_actual

    @property
    def rows_actual(self) -> int:
        return self._rows_actual

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def close_reason(self) -> str:
        return self._close_reason

    @property
    def mark_count(self) -> int:
        with self._lock:
            return self._mark_count

    @property
    def last_code(self) -> int | None:
        with self._lock:
            return self._last_code

    @property
    def cursor(self) -> int:
        with self._lock:
            return self._base + len(self._buf)

    # ---------- запуск ----------
    def start(self, timeout: float = 25.0) -> ConsoleSession:
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.sock_path)
        listener.listen(1)
        listener.settimeout(timeout)
        self._listener = listener

        cmd = [self.terminal, "--separate"]
        if self.title:
            cmd += ["--title", self.title]
        cmd += [
            "-e", "/bin/bash", LAUNCHER,
            "--sock", self.sock_path,
            "--workdir", self.workdir,
            "--cwd", self.cwd,
            "--shell", self.shell,
            "--cols", str(self.cols),
            "--rows", str(self.rows),
        ]
        env = dict(os.environ)
        env["MCP_PYTHON"] = sys.executable
        self._konsole = subprocess.Popen(
            cmd, cwd=self.cwd, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._konsole_pid = self._konsole.pid

        conn, _ = listener.accept()
        conn.settimeout(None)
        self._conn = conn
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self.wait_ready(timeout=timeout)
        return self

    def _read_loop(self) -> None:
        buf = bytearray()
        try:
            while True:
                chunk = self._conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, _, rest = bytes(buf).partition(b"\n")
                    buf.clear()
                    buf += rest
                    try:
                        self._dispatch(json.loads(line.decode("utf-8")))
                    except ValueError:
                        continue
        except OSError:
            pass
        finally:
            self._closed = True

    def _dispatch(self, msg: dict) -> None:
        kind = msg.get("t")
        if kind == "out":
            data = base64.b64decode(msg.get("d", ""))
            with self._lock:
                self._buf += data
                if len(self._buf) > MAX_BUFFER:
                    overflow = len(self._buf) - MAX_BUFFER
                    del self._buf[:overflow]
                    self._base += overflow
        elif kind == "mark":
            with self._lock:
                self._mark_count += 1
                self._last_code = msg.get("code")
        elif kind == "hello":
            self._shell_pid = msg.get("pid")
            self._cols_actual = msg.get("cols") or self.cols
            self._rows_actual = msg.get("rows") or self.rows
        elif kind == "closed":
            self._close_reason = msg.get("reason", "")
            code = msg.get("code")
            if code is not None:
                with self._lock:
                    self._last_code = code
            self._closed = True

    # ---------- ввод ----------
    def _send(self, obj: dict) -> None:
        if self._conn is None:
            raise RuntimeError("консоль не подключена")
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        self._conn.sendall(data)

    def send_bytes(self, data: bytes) -> None:
        self._send({"t": "in", "d": base64.b64encode(data).decode("ascii")})

    def type_text(self, text: str, delay_ms: int = 15, max_total: float = 3.0) -> None:
        """Печатает текст в консоль с человеческими паузами между символами."""
        if delay_ms <= 0:
            self.send_bytes(text.encode("utf-8"))
            return
        started = time.time()
        for index, ch in enumerate(text):
            self.send_bytes(ch.encode("utf-8"))
            time.sleep(delay_ms / 1000.0 * random.uniform(0.6, 1.5))  # noqa: S311 - паузы между символами
            if time.time() - started > max_total:
                rest = text[index + 1:]
                if rest:
                    self.send_bytes(rest.encode("utf-8"))
                break

    def press_enter(self) -> None:
        self.send_bytes(b"\r")

    # ---------- чтение ----------
    def read_since(self, cursor: int) -> bytes:
        with self._lock:
            start = max(0, cursor - self._base)
            return bytes(self._buf[start:])

    def wait_ready(self, timeout: float = 15.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline and self.mark_count == 0 and not self.closed:
            time.sleep(0.05)
        return self.mark_count > 0

    def wait_mark(self, since_count: int, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.mark_count > since_count:
                return True
            if self.closed:
                return self.mark_count > since_count
            time.sleep(0.02)
        return self.mark_count > since_count

    # ---------- выполнение ----------
    def exec_command(self, command: str, timeout: float = 30.0, typing_delay_ms: int = 15) -> dict:
        cursor = self.cursor
        marks = self.mark_count
        self.type_text(command, delay_ms=typing_delay_ms)
        self.press_enter()
        finished = self.wait_mark(marks, timeout)
        if not finished and self.closed:
            finished = True
        time.sleep(0.12 if finished else 0.05)
        return {
            "output": self.read_since(cursor).decode("utf-8", "replace"),
            "exit_code": self.last_code if finished else None,
            "timed_out": not finished,
            "closed": self.closed,
        }

    def state(self) -> dict:
        return {
            "console_id": self.id,
            "pid": self.shell_pid,
            "konsole_pid": self.konsole_pid,
            "cwd": self.cwd,
            "cols": self.cols_actual,
            "rows": self.rows_actual,
            "alive": not self.closed,
            "closed_reason": self.close_reason,
            "last_exit_code": self.last_code,
            "buffer_bytes": self.cursor,
        }

    # ---------- закрытие ----------
    def close(self, grace: float = 1.0) -> None:
        with contextlib.suppress(OSError):
            if self._conn is not None:
                self._send({"t": "close"})
        time.sleep(0.15)
        if self._konsole is not None and self._konsole.poll() is None:
            try:
                self._konsole.terminate()
                time.sleep(0.3)
                if self._konsole.poll() is None:
                    self._konsole.kill()
            except OSError:
                pass
        for sock in (self._conn, self._listener):
            if sock is not None:
                with contextlib.suppress(OSError):
                    sock.close()
        with contextlib.suppress(OSError):
            os.unlink(self.sock_path)
        shutil.rmtree(self.workdir, ignore_errors=True)
        self._closed = True
