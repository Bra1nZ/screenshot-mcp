#!/bin/bash
# Запуск MCP-сервера вручную (для отладки): stdio-протокол MCP.
exec "${MCP_PYTHON:-python3}" "$(dirname "${BASH_SOURCE[0]}")/server.py" "$@"
