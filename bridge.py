#!/usr/bin/env python3
"""Bridge: запускается внутри окна Konsole.

Окно Konsole -> pty терминала (T). В терминале работает настоящий интерактивный
bash пользователя: он запускается exec'ом, поэтому остаётся foreground-процессом
окна — заголовок, работа с фокусом и job control неотличимы от обычного терминала.

Рядом с bash работает дочерний процесс-«насос»: держит вторую pty (S) и переливает

    клавиатура терминала -> S -> bash
    bash -> S -> терминал (экран) + сокет сервера (вывод для агента)

Сокет: строки JSON, сервер <-> насос.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import json
import os
import select
import shlex
import signal
import socket
import struct
import sys
import termios
import time

READ_SIZE = 65536
DBUS_REQUEST_OK = 1
STD_FD_LIMIT = 2
B64 = base64.b64encode

RCFILE = """# сгенерировано desktop-console MCP
if [ -r "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi

__mcp_prompt_marker() {{
    local __mcp_rc=$?
    printf '\\036MCP_MARK\\t%s\\n' "$__mcp_rc" 2>/dev/null >> {marker}
    return $__mcp_rc
}}

__mcp_exit_marker() {{
    local __mcp_rc=$?
    printf '\\036MCP_EXIT\\t%s\\n' "$__mcp_rc" 2>/dev/null >> {marker}
    return $__mcp_rc
}}

trap '__mcp_exit_marker' EXIT

if declare -p PROMPT_COMMAND 2>/dev/null | grep -q 'declare -a'; then
    PROMPT_COMMAND=(__mcp_prompt_marker "${{PROMPT_COMMAND[@]}}")
elif [ -n "${{PROMPT_COMMAND:-}}" ]; then
    PROMPT_COMMAND=(__mcp_prompt_marker "${{PROMPT_COMMAND}}")
else
    PROMPT_COMMAND=(__mcp_prompt_marker)
fi
"""


def log(msg: str) -> None:
    print(f"[bridge] {msg}", file=sys.stderr, flush=True)


def set_winsize(fd: int, cols: int, rows: int) -> None:
    if cols <= 0 or rows <= 0:
        return
    with contextlib.suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def get_winsize(fd: int) -> tuple[int, int]:
    try:
        data = fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8)
    except OSError:
        return 0, 0
    rows, cols, _, _ = struct.unpack("HHHH", data)
    return cols, rows


class Pump:
    """Процесс в окне терминала: держит master pty и перекачивает данные."""

    def __init__(self, master, sock, marker_path, shell_pid, konsole_pid, inner_pid):
        self.master = master
        self.sock = sock
        self.marker_path = marker_path
        self.shell_pid = shell_pid
        self.konsole_pid = konsole_pid
        self.inner_pid = inner_pid
        self.to_master = bytearray()
        self._marker_offset = 0
        self.alive = True
        self.shell_gone = False
        self.exit_sent = False
        self.exit_code = None

    def send(self, obj: dict) -> None:
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            self.sock.sendall(data)
        except OSError:
            self.alive = False

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGHUP, self._stop)
        signal.signal(signal.SIGINT, self._forward_sigint)
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
        signal.signal(signal.SIGWINCH, self._on_winch)

        os.set_blocking(self.master, False)
        os.set_blocking(sys.stdin.fileno(), False)

        cols, rows = get_winsize(self.master)
        self.send({
            "t": "hello",
            "pid": self.shell_pid,
            "konsole_pid": self.konsole_pid,
            "inner_pid": self.inner_pid,
            "cols": cols,
            "rows": rows,
        })

        sock_buf = bytearray()
        fds = [self.master, sys.stdin.fileno(), self.sock.fileno()]
        while self.alive and not self.shell_gone:
            try:
                ready, _, _ = select.select(fds, [], [], 0.05)
            except (OSError, ValueError):
                break
            for fd in ready:
                if fd == self.master:
                    self._drain_master()
                elif fd == sys.stdin.fileno():
                    self._drain_stdin()
                else:
                    self._drain_sock(sock_buf)
            self._poll_marker()
            self._flush()
            self._check_child()

        self._finish()

    def _check_child(self) -> None:
        if self.inner_pid <= 0:
            return
        try:
            pid, status = os.waitpid(self.inner_pid, os.WNOHANG)
        except ChildProcessError:
            self.shell_gone = True
            return
        except OSError:
            return
        if pid == 0:
            return
        self.shell_gone = True
        code = os.waitstatus_to_exitcode(status)
        if code is not None and code < 0:
            code = 128 + abs(code)
        self.exit_code = code
        self.exit_sent = True
        self.send({"t": "closed", "reason": "shell exited", "code": code})

    def _drain_master(self) -> None:
        try:
            chunk = os.read(self.master, READ_SIZE)
        except BlockingIOError:
            return
        except OSError:
            self.shell_gone = True
            return
        if not chunk:
            self.shell_gone = True
            return
        try:
            os.write(sys.stdout.fileno(), chunk)
        except OSError:
            self.alive = False
            return
        self.send({"t": "out", "d": B64(chunk).decode("ascii")})

    def _drain_stdin(self) -> None:
        try:
            chunk = os.read(sys.stdin.fileno(), READ_SIZE)
        except (BlockingIOError, OSError):
            return
        if chunk:
            self.to_master += chunk

    def _drain_sock(self, buf: bytearray) -> None:
        try:
            chunk = self.sock.recv(READ_SIZE)
        except (BlockingIOError, OSError):
            return
        if not chunk:
            self.alive = False
            return
        buf += chunk
        while b"\n" in buf:
            line, _, rest = bytes(buf).partition(b"\n")
            buf.clear()
            buf += rest
            try:
                msg = json.loads(line.decode("utf-8"))
            except ValueError:
                continue
            self._handle(msg)

    def _handle(self, msg: dict) -> None:
        kind = msg.get("t")
        if kind == "in":
            self.to_master += base64.b64decode(msg.get("d", ""))
        elif kind == "size":
            set_winsize(self.master, int(msg.get("cols", 0)), int(msg.get("rows", 0)))

    def _flush(self) -> None:
        if not self.to_master:
            return
        data = bytes(self.to_master)
        try:
            written = os.write(self.master, data)
            del self.to_master[:written]
        except BlockingIOError:
            pass
        except OSError:
            self.alive = False

    def _poll_marker(self) -> None:
        try:
            size = os.path.getsize(self.marker_path)
        except OSError:
            return
        if size <= self._marker_offset:
            return
        try:
            with open(self.marker_path, "rb") as fh:
                fh.seek(self._marker_offset)
                chunk = fh.read()
        except OSError:
            return
        cut = chunk.rfind(b"\n")
        if cut < 0:
            return
        self._marker_offset += cut + 1
        for line in chunk[: cut + 1].decode("utf-8", "replace").splitlines():
            if "MCP_MARK" in line:
                parts = line.split("\t")
                code = int(parts[1]) if len(parts) > 1 and parts[1].lstrip("-").isdigit() else -1
                self.send({"t": "mark", "code": code})
            elif "MCP_EXIT" in line:
                parts = line.split("\t")
                code = int(parts[1]) if len(parts) > 1 and parts[1].lstrip("-").isdigit() else None
                self.exit_code = code
                self.exit_sent = True
                self.send({"t": "closed", "reason": "shell exited", "code": code})
                self.alive = False
                self.shell_gone = True

    def _finish(self) -> None:
        deadline = time.time() + 1.5
        while time.time() < deadline and not self.exit_sent:
            self._poll_marker()
            if not self.exit_sent:
                time.sleep(0.1)
        if not self.exit_sent:
            self.send({"t": "closed", "reason": "shell finished"})
        time.sleep(0.1)

    def _stop(self, *_args) -> None:
        self.alive = False
        self.shell_gone = True

    def _forward_sigint(self, *_args) -> None:
        if self.inner_pid > 0:
            with contextlib.suppress(OSError):
                os.killpg(self.inner_pid, signal.SIGINT)

    def _on_winch(self, *_args) -> None:
        cols, rows = get_winsize(sys.stdin.fileno())
        if cols > 0:
            set_winsize(self.master, cols, rows)


def connect_socket(path: str, timeout: float = 15.0) -> socket.socket:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(path)
            return s
        except OSError as exc:
            last = exc
            time.sleep(0.1)
    raise RuntimeError(f"не удалось подключиться к сокету {path}: {last}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sock", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--cwd", default=os.path.expanduser("~"))
    parser.add_argument("--shell", default=os.environ.get("SHELL", "/bin/bash"))
    parser.add_argument("--cols", type=int, default=100)
    parser.add_argument("--rows", type=int, default=30)
    args = parser.parse_args()
    os.makedirs(args.workdir, exist_ok=True)

    sock = connect_socket(args.sock)
    konsole_pid = os.getppid()
    shell_pid = os.getpid()

    master, slave = os.openpty()
    cols, rows = get_winsize(sys.stdin.fileno())
    if cols <= 0:
        cols, rows = args.cols, args.rows
    set_winsize(master, cols, rows)

    marker_path = os.path.join(args.workdir, "marker.log")
    rcfile = os.path.join(args.workdir, "shellrc")
    with open(rcfile, "w", encoding="utf-8") as fh:
        fh.write(RCFILE.format(marker=shlex.quote(marker_path)))

    env = dict(os.environ)
    env["TERM"] = "xterm-256color"
    env.pop("PYTHONSTARTUP", None)

    pid = os.fork()
    if pid == 0:
        try:
            sock.close()
            os.chdir(args.cwd)
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            os.dup2(slave, 0)
            os.dup2(slave, 1)
            os.dup2(slave, 2)
            if slave > STD_FD_LIMIT:
                os.close(slave)
            os.execve(args.shell, [args.shell, "--rcfile", rcfile, "-i"], env)
        except Exception as exc:
            log(f"inner shell failed: {exc}")
        os._exit(1)

    os.close(slave)
    try:
        Pump(master, sock, marker_path, shell_pid, konsole_pid, pid).run()
    except Exception as exc:
        log(f"pump failed: {exc}")
    finally:
        with contextlib.suppress(OSError):
            os.close(master)
        _reap(pid)
    return 0


def _reap(pid: int) -> None:
    """Дожидается завершения внутреннего шелла, не зависая намертво."""
    deadline = time.time() + 3
    while time.time() < deadline:
        try:
            done, _ = os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            return
        if done:
            return
        time.sleep(0.1)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except OSError:
            return
        time.sleep(0.3)
        try:
            done, _ = os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            return
        if done:
            return


if __name__ == "__main__":
    sys.exit(main())
