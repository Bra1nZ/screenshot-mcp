"""Общие помощники для бэкендов снимка экрана."""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import time
from datetime import datetime

DEFAULT_FILENAME = "Screenshot from {stamp}.png"


def png_size(path: str) -> tuple[int, int] | None:
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", head[16:24])
    except (OSError, struct.error):
        return None


def pictures_dir() -> str:
    try:
        proc = subprocess.run(
            ["xdg-user-dir", "PICTURES"], capture_output=True, text=True, timeout=5, check=False
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return os.path.expanduser("~/Pictures")


def _locale_folder() -> str:
    lang = (
        os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or "en_US"
    )
    return "Снимки экрана" if lang.lower().startswith("ru") else "Screenshots"


def default_screenshot_dir() -> str:
    """Стандартная папка для снимков: как настроена в KDE, иначе по локали."""
    name = _locale_folder()
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


def default_screenshot_path() -> str:
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H-%M-%S")
    return os.path.join(default_screenshot_dir(), DEFAULT_FILENAME.format(stamp=stamp))


def run_capture(cmd: list[str], path: str, delay_ms: int = 0) -> dict:
    """Выполнить команду, которая сохраняет снимок в path."""
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    if not shutil.which(cmd[0]):
        return {"ok": False, "path": path, "error": f"{cmd[0]} не найден в PATH"}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "path": path, "error": str(exc)}
    if proc.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 0:
        return {"ok": True, "path": path}
    error = (proc.stderr or proc.stdout or "").strip()
    return {"ok": False, "path": path, "error": error or f"{cmd[0]} не смог сохранить снимок"}


def session_locked() -> bool:
    """Заблокирован ли экран: под lock screen композитор не отдаёт снимки."""
    for probe in (["pgrep", "-f", "kscreenlocker_greet"], ["pgrep", "-f", "kscreenlocker"]):
        try:
            proc = subprocess.run(probe, capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            return True
    return False
