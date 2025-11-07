#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${MEDIA_PIPELINE_CONFIG:-/etc/media-pipeline/config.yaml}"
DEFAULT_DB="/var/lib/media-pipeline/db.sqlite"
DEFAULT_LOG_DIR="/var/log/media-pipeline"
DB_PATH="${MEDIA_PIPELINE_DB:-$DEFAULT_DB}"
LOG_DIR="${MEDIA_PIPELINE_LOG_DIR:-$DEFAULT_LOG_DIR}"
INSTALL_DIR="${MEDIA_PIPELINE_INSTALL_DIR:-$ROOT_DIR}"
API_URL="${MEDIA_PIPELINE_API_URL:-http://127.0.0.1:8080}"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" && -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$INSTALL_DIR/.venv/bin/python"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 2>/dev/null || echo python3)"
fi

if [[ -z "${MEDIA_PIPELINE_DB:-}" && -f "$CONFIG_PATH" ]]; then
  conf_db=$(grep -E "^\s*db_path:" "$CONFIG_PATH" | head -n1 | awk -F': ' '{print $2}') || true
  if [[ -n "${conf_db:-}" ]]; then
    DB_PATH="$conf_db"
  fi
fi

if [[ -z "${MEDIA_PIPELINE_LOG_DIR:-}" && -f "$CONFIG_PATH" ]]; then
  conf_log=$(grep -E "^\s*log_dir:" "$CONFIG_PATH" | head -n1 | awk -F': ' '{print $2}') || true
  if [[ -n "${conf_log:-}" ]]; then
    LOG_DIR="$conf_log"
  fi
fi

PORT_API="${MEDIA_PIPELINE_PORT_API:-}"
PORT_DBUI="${MEDIA_PIPELINE_PORT_DBUI:-}"
if [[ -z "${PORT_API:-}" && -f "$CONFIG_PATH" ]]; then
  conf_port_api=$(grep -E "^\s*port_api:" "$CONFIG_PATH" | head -n1 | awk -F': ' '{print $2}') || true
  if [[ -n "${conf_port_api:-}" ]]; then
    PORT_API="$conf_port_api"
  fi
fi
if [[ -z "${PORT_DBUI:-}" && -f "$CONFIG_PATH" ]]; then
  conf_port_dbui=$(grep -E "^\s*port_dbui:" "$CONFIG_PATH" | head -n1 | awk -F': ' '{print $2}') || true
  if [[ -n "${conf_port_dbui:-}" ]]; then
    PORT_DBUI="$conf_port_dbui"
  fi
fi
PORT_API="${PORT_API:-8080}"
PORT_DBUI="${PORT_DBUI:-8081}"

section() {
  printf '\n========== %s ==========' "$1"
  printf '\n'
}

run_cmd() {
  printf '\n$'
  for arg in "$@"; do
    printf ' %q' "$arg"
  done
  printf '\n'
  "$@"
  local status=$?
  if [[ $status -ne 0 ]]; then
    printf '(command exited with status %s)\n' "$status" >&2
  fi
}

section "Environment"
run_cmd uname -a
if command -v hostnamectl >/dev/null 2>&1; then
  run_cmd hostnamectl
fi
if command -v python3 >/dev/null 2>&1; then
  run_cmd python3 --version
else
  echo "python3 not found on PATH"
