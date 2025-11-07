#!/bin/bash
set -euo pipefail

APP_DIR="/opt/media-pipeline"
RUN_DIR="$APP_DIR/run"
PY_ENV="$APP_DIR/.venv"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Application directory $APP_DIR not found. Nothing to stop." >&2
  exit 0
fi

stop_process() {
  local pid_file="$1"
  local label="$2"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(cat "$pid_file")
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "Stopping $label (pid $pid)"
      kill "$pid" 2>/dev/null || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$pid_file"
  fi
}

stop_process "$RUN_DIR/api.pid" "API server"
stop_process "$RUN_DIR/dbui.pid" "DB UI"

if command -v pkill >/dev/null 2>&1; then
  pkill -f "$PY_ENV/bin/uvicorn" 2>/dev/null || true
  pkill -f "$PY_ENV/bin/sqlite_web" 2>/dev/null || true
fi

echo "Processes stopped."
