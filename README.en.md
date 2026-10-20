# screenshot-mcp

An MCP server for **KDE Plasma 6 / Wayland**: an agent opens a real terminal window,
drives it, and captures the desktop with the system's own screenshot tool (Spectacle
— the same binary Plasma runs on PrintScreen).

The hard part is that the usual terminal automation tricks do not work under Wayland:
`xdotool` cannot type into native Wayland applications, `wmctrl` does not exist, and
`tmux` can drive a session but not a window on screen. Here the input is written
**straight into a pseudoterminal**, so the terminal renders it exactly like keyboard
input — no key emulation, no traces left in the interface.

Features:

* a separate terminal window running **your** `~/.bashrc` — your prompt, colours, aliases;
* run commands, read the output and the exit status;
* interactive programs: input, `Ctrl+C`, `Ctrl+D`, arrows, command history;
* a full-desktop capture with the terminal window raised to the front;
* the capture is returned to the agent as an image, so it can judge what ended up in
  the frame.

## How it works

```
MCP server (server.py)
   │  UNIX socket, JSON
   ▼
bridge.py — the pump: relays input and output
   │  pseudoterminal (pty)
   ▼
bash — running inside the Konsole window, inherits ~/.bashrc
```

* A real `bash` runs **inside** the Konsole window and sources the user's `.bashrc`.
  The window title is indistinguishable from a regular one (`<dir> : bash — Konsole`).
* The agent writes bytes directly into the pty. The tty driver echoes them and
  `readline` handles them — literally the same path as keyboard input. Because no keys
  are emulated, nothing in the terminal betrays the automation.
* The exit status is taken from a `PROMPT_COMMAND` hook that writes a marker to a
  side file: nothing shows up on screen.
* The window is raised by a KWin script: the window is located by the PID of its
  Konsole process, and activation is `workspace.activeWindow = client`.
* The capture is `spectacle -b -n -o <file>` — the same binary Plasma launches on
  PrintScreen, so the image is indistinguishable from a manual one.

## Requirements

* KDE Plasma 6 in a Wayland session;
* `konsole` and `spectacle` (both ship with Plasma 6);
* `qdbus6` for KWin scripting;
* Python 3.11+ and the `mcp` package.

Tested on Debian 13, KDE Plasma 6.3, Wayland.

## Install

```bash
git clone git@github.com:Bra1nZ/screenshot-mcp.git
cd screenshot-mcp
pip install -r requirements.txt
```

## Connecting

### opencode

`~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "screenshot-mcp": {
      "command": ["python3", "/path/to/screenshot-mcp/server.py"],
      "type": "local"
    }
  }
}
```

### Other MCP clients

The server speaks over stdio, so it fits any client with local MCP server support:

```bash
python3 /path/to/screenshot-mcp/server.py
```

The server must run **inside the graphical session** and inherits `WAYLAND_DISPLAY`
and `DBUS_SESSION_BUS_ADDRESS`; when they are missing, defaults for the current user
are substituted.

## Tools

| Tool | Purpose |
|---|---|
| `console_open(cwd, cols, rows, title, terminal)` | open a new terminal window, return `console_id` |
| `console_exec(console_id, command, timeout, typing_delay_ms)` | type a command and wait for the result: `output`, `exit_code`, `timed_out` |
| `console_send(console_id, text, enter)` | type text without running it — for programs awaiting input |
| `console_key(console_id, key)` | special keys: `enter`, `tab`, `esc`, `up`/`down`, `ctrl+c`, `ctrl+d`, `f1`..`f12` |
| `console_read(console_id, cursor)` | read the new output |
| `console_state(console_id)` / `console_list()` | console state |
| `console_close(console_id)` | close the window |
| `desktop_screenshot(path, console_id, delay_ms, preview)` | desktop capture; `console_id` raises the window first; returns metadata and a downscaled preview |
| `desktop_focus(console_id)` | raise the terminal window |
| `desktop_active_window()` / `desktop_list_windows()` | what is in the foreground, window list |

## Example session

```
console_open(cwd="~/projects/lab")        → console_id
console_exec(console_id, "make")          → output, exit_code
console_exec(console_id, "ls -la build/")  → confirm the artefacts
desktop_screenshot(console_id=console_id)  → PNG in ~/Pictures/Screenshots + image in the reply
```

## Limitations

* **KDE Plasma 6 / Wayland only.** The console and the capture also work under X11,
  but raising the window is implemented through KWin scripting, so it needs KWin.
* **The screen must be unlocked.** While the lock screen is active, KWin refuses to
  hand out captures — a compositor safeguard. `desktop_screenshot` returns a clear
  message in that case.
* Tab characters in commands are not supported: `bash` treats them as a completion
  request.
* `console_exec` waits for the next prompt; long tasks need a `timeout`, interactive
  programs need `console_send` and `console_key`.

## Security

The server gives the connected agent **full control over a terminal in the graphical
session and read access to the screen contents**. This is an automation tool, not a
sandbox: run it only with an agent you trust, and do not leave console windows with
live sessions open.

Captures are written to the standard KDE screenshots folder and duplicated into
`screenshots/` next to the server — remember they may contain sensitive data.

## Tests

The tests are live: they open real windows and capture the real screen, so they need
a running KDE Plasma session.

```bash
pip install -r requirements-dev.txt
python3 tests/test_bridge.py      # pty bridge: commands, output, exit status
python3 tests/test_interactive.py  # program input, ctrl+c, history
python3 tests/test_e2e.py          # full cycle: window → commands → focus → capture
python3 tests/test_mcp_stdio.py    # MCP protocol: tool list and calls
```

CI (`.github/workflows/ci.yml`) runs the linter and an import check only — the live
tests cannot run in a container without a compositor.

## License

MIT — see [LICENSE](LICENSE).
