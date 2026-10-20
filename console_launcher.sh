#!/bin/bash
# Запускается окном Konsole. Держит терминал под именем bash (как в обычной
# консоли), а перекачку ввода/вывода берёт на себя bridge.py.
# Аргументы: --sock ... --workdir ... --cwd ... --shell ...
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${MCP_PYTHON:-python3}" "$DIR/bridge.py" "$@"
exit $?
