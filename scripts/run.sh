#!/bin/bash
set -euo pipefail

APP_DIR="/opt/media-pipeline"
DB_PATH="/var/lib/media-pipeline/db.sqlite"
PY_ENV="$APP_DIR/.venv"
CONFIG_PATH="${MEDIA_PIPELINE_CONFIG:-/etc/media-pipeline/config.yaml}"
RUN_DIR="$APP_DIR/run"
DEFAULT_LOG_DIR="$APP_DIR/data/logs"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Application directory $APP_DIR not found. Have you run install.sh?" >&2
  exit 1
fi

if [[ ! -d "$PY_ENV" ]]; then
  echo "Virtual environment missing at $PY_ENV. Run setup.sh to provision dependencies." >&2
  exit 1
fi

mkdir -p "$RUN_DIR"

# shellcheck disable=SC1091
source "$PY_ENV/bin/activate"

export PYTHONPATH="$APP_DIR:${PYTHONPATH:-}"

read_config() {
  CONFIG_FOR_SCRIPT="$CONFIG_PATH" DEFAULT_LOG_DIR="$DEFAULT_LOG_DIR" "$PY_ENV/bin/python" <<'PY'
import os
import shlex
from utils.config_loader import get_config_value, load_config

config_path = os.environ.get("CONFIG_FOR_SCRIPT")
default_log_dir = os.environ.get("DEFAULT_LOG_DIR") or "${DEFAULT_LOG_DIR}"

try:
    config = load_config(config_path)
except FileNotFoundError:
    config = load_config()

log_dir = get_config_value("system", "log_dir", default=default_log_dir, config=config)
port_api = get_config_value("system", "port_api", default=8080, config=config)
port_dbui = get_config_value("system", "port_dbui", default=8081, config=config)

print(f"LOG_DIR={shlex.quote(str(log_dir))}")
print(f"PORT_API={int(port_api)}")
print(f"PORT_DBUI={int(port_dbui)}")
PY
}

eval "$(read_config)"

LOG_DIR="${LOG_DIR:-$DEFAULT_LOG_DIR}"
mkdir -p "$LOG_DIR"

API_PID_FILE="$RUN_DIR/api.pid"
DBUI_PID_FILE="$RUN_DIR/dbui.pid"

stop_if_running() {
  local pid_file="$1"
  local label="$2"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(cat "$pid_file")
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "Stopping existing $label (pid $pid)"
      kill "$pid" 2>/dev/null || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$pid_file"
  fi
}

stop_if_running "$API_PID_FILE" "API server"
stop_if_running "$DBUI_PID_FILE" "DB UI"

pushd "$APP_DIR" >/dev/null || exit 1

UVICORN_ARGS=("$PY_ENV/bin/uvicorn" "main:app" "--host" "0.0.0.0" "--port" "$PORT_API")
if [[ "${UVICORN_RELOAD:-}" =~ ^(1|true|yes)$ ]]; then
  UVICORN_ARGS+=("--reload")
fi

nohup "${UVICORN_ARGS[@]}" >"$LOG_DIR/api.log" 2>&1 &
echo $! >"$API_PID_FILE"

nohup "$PY_ENV/bin/sqlite_web" "$DB_PATH" --host 0.0.0.0 --port "$PORT_DBUI" >"$LOG_DIR/dbui.log" 2>&1 &
echo $! >"$DBUI_PID_FILE"

popd >/dev/null

echo "API:     http://<host>:$PORT_API"
echo "DB-UI:   http://<host>:$PORT_DBUI"
echo "Logs:    $LOG_DIR (api.log, dbui.log)"
