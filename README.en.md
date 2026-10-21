# screenshot-mcp

An MCP server that gives an agent a **real terminal window** on the desktop and
**screen captures** taken with the system's own screenshot tool.

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
core/bridge.py — the pump: relays input and output
   │  pseudoterminal (pty)
   ▼
bash — running inside the terminal window, inherits ~/.bashrc
```

* A real `bash` runs **inside** the terminal window and sources the user's `.bashrc`.
  The window title is indistinguishable from a regular one (`<dir> : bash — Konsole`).
* The agent writes bytes directly into the pty. The tty driver echoes them and
  `readline` handles them — literally the same path as keyboard input. Because no keys
  are emulated, nothing in the terminal betrays the automation.
* The exit status is taken from a `PROMPT_COMMAND` hook that writes a marker to a
  side file: nothing shows up on screen.

## Architecture

Platform differences live in backends; the core does not depend on them:

```
screenshot_mcp/
├── core/            pty bridge, console session, launcher — POSIX, works everywhere
├── backends/
│   ├── terminal/    konsole · xterm · gnome-terminal
│   ├── screenshot/  spectacle · x11 · gnome
│   └── focus/       kwin · xdo_tool · atspi · none
├── config.py        environment detection and user settings
└── runtime.py       assembles environment, settings and backends
```

Backends are selected automatically from the session type (`XDG_SESSION_TYPE`) and
the desktop environment (`XDG_CURRENT_DESKTOP`). You can always pick one explicitly —
see [Configuration](#configuration).

## Supported environments

| Environment | Terminal window | Screen capture | Raise window |
|---|---|---|---|
| KDE Plasma 6 / Wayland | Konsole | Spectacle | KWin scripting |
| KDE Plasma / X11 | Konsole, xterm | ImageMagick, scrot, maim | xdotool |
| GNOME / Wayland | gnome-terminal | gnome-screenshot | AT-SPI |
| X11 (any DE) | xterm, gnome-terminal | ImageMagick, scrot, maim | xdotool |

> **What has been verified live:** only the **KDE Plasma / Wayland** path — that is
> the one all tests were run against. The X11 and GNOME paths are written against
> the documentation of the tools they use (`scrot`, `maim`, `import`, `xdotool`,
> `gnome-screenshot`, AT-SPI) and need checking on your own hardware: the terminal
> and the capture run through the same core backends there, but raising a window
> relies on `xdotool` under X11 and on AT-SPI under GNOME, and their availability
> depends on the environment.

## Requirements

* Python 3.11+ and the `mcp` package;
* a terminal: `konsole`, `xterm` or `gnome-terminal`;
* for captures: `spectacle` (KDE), or `scrot`/`maim`/`import` (X11), or
  `gnome-screenshot` (GNOME);
* for raising windows: KWin (ships with Plasma) or `xdotool` on X11;
* `dbus-python` and `PyGObject` — to receive reports from KWin scripts and to use AT-SPI.

Tested on Debian 13, KDE Plasma 6.3, Wayland.

## Install

```bash
git clone git@github.com:Bra1nZ/screenshot-mcp.git
cd screenshot-mcp
pip install -r requirements.txt
```

## Configuration

By default the backends are picked from the environment. To choose explicitly, create
`~/.config/screenshot-mcp/config.toml`:

```toml
[terminal]
backend = "konsole"      # konsole | xterm | gnome-terminal

[screenshot]
backend = "spectacle"    # spectacle | x11 | gnome

[focus]
backend = "kwin"         # kwin | xdo_tool | atspi | none
```

A different path can be set with the `SCREENSHOT_MCP_CONFIG` environment variable.

## Connecting

### opencode

`~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "desktop-console": {
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
desktop_screenshot(console_id=console_id)  → PNG in the screenshots folder + image in the reply
```

## Limitations

* **The screen must be unlocked.** While the lock screen is active, the compositor
  refuses to hand out captures — a compositor safeguard, not a server bug.
  `desktop_screenshot` returns a clear message in that case.
* Under GNOME raising a window does not always work: there is no compositor scripting
  there, and AT-SPI is not implemented by every application. The capture still works,
  but another window may be in the frame.
* Tab characters in commands are not supported: `bash` treats them as a completion
  request.
* `console_exec` waits for the next prompt; long tasks need a `timeout`, interactive
  programs need `console_send` and `console_key`.

## Security

The server gives the connected agent **full control over a terminal in the graphical
session and read access to the screen contents**. This is an automation tool, not a
sandbox: run it only with an agent you trust, and do not leave console windows with
live sessions open.

Captures are written to the standard screenshots folder and duplicated into
`screenshots/` next to the server — remember they may contain sensitive data.

## Tests

The live tests are live: they open real windows and capture the real screen, so they
need a running graphical session.

```bash
pip install -r requirements-dev.txt
python3 tests/test_backends.py      # unit tests: config and backends (no GUI needed)
python3 tests/test_bridge.py        # pty bridge: commands, output, exit status
python3 tests/test_interactive.py   # program input, ctrl+c, history
python3 tests/test_e2e.py           # full cycle: window → commands → focus → capture
python3 tests/test_agent_flow.py    # the same through the real MCP protocol
python3 tests/test_mcp_stdio.py     # MCP protocol: tool list and calls
```

CI (`.github/workflows/ci.yml`) runs the linter, the unit tests and an import check —
the live tests cannot run in a container without a compositor.

## License

MIT — see [LICENSE](LICENSE).
