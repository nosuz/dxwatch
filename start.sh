#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CADDY_PID=""
UVICORN_PID=""

cleanup() {
  local exit_code=${1:-0}

  echo "[start.sh] shutting down..."

  if [ -n "${UVICORN_PID}" ] && kill -0 "${UVICORN_PID}" 2>/dev/null; then
    kill -TERM "${UVICORN_PID}" 2>/dev/null || true
  fi

  if [ -n "${CADDY_PID}" ] && kill -0 "${CADDY_PID}" 2>/dev/null; then
    kill -TERM "${CADDY_PID}" 2>/dev/null || true
  fi

  wait || true
  return "$exit_code"
}

on_signal() {
  echo "[start.sh] signal received"
  cleanup 0
  exit 0
}

trap on_signal TERM INT

start_caddy() {
  caddy run --config "$SCRIPT_DIR/Caddyfile" 2>&1 \
    | sed -u 's/^/[caddy] /' &
  CADDY_PID=$!
}

start_uvicorn() {
 uv run uvicorn server:app \
    --host 127.0.0.1 --port 8001 \
    2>&1 | sed -u 's/^/[uvicorn] /' &
  UVICORN_PID=$!
}

start_caddy
start_uvicorn

set +e
wait -n "$CADDY_PID" "$UVICORN_PID"
EXIT_CODE=$?
set -e

echo "[start.sh] one process exited with code $EXIT_CODE"

cleanup "$EXIT_CODE"
exit "$EXIT_CODE"
