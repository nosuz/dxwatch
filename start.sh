#!/bin/bash
set -e
caddy run --config /app/Caddyfile &
exec /home/vscode/.local/bin/uv run uvicorn server:app --host 127.0.0.1 --port 8001
