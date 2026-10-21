"""Генератор скрипта-лаунчера для окна терминала.

Лаунчер запускается терминалом и выполняет мост (bridge.py). Важно, что он
не делает exec: тогда процессом в терминале остаётся bash — заголовок окна
и поведение неотличимы от обычной консоли.
"""

from __future__ import annotations

import os
import shlex

TEMPLATE = """#!/bin/bash
# Создаётся автоматически: держит терминал под именем bash и запускает мост.
export PYTHONPATH={package_root}${{PYTHONPATH:+:$PYTHONPATH}}
{python} {bridge} "$@"
exit $?
"""


def render_launcher(python: str, package_root: str, bridge: str) -> str:
    return TEMPLATE.format(
        package_root=shlex.quote(package_root),
        python=shlex.quote(python),
        bridge=shlex.quote(bridge),
    )


def write_launcher(path: str, python: str, package_root: str, bridge: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_launcher(python, package_root, bridge))
    os.chmod(path, 0o700)
    return path