fi
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  run_cmd "$ROOT_DIR/.venv/bin/python" --version
elif [[ -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  run_cmd "$INSTALL_DIR/.venv/bin/python" --version
fi

section "Filesystem"
printf 'Project root: %s\n' "$ROOT_DIR"
printf 'Install dir:  %s\n' "$INSTALL_DIR"
printf 'Config path:  %s\n' "$CONFIG_PATH"
printf 'DB path:      %s\n' "$DB_PATH"
printf 'Log dir:      %s\n' "$LOG_DIR"

section "Python packages"
if [[ -x "$ROOT_DIR/.venv/bin/pip" ]]; then
  run_cmd "$ROOT_DIR/.venv/bin/pip" list
elif [[ -x "$INSTALL_DIR/.venv/bin/pip" ]]; then
  run_cmd "$INSTALL_DIR/.venv/bin/pip" list
else
  echo "Virtual environment not detected at $ROOT_DIR/.venv or $INSTALL_DIR/.venv"
fi

section "Configuration snapshot"
if [[ -f "$CONFIG_PATH" ]]; then
  run_cmd sed -n "1,200p" "$CONFIG_PATH"
else
  echo "Config file not found. Override MEDIA_PIPELINE_CONFIG to specify a custom path."
fi

section "Web UI"
host_guess="${MEDIA_PIPELINE_HOST_IP:-}"
if [[ -z "$host_guess" ]]; then
  host_guess=$(hostname -I 2>/dev/null | awk '{print $1}') || true
fi
if [[ -z "${host_guess:-}" ]]; then
  host_guess="127.0.0.1"
fi
printf 'Control:   http://%s:%s/control\n' "$host_guess" "$PORT_API"
printf 'Dashboard: http://%s:%s/dashboard\n' "$host_guess" "$PORT_API"
printf 'DB UI:     http://%s:%s\n' "$host_guess" "$PORT_DBUI"
printf 'Local API: http://127.0.0.1:%s\n' "$PORT_API"
if [[ -n "$API_URL" ]]; then
  printf 'Configured API URL: %s\n' "$API_URL"
fi

read_syncthing_config() {
  PYTHONPATH="$ROOT_DIR" CONFIG_FOR_SCRIPT="$CONFIG_PATH" "$PYTHON_BIN" <<'PY'
import os
import shlex
from utils.config_loader import load_config, resolve_config_path

config_path = os.environ.get("CONFIG_FOR_SCRIPT")
resolved = resolve_config_path(config_path)
config = load_config(resolved)
syncthing = config.get("syncthing", {})

api_url = str(syncthing.get("api_url") or "")
folder_id = syncthing.get("folder_id") or ""
device_id = syncthing.get("device_id") or ""
api_key = str(syncthing.get("api_key") or "")

print(f"SYNCTHING_CONFIG_PATH={shlex.quote(str(resolved))}")
print(f"SYNCTHING_API_URL={shlex.quote(api_url)}")
print(f"SYNCTHING_FOLDER_ID={shlex.quote(folder_id)}")
print(f"SYNCTHING_DEVICE_ID={shlex.quote(device_id)}")
print(f"SYNCTHING_API_KEY_VALUE={shlex.quote(api_key)}")
print(f"SYNCTHING_API_KEY_LEN={len(api_key)}")
print(f"SYNCTHING_API_KEY_SUFFIX={shlex.quote(api_key[-4:] if api_key else '')}")
PY
}

eval "$(read_syncthing_config)"

SYNCTHING_REST_ENDPOINT="${SYNCTHING_API_URL%/}"
if [[ -n "$SYNCTHING_REST_ENDPOINT" && "$SYNCTHING_REST_ENDPOINT" != */rest ]]; then
  SYNCTHING_REST_ENDPOINT+="/rest"
fi
SYNCTHING_STATUS_URL="${SYNCTHING_REST_ENDPOINT}/system/status"
SYNCTHING_UI_URL="${SYNCTHING_REST_ENDPOINT%/rest}"

section "Syncthing"
printf 'Config file: %s\n' "${SYNCTHING_CONFIG_PATH:-$CONFIG_PATH}"
printf 'REST API:   %s\n' "${SYNCTHING_REST_ENDPOINT:-N/A}"
printf 'UI URL:     %s\n' "${SYNCTHING_UI_URL:-N/A}"
printf 'Folder ID:  %s\n' "${SYNCTHING_FOLDER_ID:-"(not set)"}"
printf 'Device ID:  %s\n' "${SYNCTHING_DEVICE_ID:-"(not set)"}"
printf 'API Port:   %s\n' "$PORT_API"
printf 'DB UI Port: %s\n' "$PORT_DBUI"
if [[ ${SYNCTHING_API_KEY_LEN:-0} -gt 0 ]]; then
  printf 'API key:    set (len=%s, ends with %s)\n' "$SYNCTHING_API_KEY_LEN" "${SYNCTHING_API_KEY_SUFFIX:-""}"
else
  echo "API key:    not configured"
fi
if command -v systemctl >/dev/null 2>&1; then
  run_cmd systemctl status "syncthing@$USER"
fi
if command -v curl >/dev/null 2>&1 && [[ -n "$SYNCTHING_REST_ENDPOINT" ]]; then
  syncthing_headers=()
  if [[ ${SYNCTHING_API_KEY_LEN:-0} -gt 0 ]]; then
    syncthing_headers=(-H "X-API-Key: ${SYNCTHING_API_KEY_VALUE}")
  fi
  run_cmd curl -fsS "${syncthing_headers[@]}" "$SYNCTHING_STATUS_URL"
  if [[ -n "${SYNCTHING_FOLDER_ID:-}" ]]; then
    completion_url="$SYNCTHING_REST_ENDPOINT/db/completion?folder=${SYNCTHING_FOLDER_ID}"
    if [[ -n "${SYNCTHING_DEVICE_ID:-}" ]]; then
      completion_url+="&device=${SYNCTHING_DEVICE_ID}"
    fi
    run_cmd curl -fsS "${syncthing_headers[@]}" "$completion_url"
  fi
else
  echo "curl not available or Syncthing API URL missing; skipping status check."
fi

section "Database"
if command -v sqlite3 >/dev/null 2>&1 && [[ -f "$DB_PATH" ]]; then
  run_cmd sqlite3 "$DB_PATH" ".tables"
  run_cmd sqlite3 "$DB_PATH" "SELECT COUNT(*) AS files FROM files;"
  run_cmd sqlite3 "$DB_PATH" "SELECT COUNT(*) AS errors FROM files WHERE error IS NOT NULL AND error != '';"
else
  echo "Database not reachable. Ensure sqlite3 is installed and the DB path is correct."
fi

section "Service status"
if command -v systemctl >/dev/null 2>&1; then
  run_cmd systemctl status media-pipeline
else
  echo "systemctl not available on this host."
fi

section "Recent logs"
if [[ -d "$LOG_DIR" ]]; then
  recent_logs=$(find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' | head -n 5)
  if [[ -n "$recent_logs" ]]; then
    for log_file in $recent_logs; do
      printf '\n--- %s (last 50 lines) ---\n' "$log_file"
      tail -n 50 "$log_file" || true
    done
  else
    echo "No log files found in $LOG_DIR"
  fi
else
  echo "Log directory not found."
fi

section "HTTP health check"
if command -v curl >/dev/null 2>&1; then
  run_cmd curl -fsS "$API_URL/health"
else
  echo "curl not available; skipping API health check."
fi

section "Completed"
printf 'Debug capture finished at %s\n' "$(date --iso-8601=seconds 2>/dev/null || date)"
